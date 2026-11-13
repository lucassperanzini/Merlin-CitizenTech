"""Aba Alertas da Central: busca os focos de calor pelo robô FIRMS Monitor e mostra na tela."""
import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime

from merlin.alertas import focos
from merlin.config import ARQ_ENV
from merlin.interface.perfil import AVISO_SO_ADMINISTRADOR

logger = logging.getLogger(__name__)

# De quantos em quantos minutos a busca automática pode rodar (0: desligada). Os dados da NASA (NRT) mudam
# a cada passagem de satélite, então menos de 15 minutos só repetiria a mesma consulta.
INTERVALOS = (0,1, 15, 30, 60, 180, 360, 720, 1440)


_CHAVE_VALIDA = re.compile(r"^[A-Za-z0-9_-]{8,128}$")  # vai para dentro de um endereço: nada além disso
_BLOCO_DE_TESTE = "https://api.maptiler.com/maps/streets-v2/256/0/0/0.png?key={}"


def _conferir_chave_maptiler(chave: str) -> bool | None:
    """True: aceita. False: recusada. None: sem resposta (sem internet), para tentar de novo depois.
    A recusa vem como imagem com status 403, que o navegador mostra como se fosse um bloco normal:
    por isso a conferência é feita aqui, onde o status aparece."""
    import urllib.error
    import urllib.request
    pedido = urllib.request.Request(_BLOCO_DE_TESTE.format(chave), headers={"User-Agent": "Merlin"})
    try:
        # O endereço é fixo (https, api.maptiler.com) e a chave só chega aqui depois de passar por _CHAVE_VALIDA:
        # não dá para trocar o servidor nem o esquema (file://, por exemplo)
        with urllib.request.urlopen(pedido, timeout=8):  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            return True
    except urllib.error.HTTPError as erro:
        return False if erro.code in (401, 403) else None
    except OSError:
        return None


