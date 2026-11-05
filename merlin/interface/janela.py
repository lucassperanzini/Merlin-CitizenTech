"""Janela com o olho: mostra e esconde, e repassa à página tudo o que chega pelo canal."""
import json
import logging
import threading
import time

import webview

from merlin.config import ARQ_JANELA, ARQ_OLHO, JANELA_ALTURA, JANELA_LARGURA, NOME, VOZES
from merlin.interface.eventos import TipoEvento

logger = logging.getLogger(__name__)

INTERVALO_NIVEL = 0.066  # atualiza o volume cerca de 15 vezes por segundo
QUEDA_NIVEL = 0.8  # queda suave, para as ondas não piscarem entre as sílabas
NIVEL_MINIMO = 0.02
ESPERA_EVENTO = 0.05


class ApiJanela:
    """Funções que a página pode chamar. O pywebview expõe tudo o que é público, por isso os atributos são privados."""

    def __init__(self, preferencias, locutor):
        self._preferencias = preferencias
        self._locutor = locutor

    def trocar_voz(self, rotulo):
        if rotulo not in VOZES:
            return
        self._preferencias.voz = VOZES[rotulo]
        threading.Thread(target=self._locutor.falar, args=("Olá, esta é a minha nova voz.",), daemon=True).start()


class JanelaMerlin:
    def __init__(self, estado, canal, sessao, preferencias, locutor):
        self._estado = estado
        self._canal = canal
        self._sessao = sessao
        self._visivel = False
        self._nivel = 0.0
        self._ultimo_nivel = 0.0

        x, y, largura, altura = self._calcular_posicao()
        self.janela = webview.create_window(
            NOME, html=self._montar_pagina(preferencias.voz), js_api=ApiJanela(preferencias, locutor),
            width=largura, height=altura, x=x, y=y,
            resizable=False, on_top=True, hidden=True, background_color="#05070C",
        )
        self.janela.events.closing += self._ao_fechar

    def executar(self) -> None:
        """Bloqueia a thread principal até a janela ser destruída."""
        webview.start(self._loop, gui="edgechromium")

    @staticmethod
    def _montar_pagina(voz_atual) -> str:
        rotulo_atual = next((rotulo for rotulo, voz in VOZES.items() if voz == voz_atual), list(VOZES)[0])
        dados = json.dumps({"vozes": list(VOZES), "atual": rotulo_atual}, ensure_ascii=False)
        pagina = ARQ_JANELA.read_text(encoding="utf-8")
        return pagina.replace("<!--OLHO-->", ARQ_OLHO.read_text(encoding="utf-8")).replace("/*DADOS*/", dados)

    @staticmethod
    def _calcular_posicao():
        # A posição vai na criação: janela.move() exibiria a janela escondida
        tela = webview.screens[0]
        largura = min(JANELA_LARGURA, int(tela.width * 0.9))
        altura = min(JANELA_ALTURA, int(tela.height * 0.88))
        return tela.x + (tela.width - largura) // 2, tela.y + (tela.height - altura) // 2, largura, altura

    def _ao_fechar(self):
        # Fechar no X equivale a desativar (o programa segue escutando)
        if self._estado.encerrando.is_set():
            return True
        self._sessao.desativar()
        return False

    def _chamar_pagina(self, funcao, *args):
        self.janela.evaluate_js(f"{funcao}({', '.join(json.dumps(a) for a in args)})")

    def _atualizar_nivel(self):
        agora = time.time()
        if not self._visivel or agora - self._ultimo_nivel < INTERVALO_NIVEL:
            return
        self._ultimo_nivel = agora
        novo = max(self._estado.consumir_nivel(), self._nivel * QUEDA_NIVEL)
        if novo < NIVEL_MINIMO:
            novo = 0.0
        if novo != self._nivel:
            self._nivel = novo
            self._chamar_pagina("definirNivel", round(novo, 2))

    def _tratar_evento(self, tipo, dado):
        if tipo is TipoEvento.MOSTRAR:
            self._visivel = True
            self._nivel = 0.0
            self._chamar_pagina("aoMostrar")
            self.janela.show()
        elif tipo is TipoEvento.ESCONDER:
            self._visivel = False
            self.janela.hide()
        elif tipo is TipoEvento.ESTADO and self._visivel:
            self._chamar_pagina("definirEstado", dado.value)
        elif tipo is TipoEvento.LEGENDA and self._visivel:
            self._chamar_pagina("definirLegenda", dado)

    def _loop(self):
        self.janela.events.loaded.wait()
        while not self._estado.encerrando.is_set():
            tipo, dado = self._canal.proximo(ESPERA_EVENTO)
            try:
                self._atualizar_nivel()
                self._tratar_evento(tipo, dado)
            except Exception as erro:
                logger.error("[JANELA] %s", erro)
        self.janela.destroy()
