"""Métricas do painel no formato do Prometheus (texto), sem bibliotecas: as três métricas de ouro do lado da
aplicação (latência, tráfego e erros). A quarta, saturação (CPU e memória), vem do cAdvisor.

  painel_http_requests_total{metodo, rota, status}           tráfego e erros (status 4xx/5xx)
  painel_http_request_duration_seconds{metodo, rota}         latência (histograma)
  painel_alertas_buscas_total{resultado}                     buscas na NASA, com sucesso ou falha
  painel_alertas_busca_duracao_segundos                      quanto durou a última busca
  painel_alertas_focos_ativos / painel_alertas_focos_em_alerta   o que a última busca trouxe

A rota é normalizada (só as rotas conhecidas viram rótulo): um robô pedindo milhares de endereços diferentes
não cria milhares de séries no Prometheus.
"""
import threading
import time
from collections import defaultdict

# Segundos. O painel responde em milissegundos; os baldes maiores pegam a lentidão de verdade
BALDES = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
METODOS_CONHECIDOS = {"GET", "POST", "HEAD"}


def normalizar_rota(caminho: str, funcoes) -> str:
    caminho = caminho.split("?", 1)[0]
    if caminho in ("/", "/index.html"):
        return "/"
    if caminho in ("/healthz", "/metrics"):
        return caminho
    if caminho.startswith("/api/"):
        nome = caminho.removeprefix("/api/")
        return f"/api/{nome}" if nome in funcoes else "/api/desconhecida"
    return "desconhecida"


def _rotulos(**pares) -> str:
    def escapar(valor) -> str:
        return str(valor).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    return "{" + ",".join(f'{chave}="{escapar(valor)}"' for chave, valor in pares.items()) + "}"


def _numero(valor: float) -> str:
    return repr(float(valor)) if valor != int(valor) else f"{int(valor)}"


class Metricas:
    def __init__(self):
        self._trava = threading.Lock()
        self._pedidos = defaultdict(int)  # (metodo, rota, status) -> quantidade
        self._baldes = defaultdict(lambda: [0] * len(BALDES))  # (metodo, rota) -> contagem por balde
        self._soma = defaultdict(float)  # (metodo, rota) -> soma das durações
        self._contagem = defaultdict(int)  # (metodo, rota) -> quantidade
        self._buscas = {"ok": 0, "erro": 0}
        self._ultima_busca = None  # duração em segundos
        self._focos = None  # (ativos, em_alerta)

    def pedido(self, metodo: str, rota: str, status: int, duracao: float) -> None:
        metodo = metodo if metodo in METODOS_CONHECIDOS else "OUTRO"
        with self._trava:
            self._pedidos[(metodo, rota, int(status))] += 1
            chave = (metodo, rota)
            for i, limite in enumerate(BALDES):
                if duracao <= limite:
                    self._baldes[chave][i] += 1
            self._soma[chave] += duracao
            self._contagem[chave] += 1

    def busca(self, resultado: str, duracao: float, ativos=None, em_alerta=None) -> None:
        with self._trava:
            self._buscas[resultado] = self._buscas.get(resultado, 0) + 1
            self._ultima_busca = duracao
            if ativos is not None:
                self._focos = (ativos, em_alerta or 0)

    def texto(self) -> str:
        """Tudo no formato de exposição do Prometheus (text/plain; version=0.0.4)."""
        linhas = []
        with self._trava:
            linhas += ["# HELP painel_http_requests_total Pedidos HTTP atendidos pelo painel.",
                       "# TYPE painel_http_requests_total counter"]
            for (metodo, rota, status), quantidade in sorted(self._pedidos.items()):
                linhas.append(f"painel_http_requests_total{_rotulos(metodo=metodo, rota=rota, status=status)} {quantidade}")

            linhas += ["# HELP painel_http_request_duration_seconds Tempo de resposta dos pedidos HTTP.",
                       "# TYPE painel_http_request_duration_seconds histogram"]
            for (metodo, rota) in sorted(self._contagem):
                contagens = self._baldes[(metodo, rota)]
                for limite, quantidade in zip(BALDES, contagens):
                    linhas.append("painel_http_request_duration_seconds_bucket"
                                  f"{_rotulos(metodo=metodo, rota=rota, le=_numero(limite))} {quantidade}")
                total = self._contagem[(metodo, rota)]
                linhas.append(f"painel_http_request_duration_seconds_bucket{_rotulos(metodo=metodo, rota=rota, le='+Inf')} {total}")
                linhas.append(f"painel_http_request_duration_seconds_sum{_rotulos(metodo=metodo, rota=rota)} {self._soma[(metodo, rota)]!r}")
                linhas.append(f"painel_http_request_duration_seconds_count{_rotulos(metodo=metodo, rota=rota)} {total}")

            linhas += ["# HELP painel_alertas_buscas_total Buscas de focos na NASA (FIRMS), por resultado.",
                       "# TYPE painel_alertas_buscas_total counter"]
            for resultado, quantidade in sorted(self._buscas.items()):
                linhas.append(f"painel_alertas_buscas_total{_rotulos(resultado=resultado)} {quantidade}")

            if self._ultima_busca is not None:
                linhas += ["# HELP painel_alertas_busca_duracao_segundos Duração da última busca na NASA.",
                           "# TYPE painel_alertas_busca_duracao_segundos gauge",
                           f"painel_alertas_busca_duracao_segundos {self._ultima_busca!r}"]
            if self._focos is not None:
                linhas += ["# HELP painel_alertas_focos_ativos Focos ativos na última busca.",
                           "# TYPE painel_alertas_focos_ativos gauge",
                           f"painel_alertas_focos_ativos {self._focos[0]}",
                           "# HELP painel_alertas_focos_em_alerta Focos do nível de alerta para cima na última busca.",
                           "# TYPE painel_alertas_focos_em_alerta gauge",
                           f"painel_alertas_focos_em_alerta {self._focos[1]}"]
        return "\n".join(linhas) + "\n"


def consultar_medido(consultar, metricas: Metricas):
    """A consulta à NASA, contando sucessos, falhas e quanto tempo levou."""
    def medida(**argumentos):
        inicio = time.monotonic()
        try:
            resultado = consultar(**argumentos)
        except Exception:
            metricas.busca("erro", time.monotonic() - inicio)
            raise
        if isinstance(resultado, dict) and "erro" not in resultado:
            metricas.busca("ok", time.monotonic() - inicio, resultado.get("ativos"), resultado.get("em_alerta"))
        else:
            metricas.busca("erro", time.monotonic() - inicio)
        return resultado
    return medida
