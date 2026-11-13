"""Painel web de alertas: a mesma página da aba Alertas (recursos/alertas.html), servida por HTTP.

A página não muda: ela continua chamando window.pywebview.api.<função>(...). Aqui, uma ponte no começo da página
troca o pywebview por chamadas HTTP (POST /api/<função>) ao mesmo ServicoAlertas que a Central usa.

Só a biblioteca padrão do Python, para a imagem do contêiner ficar pequena. Sem login: o painel fica no perfil
operador (só lê) a não ser que PAINEL_PERFIL=administrador, e o docker-compose.yml só o publica em 127.0.0.1.

Variáveis de ambiente (nenhuma é segredo, a não ser as chaves do robô):
  PAINEL_HOST, PAINEL_PORTA       onde escutar (padrão 127.0.0.1:8080; no contêiner, 0.0.0.0:8080)
  PAINEL_PERFIL                   operador (padrão) ou administrador (pode mudar a busca automática)
  ALERTAS_INTERVALO               minutos entre as buscas automáticas, um de INTERVALOS (padrão 60; 0 desliga)
  ALERTAS_BUSCAR_AO_INICIAR       1 (padrão): faz uma busca logo ao subir; 0: espera o intervalo
  FIRMS_MAP_KEY, MAPTILER_KEY...  as do robô FIRMS Monitor (as mesmas do .env)
"""
import json
import logging
import os
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from merlin.config import ARQ_ALERTAS, ARQ_ULTIMA_CONSULTA
from merlin.interface.mapa import com_mapa
from merlin.interface.painel_alertas import INTERVALOS, ApiAlertas, ServicoAlertas

logger = logging.getLogger(__name__)

INTERVALO_PADRAO = 60
MAX_CORPO = 4096  # bytes: os pedidos da página são minúsculos (no máximo dois números)
# As funções da página e quantos argumentos cada uma recebe. abrir_mapa fica na ponte: abre no navegador de quem
# está vendo o painel, e não no servidor.
METODOS = {"ultima": 0, "mais_recente": 0, "vistos": 0, "estado_automatico": 0, "configurar": 2, "fundos": 0,
           "escolher_fundo": 1}
CABECALHO_PONTE = "X-Painel"  # só a ponte manda: outro site não consegue mandar sem a permissão do CORS, que não damos

# Vai no começo da página: a mesma API do pywebview, por HTTP, e o aviso de "pronto" quando a página carrega
PONTE = """<script>
  (() => {
    const chamar = async (nome, args) => {
      const resposta = await fetch(`api/${encodeURIComponent(nome)}`, { method: "POST",
        headers: { "Content-Type": "application/json", "%(cabecalho)s": "1" }, body: JSON.stringify(args) });
      if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
      return resposta.json();
    };
    const abrirMapa = async (latitude, longitude) => {
      const lat = Number(latitude), lon = Number(longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return { erro: "Coordenadas inválidas." };
      window.open(`https://www.google.com/maps?q=${lat},${lon}`, "_blank", "noopener,noreferrer");
      return {};
    };
    window.pywebview = { api: new Proxy({}, { get: (_, nome) => nome === "abrir_mapa" ? abrirMapa : (...args) => chamar(nome, args) }) };
    window.addEventListener("load", () => window.dispatchEvent(new Event("pywebviewready")));
  })();
</script>
""" % {"cabecalho": CABECALHO_PONTE}

# A página tem scripts e estilos dentro dela (o mapa vai embutido) e busca as imagens do mapa na internet
POLITICA = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://tile.openstreetmap.org https://api.maptiler.com; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
CABECALHOS_SEGURANCA = {
    "Content-Security-Policy": POLITICA,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cache-Control": "no-store",
}


class PreferenciasDoPainel:
    """O que o ServicoAlertas lê do merlin_config.json na Central, aqui vindo das variáveis de ambiente.
    As mudanças do administrador valem até o contêiner reiniciar."""

    def __init__(self, ambiente=None):
        ambiente = os.environ if ambiente is None else ambiente
        self.administrador = ambiente.get("PAINEL_PERFIL", "operador").strip().lower() == "administrador"
        self.alertas_intervalo = _intervalo(ambiente.get("ALERTAS_INTERVALO", ""))
        self.alertas_modo_teste = False  # o modo teste apaga o CSV: só o administrador liga, pela tela


