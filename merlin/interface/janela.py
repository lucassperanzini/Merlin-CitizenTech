"""Janela do assistente: mostra e esconde, e repassa à página tudo o que chega pelo canal.
A aparência (olho do Merlin ou esfera do Jarvis) segue a personalidade escolhida.
Em espera, a janela fica numa bolinha no canto da tela, que cresce até o centro quando o assistente é chamado."""
import json
import logging
import time

import webview

from merlin.config import ARQ_ESFERA, ARQ_JANELA, ARQ_OLHO, ARQ_THREE, JANELA_ALTURA, JANELA_LARGURA
from merlin.interface.eventos import TipoEvento
from merlin.interface.moldura import Moldura

logger = logging.getLogger(__name__)

INTERVALO_NIVEL = 0.066  # atualiza o volume cerca de 15 vezes por segundo
QUEDA_NIVEL = 0.8  # queda suave, para as ondas não piscarem entre as sílabas
NIVEL_MINIMO = 0.02
ESPERA_EVENTO = 0.05


def dados_da_personalidade(preferencias) -> dict:
    """O que a página precisa para se ajustar à personalidade escolhida."""
    personalidade = preferencias.personalidade
    return {"id": personalidade.id, "nome": personalidade.nome, "visual": personalidade.visual}


class ApiJanela:
    """Funções que a página pode chamar. O pywebview expõe tudo o que é público, por isso os atributos são privados."""

    def __init__(self, configuracoes, raciocinio, sessao):
        self._configuracoes = configuracoes
        self._raciocinio = raciocinio
        self._sessao = sessao

    def abrir_configuracoes(self):
        self._configuracoes.abrir()

    def abrir_raciocinio(self):
        self._raciocinio.abrir()

    def ativar(self):
        """Clique na bolinha do canto: o mesmo que chamar pelo nome."""
        self._sessao.ativar()


class JanelaMerlin:
    def __init__(self, estado, canal, sessao, preferencias, configuracoes, raciocinio):
        self._estado = estado
        self._canal = canal
        self._sessao = sessao
        self._preferencias = preferencias
        self._configuracoes = configuracoes
        self._raciocinio = raciocinio
        self._visivel = False  # janela cheia, ativa: só nela chegam volume, estado e legenda
        self._compacta = False  # bolinha no canto, em espera
        self._moldura = None  # criada quando a janela nativa existe
        self._nivel = 0.0
        self._ultimo_nivel = 0.0

        x, y, largura, altura = self._calcular_posicao()
        self.janela = webview.create_window(
            preferencias.personalidade.nome, html=self._montar_pagina(),
            js_api=ApiJanela(configuracoes, raciocinio, sessao),
            width=largura, height=altura, x=x, y=y,
            resizable=False, on_top=True, hidden=True, background_color="#05070C",
            min_size=(100, 100),  # o padrão (200 de largura) não deixaria a bolinha do canto ficar redonda
        )
        self.janela.events.closing += self._ao_fechar

    def executar(self) -> None:
        """Bloqueia a thread principal até a janela ser destruída."""
        webview.start(self._loop, gui="edgechromium")

    def _montar_pagina(self) -> str:
        """Tudo vai embutido na página: o assistente funciona sem internet."""
        dados = {"personalidade": dados_da_personalidade(self._preferencias)}
        scripts = "".join(f"<script>{arquivo.read_text(encoding='utf-8')}</script>" for arquivo in (ARQ_THREE, ARQ_ESFERA))
        pagina = ARQ_JANELA.read_text(encoding="utf-8")
        return (pagina.replace("<!--OLHO-->", ARQ_OLHO.read_text(encoding="utf-8"))
                .replace("<!--SCRIPTS-->", scripts)
                .replace("/*DADOS*/", json.dumps(dados, ensure_ascii=False)))

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
            self._mostrar()
        elif tipo is TipoEvento.ESCONDER:
            self._esconder()
        elif tipo is TipoEvento.PERSONALIDADE:
            self._chamar_pagina("definirPersonalidade", dados_da_personalidade(self._preferencias))
            self.janela.set_title(self._preferencias.personalidade.nome)
            if self._compacta:
                self._chamar_pagina("aoCompactar")  # o visual novo também entra no modo da bolinha
        elif tipo is TipoEvento.ABRIR_CONFIGURACOES:
            self._configuracoes.abrir()
        elif tipo is TipoEvento.ESTADO and self._visivel:
            self._chamar_pagina("definirEstado", dado.value)
        elif tipo is TipoEvento.LEGENDA and self._visivel:
            self._chamar_pagina("definirLegenda", dado)
        elif tipo is TipoEvento.ENVELOPE_FALA and self._visivel:
            self._chamar_pagina("falarComVolume", dado["volumes"], dado["passo"])

    def _mostrar(self):
        self._visivel = True
        self._nivel = 0.0
        self._chamar_pagina("aoMostrar")
        if self._compacta and self._moldura:
            self._compacta = False
            m = self._moldura
            m.animar(m.canto(), m.conteudo, 1.0, 0.0)  # cresce até o centro sem a barra de título...
            m.com_moldura()
            m.posicionar(m.cheia)  # ...que volta em volta do conteúdo, sem mexer nele
        self.janela.show()

    def _esconder(self):
        self._visivel = False
        if self._compacta:
            return  # já está no canto
        if self._moldura:
            self._chamar_pagina("aoCompactar")
            m = self._moldura
            m.sem_moldura()
            m.posicionar(m.conteudo)  # tira a barra de título sem mexer no conteúdo...
            m.animar(m.conteudo, m.canto(), 0.0, 1.0)  # ...e encolhe até o canto
            self._compacta = True
        else:  # sem controle da moldura, a janela simplesmente some
            self._chamar_pagina("aoEsconder")  # para a animação, liberando a placa de vídeo
            self.janela.hide()

    def _ficar_em_espera(self):
        """Bolinha no canto sem animação, ao abrir o programa."""
        if self._moldura and not self._compacta:
            self._chamar_pagina("aoCompactar")
            self._moldura.sem_moldura()
            self._moldura.posicionar(self._moldura.canto(), 1.0)
            self._compacta = True
            self.janela.show()

    def _criar_moldura(self):
        try:
            self._moldura = Moldura(self.janela.native.Handle.ToInt32())
        except Exception as erro:  # sem ela, a janela só some em espera
            logger.warning("[JANELA] Não consegui controlar a moldura da janela: %s", erro)

    def _loop(self):
        self.janela.events.loaded.wait()
        self._criar_moldura()
        if not self._estado.ativo.is_set():
            self._ficar_em_espera()
        while not self._estado.encerrando.is_set():
            tipo, dado = self._canal.proximo(ESPERA_EVENTO)
            try:
                self._atualizar_nivel()
                self._tratar_evento(tipo, dado)
            except Exception as erro:
                logger.error("[JANELA] %s", erro)
        self._configuracoes.fechar()  # se elas ficassem abertas, o programa não terminaria
        self._raciocinio.fechar()
        self.janela.destroy()
