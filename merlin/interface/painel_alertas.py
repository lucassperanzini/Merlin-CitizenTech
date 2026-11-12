"""Aba Alertas da Central: busca os focos de calor pelo robô FIRMS Monitor e mostra na tela."""
import json
import logging
import math
import os
import re
import threading

from merlin.alertas import focos
from merlin.config import ARQ_ENV

logger = logging.getLogger(__name__)


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
        with urllib.request.urlopen(pedido, timeout=8):
            return True
    except urllib.error.HTTPError as erro:
        return False if erro.code in (401, 403) else None
    except OSError:
        return None


class ServicoAlertas:
    def __init__(self, consultar=focos.consultar, abrir_pagina=None, arquivo_env=ARQ_ENV, conferir_chave=None,
                 arquivo_ultima=None):
        self._consultar = consultar
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
            chave = (dotenv_values(self._arquivo_env).get("MAPTILER_KEY") or "").strip()
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

    def buscar(self) -> dict:
        if not self._ocupado.acquire(blocking=False):
            return {"erro": "Já estou consultando a NASA. Espere terminar."}
        try:
            resultado = self._consultar()
            self._guardar(resultado)
            return resultado
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

    def buscar(self):
        return self._servico.buscar()

    def ultima(self):
        return self._servico.ultima()

    def fundos(self):
        return self._servico.fundos()

    def escolher_fundo(self, nome):
        return self._servico.escolher_fundo(nome)

    def abrir_mapa(self, latitude, longitude):
        return self._servico.abrir_mapa(latitude, longitude)