class ServicoAlertas:
    def __init__(self, consultar=focos.consultar, abrir_pagina=None, arquivo_env=ARQ_ENV, conferir_chave=None,
                 arquivo_ultima=None, preferencias=None, segundos_por_minuto=60, ao_alertar=None, ao_ver=None):
        self._consultar = consultar
        self._ao_alertar = ao_alertar  # recebe cada busca bem-sucedida: avisa se chegou foco em alerta
        self._ao_ver = ao_ver  # a aba Alertas apareceu na tela: o alarme para
        self._preferencias = preferencias  # intervalo e modo teste (None: sem busca automática, como nos testes)
        self._segundos_por_minuto = segundos_por_minuto  # só os testes encurtam o minuto
        self._mais_recente = {}  # a última busca, guardada ou não: a página aberta a mostra quando ela chega sozinha
        self._versao = 0  # sobe a cada busca bem-sucedida, para a página saber que há algo novo
        self._proxima = None  # quando roda a próxima busca automática (time.time()), ou None
        self._acordar = threading.Event()  # o intervalo mudou: o agendador recomeça a contar
        self._parar = threading.Event()
        self._arquivo_ultima = arquivo_ultima  # onde fica a última consulta (None: não guarda, como nos testes)
        self._abrir_pagina = abrir_pagina
        self._arquivo_env = arquivo_env
        self._conferir_chave = conferir_chave or _conferir_chave_maptiler
        self._chaves_conferidas = {}  # chave -> aceita? (uma conferência por chave enquanto o Merlin estiver aberto)
        self._fundo_escolhido = ""  # a página não pode gravar no navegador: a escolha fica aqui
        self._ocupado = threading.Lock()  # dois cliques seguidos não podem rodar o robô duas vezes ao mesmo tempo

    def fundos(self) -> dict:
        """A chave do MapTiler, do .env, já conferida. Vazia se não houver ou se for recusada: aí o mapa usa o
        OpenStreetMap, que não pede chave. A página precisa dela porque é ela que pede as imagens do mapa."""
        try:
            from dotenv import dotenv_values
            # Sem o arquivo (no contêiner, por exemplo), a chave vem das variáveis de ambiente
            valores = dotenv_values(self._arquivo_env) if os.path.isfile(self._arquivo_env) else os.environ
            chave = (valores.get("MAPTILER_KEY") or "").strip()
        except (ImportError, OSError):
            chave = ""
        if not _CHAVE_VALIDA.match(chave):
            return {"maptiler": "", "escolhido": self._fundo_escolhido, "aviso": ""}
        if chave not in self._chaves_conferidas or self._chaves_conferidas[chave] is None:
            self._chaves_conferidas[chave] = self._conferir_chave(chave)
        if self._chaves_conferidas[chave] is False:
            return {"maptiler": "", "escolhido": self._fundo_escolhido,
                    "aviso": "O MapTiler recusou a chave MAPTILER_KEY do .env: usando o OpenStreetMap."}
        return {"maptiler": chave, "escolhido": self._fundo_escolhido, "aviso": ""}

    def escolher_fundo(self, nome) -> dict:
        self._fundo_escolhido = str(nome or "")[:30]
        return {}

    # --- Busca automática e modo teste (só o administrador muda)
    @property
    def _administrador(self) -> bool:
        return self._preferencias is not None and self._preferencias.administrador

    @property
    def modo_teste(self) -> bool:
        return self._preferencias is not None and self._preferencias.alertas_modo_teste

    @property
    def intervalo(self) -> int:
        return self._preferencias.alertas_intervalo if self._preferencias is not None else 0

    def estado_automatico(self) -> dict:
        return {
            "administrador": self._administrador,
            "intervalos": list(INTERVALOS),
            "intervalo": self.intervalo,
            "modo_teste": self.modo_teste,
            "proxima": datetime.fromtimestamp(self._proxima).strftime("%H:%M") if self._proxima else "",
            "versao": self._versao,
        }

    def configurar(self, intervalo, modo_teste) -> dict:
        if not self._administrador:
            logger.warning("[PERFIL] Pedido recusado no perfil operador: configurar a busca automática.")
            return {"erro": AVISO_SO_ADMINISTRADOR}
        try:
            minutos = int(intervalo)
        except (TypeError, ValueError):
            minutos = -1
        if minutos not in INTERVALOS:
            return {"erro": "Escolha um dos intervalos da lista."}
        if minutos != self.intervalo:
            self._preferencias.alertas_intervalo = minutos
            logger.info("[ALERTAS] Busca automática: %s.", f"a cada {minutos} min" if minutos else "desligada")
        if bool(modo_teste) != self.modo_teste:
            self._preferencias.alertas_modo_teste = bool(modo_teste)
            logger.info("[ALERTAS] Modo teste %s.", "ligado" if modo_teste else "desligado")
        self._acordar.set()  # recomeça a contar com o intervalo novo
        self._esperar_agendador()
        return self.estado_automatico()

    def _esperar_agendador(self, limite=0.5) -> None:
        """Dá ao agendador um instante para recalcular a próxima busca, para a tela já mostrar o horário certo."""
        fim = time.monotonic() + limite
        while self._acordar.is_set() and self._rodando and time.monotonic() < fim:
            time.sleep(0.01)

    _rodando = False

    def iniciar_agendamento(self) -> None:
        if self._rodando or self._preferencias is None:
            return
        self._rodando = True
        threading.Thread(target=self._agendar, name="alertas-agendamento", daemon=True).start()

    def parar_agendamento(self) -> None:
        self._parar.set()
        self._acordar.set()

    def _agendar(self) -> None:
        while not self._parar.is_set():
            minutos = self.intervalo
            espera = minutos * self._segundos_por_minuto if minutos else None
            self._proxima = time.time() + espera if espera else None
            self._acordar.clear()
            if self._acordar.wait(espera):  # o intervalo mudou (ou o Merlin está fechando): recomeça
                continue
            logger.info("[ALERTAS] Busca automática (a cada %d min).", minutos)
            resultado = self.buscar(automatica=True)
            if "erro" in resultado:
                logger.warning("[ALERTAS] A busca automática falhou: %s", resultado["erro"])
        self._proxima = None

    def vistos(self) -> dict:
        """A aba Alertas apareceu na tela: quem tinha de ver os alertas viu (o alarme para)."""
        if self._ao_ver:
            try:
                self._ao_ver()
            except Exception as erro:
                logger.error("[ALERTAS] Não consegui desligar o alarme: %s", erro)
        return {}

    def mais_recente(self) -> dict:
        """A última busca feita enquanto o Merlin está aberto (no modo teste também), ou {}."""
        return self._mais_recente

    def buscar(self, automatica=False) -> dict:
        if not self._ocupado.acquire(blocking=False):
            return {"erro": "Já estou consultando a NASA. Espere terminar."}
        try:
            teste = self.modo_teste
            if teste:
                # Modo teste: cada busca começa do zero (sem o CSV do robô e sem a última consulta), então todo
                # foco do nível de alerta volta como novo e o Merlin avisa de novo
                self._apagar_ultima()
                consulta = self._consultar(do_zero=True)
            else:
                consulta = self._consultar()
            self._guardar(consulta)  # sem as marcas abaixo: elas só valem para a tela aberta agora
            if "erro" in consulta:
                return consulta
            self._versao += 1
            self._mais_recente = {**consulta, "teste": teste, "automatica": bool(automatica), "versao": self._versao}
            if self._ao_alertar:
                try:
                    self._ao_alertar(self._mais_recente)
                except Exception as erro:  # o aviso falhar não pode estragar a busca
                    logger.error("[ALERTAS] Não consegui avisar: %s", erro)
            return self._mais_recente
        except focos.RoboAusente:
            return {"erro": "O robô FIRMS Monitor não está instalado no Python do Merlin."}
        except focos.ConsultaFalhou as erro:
            return {"erro": str(erro)}
        except Exception as erro:  # o robô é de outro projeto: uma falha dele não pode derrubar a Central
            logger.error("[ALERTAS] Falha ao consultar: %s", erro)
            return {"erro": f"O robô falhou: {erro}"}
        finally:
            self._ocupado.release()

    def _guardar(self, resultado: dict) -> None:
        """Grava a consulta para ela voltar ao mapa quando a aba for aberta de novo. Uma falha aqui não estraga a busca."""
        if not self._arquivo_ultima or "erro" in resultado:
            return
        destino = self._arquivo_ultima
        provisorio = destino.with_suffix(".tmp")
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            provisorio.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
            os.replace(provisorio, destino)  # troca de uma vez: um arquivo pela metade nunca fica no lugar do bom
        except (OSError, TypeError, ValueError) as erro:
            logger.warning("[ALERTAS] Não consegui guardar a consulta: %s", erro)

    def _apagar_ultima(self) -> None:
        if not self._arquivo_ultima:
            return
        try:
            self._arquivo_ultima.unlink(missing_ok=True)
        except OSError as erro:
            logger.warning("[ALERTAS] Modo teste: não consegui apagar a última consulta: %s", erro)

    def ultima(self) -> dict:
        """A última consulta guardada, ou {} se não houver (ou se o arquivo estiver estragado)."""
        if not self._arquivo_ultima:
            return {}
        try:
            dados = json.loads(self._arquivo_ultima.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as erro:
            logger.warning("[ALERTAS] Não consegui ler a última consulta: %s", erro)
            return {}
        return dados if isinstance(dados, dict) and isinstance(dados.get("focos"), list) else {}

    def abrir_mapa(self, latitude, longitude) -> dict:
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            return {"erro": "Coordenadas inválidas."}
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return {"erro": "Coordenadas inválidas."}
        abrir = self._abrir_pagina
        if abrir is None:
            import webbrowser
            abrir = webbrowser.open
        abrir(f"https://www.google.com/maps?q={lat},{lon}")
        return {}


class ApiAlertas:
    """Funções que a página pode chamar (atributos privados: o pywebview expõe os públicos)."""

    def __init__(self, servico):
        self._servico = servico

    def ultima(self):
        return self._servico.ultima()

    def mais_recente(self):
        return self._servico.mais_recente()

    def vistos(self):
        return self._servico.vistos()

    def estado_automatico(self):
        return self._servico.estado_automatico()

    def configurar(self, intervalo, modo_teste):
        return self._servico.configurar(intervalo, modo_teste)

    def fundos(self):
        return self._servico.fundos()

    def escolher_fundo(self, nome):
        return self._servico.escolher_fundo(nome)

    def abrir_mapa(self, latitude, longitude):
        return self._servico.abrir_mapa(latitude, longitude)