def _intervalo(valor: str) -> int:
    valor = valor.strip()
    if not valor:
        return INTERVALO_PADRAO
    try:
        minutos = int(valor)
    except ValueError:
        minutos = -1
    if minutos not in INTERVALOS:
        logger.warning("[PAINEL] ALERTAS_INTERVALO=%r não é um dos intervalos %s: usando %d.", valor, INTERVALOS, INTERVALO_PADRAO)
        return INTERVALO_PADRAO
    return minutos


def montar_pagina() -> bytes:
    pagina = com_mapa(ARQ_ALERTAS.read_text(encoding="utf-8"))
    return pagina.replace("<head>", "<head>" + PONTE, 1).encode("utf-8")


def criar_servidor(host: str, porta: int, api: ApiAlertas, pagina: bytes | None = None) -> ThreadingHTTPServer:
    pagina = montar_pagina() if pagina is None else pagina

    class Pedido(BaseHTTPRequestHandler):
        server_version = "MerlinPainel"
        sys_version = ""  # não conta a versão do Python a quem pergunta

        def _responder(self, status: HTTPStatus, corpo: bytes, tipo: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            for nome, valor in CABECALHOS_SEGURANCA.items():
                self.send_header(nome, valor)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _json(self, status: HTTPStatus, dados) -> None:
            self._responder(status, json.dumps(dados, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            caminho = self.path.split("?", 1)[0]
            if caminho in ("/", "/index.html"):
                self._responder(HTTPStatus.OK, pagina, "text/html; charset=utf-8")
            elif caminho == "/healthz":
                self._json(HTTPStatus.OK, {"status": "ok"})
            else:
                self._json(HTTPStatus.NOT_FOUND, {"erro": "Não encontrado."})

        do_HEAD = do_GET

        def do_POST(self):
            caminho = self.path.split("?", 1)[0]
            nome = caminho.removeprefix("/api/") if caminho.startswith("/api/") else ""
            if nome not in METODOS:
                return self._json(HTTPStatus.NOT_FOUND, {"erro": "Não encontrado."})
            if self.headers.get(CABECALHO_PONTE) != "1" or not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json(HTTPStatus.FORBIDDEN, {"erro": "Pedido recusado."})
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                tamanho = -1
            if not 0 <= tamanho <= MAX_CORPO:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"erro": "Pedido grande demais."})
            try:
                argumentos = json.loads(self.rfile.read(tamanho) or b"[]")
            except (ValueError, UnicodeDecodeError):
                argumentos = None
            if not isinstance(argumentos, list) or len(argumentos) != METODOS[nome]:
                return self._json(HTTPStatus.BAD_REQUEST, {"erro": "Argumentos inválidos."})
            try:
                resposta = getattr(api, nome)(*argumentos)
            except Exception as erro:  # uma falha numa função não pode derrubar o painel
                logger.error("[PAINEL] Falha em %s: %s", nome, erro)
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"erro": "Falha interna."})
            self._json(HTTPStatus.OK, resposta)

        def log_message(self, formato, *args):
            logger.debug("[PAINEL] %s %s", self.address_string(), formato % args)

    servidor = ThreadingHTTPServer((host, porta), Pedido)
    servidor.daemon_threads = True
    return servidor


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("PAINEL_HOST", "127.0.0.1")
    porta = int(os.environ.get("PAINEL_PORTA", "8080"))
    preferencias = PreferenciasDoPainel()
    # abrir_pagina: no servidor não há navegador (a ponte abre o Google Maps no navegador de quem vê o painel)
    servico = ServicoAlertas(arquivo_ultima=ARQ_ULTIMA_CONSULTA, preferencias=preferencias, abrir_pagina=lambda url: None)
    servico.iniciar_agendamento()
    if os.environ.get("ALERTAS_BUSCAR_AO_INICIAR", "1").strip() == "1":
        threading.Thread(target=servico.buscar, kwargs={"automatica": True}, name="alertas-primeira-busca", daemon=True).start()
    servidor = criar_servidor(host, porta, ApiAlertas(servico))

    def encerrar(*_):  # docker stop manda SIGTERM: fecha sem esperar o tempo limite
        logger.info("[PAINEL] Encerrando.")
        servico.parar_agendamento()
        threading.Thread(target=servidor.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, encerrar)
    signal.signal(signal.SIGINT, encerrar)
    logger.info("[PAINEL] Painel de alertas em http://%s:%d (perfil %s, busca automática %s).", host, porta,
                "administrador" if preferencias.administrador else "operador",
                f"a cada {preferencias.alertas_intervalo} min" if preferencias.alertas_intervalo else "desligada")
    servidor.serve_forever()
    servidor.server_close()
