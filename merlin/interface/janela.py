"""Janela do assistente: mostra e esconde, e repassa à página tudo o que chega pelo canal.
A aparência (olho do Merlin ou esfera do Jarvis) segue a personalidade escolhida.
Em espera, a janela fica numa bolinha no canto da tela, que cresce até o centro quando o assistente é chamado."""
import json
import logging
import threading
import time

import webview

from merlin.config import ARQ_ESFERA, ARQ_JANELA, ARQ_OLHO, ARQ_RACIOCINIO, ARQ_THREE, JANELA_ALTURA, JANELA_LARGURA
from merlin.ia.cliente import listar_modelos
from merlin.interface.central import quadro
from merlin.interface.eventos import TipoEvento
from merlin.interface.moldura import Moldura, desenho_compacto
from merlin.personalidades import PERSONALIDADES

logger = logging.getLogger(__name__)

INTERVALO_NIVEL = 0.066  # atualiza o volume cerca de 15 vezes por segundo
QUEDA_NIVEL = 0.8  # queda suave, para as ondas não piscarem entre as sílabas
NIVEL_MINIMO = 0.02
ESPERA_EVENTO = 0.05
INTERVALO_CHECAR_IA = 20  # segundos entre as verificações do Ollama (o anel da bolinha avisa se ele cair)


def dados_da_personalidade(preferencias) -> dict:
    """O que a página precisa para se ajustar à personalidade escolhida."""
    personalidade = preferencias.personalidade
    return {"id": personalidade.id, "nome": personalidade.nome, "visual": personalidade.visual, "cor": personalidade.cor}


def com_aba(preferencias, tem_raciocinio: bool) -> bool:
    """A aba do raciocínio aparece no cartão só no modo debug (botão da órbita)."""
    return tem_raciocinio and preferencias.modo_debug


class ApiJanela:
    """Funções que a página pode chamar. O pywebview expõe tudo o que é público, por isso os atributos são privados."""

    def __init__(self, central, sessao, estado=None, mostrar_botoes=None, abrir_menu=None, trocar_assistente=None,
                 raciocinio=None, painel=None, debug=None, balao=None):
        self._balao = balao
        self.raciocinio = raciocinio  # a API da página do raciocínio, no painel à esquerda do cartão
        self._painel = painel
        self._debug = debug
        self._estado = estado
        self._mostrar_botoes = mostrar_botoes
        self._abrir_menu = abrir_menu
        self._trocar_assistente = trocar_assistente
        self._central = central
        self._sessao = sessao

    def abrir_configuracoes(self):
        self._central.abrir_aba("assistente")

    def alternar_microfone(self) -> bool:
        """Botão de mudo: liga ou desliga a escuta. Devolve True se o microfone ficou desligado."""
        mudo = self._estado.microfone_desligado
        if mudo.is_set():
            mudo.clear()
            logger.info("[INFO] Microfone ligado.")
        else:
            mudo.set()
            logger.info("[INFO] Microfone no mudo.")
        return mudo.is_set()

    def ativar(self):
        """Clique na bolinha do canto: o mesmo que chamar pelo nome."""
        self._sessao.ativar()

    def botoes_compactos(self, visiveis):
        """Mouse chegou perto da bolinha (ou saiu): os botões em volta entram (ou saem) do recorte da janela."""
        if self._mostrar_botoes:
            self._mostrar_botoes(bool(visiveis))

    def balao_compacto(self, caixa=None):
        """O balão do modo discreto apareceu (x, y, largura, altura em pontos) ou sumiu (nada): ele entra no
        recorte da janela só enquanto está na tela."""
        if self._balao:
            self._balao(tuple(float(v) for v in caixa) if caixa else None)

    def menu_assistentes(self, aberto, altura=0):
        """Clique no nome da bolinha: a lista de assistentes abre embaixo do nome, com a altura pedida (em pontos)."""
        if self._abrir_menu:
            self._abrir_menu(bool(aberto), int(altura or 0))

    def listar_assistentes(self):
        return [{"id": p.id, "nome": p.nome} for p in PERSONALIDADES.values()]

    def trocar_assistente(self, identificador):
        """Escolha na lista do nome da bolinha: a mesma troca da Central (com a apresentação falada)."""
        if self._trocar_assistente:
            self._trocar_assistente(identificador)

    def alternar_debug(self) -> bool:
        """Botão da órbita: liga ou desliga o modo debug (a aba do raciocínio no cartão). Devolve o estado novo."""
        return self._debug() if self._debug else False

    def painel_raciocinio(self, aberto):
        """Aba da borda esquerda do cartão: abre (ou fecha) o painel do raciocínio ao lado dele."""
        if self._painel:
            self._painel(bool(aberto))

    def decidir_rascunho(self, acao):
        """Botões do texto escrito pela IA. Devolve a frase a mostrar no lugar deles."""
        pendencia = self._sessao.pegar_pendencia()
        if self._estado:
            self._estado.registrar_atividade()
        if pendencia is None:
            return "O prazo acabou. Peça de novo."
        try:
            if acao == "descartar":
                return ""
            if acao == "copiar" and pendencia.copiar:
                pendencia.copiar()
                return "Copiado para a área de transferência."
            fala = pendencia.ao_confirmar().fala
        except Exception as erro:
            logger.error("[JANELA] Não consegui concluir o texto: %s", erro)
            return "Não consegui concluir."
        return fala[:1].upper() + fala[1:] + "."

    def recolher(self):
        """Botão de recolher do cartão: o mesmo que dispensar o assistente por voz."""
        self._sessao.desativar()


class JanelaMerlin:
    def __init__(self, estado, canal, sessao, preferencias, central, trocar_assistente=None, raciocinio=None):
        self._estado = estado
        self._canal = canal
        self._sessao = sessao
        self._preferencias = preferencias
        self._central = central
        self._visivel = False  # janela cheia, ativa: só nela chegam volume, estado e legenda
        self._compacta = False  # bolinha no canto, em espera
        self._moldura = None  # criada quando a janela nativa existe
        self._nivel = 0.0
        self._ultimo_nivel = 0.0
        self._botoes_visiveis = False  # na bolinha, os botões em volta só aparecem com o mouse por perto
        self._menu_aberto = False  # a lista de assistentes, aberta com um clique no nome da bolinha
        self._altura_menu = 0  # em pontos: quanto a janela cresce, embaixo do nome, para a lista caber
        self._painel_aberto = False  # o raciocínio ao lado do cartão (aba da borda esquerda)
        self._balao = None  # o balão do modo discreto, quando está na tela: (x, y, largura, altura) em pontos
        self._tem_raciocinio = raciocinio is not None
        self._trava_forma = threading.Lock()  # a animação e o mouse mexem no recorte da janela, de threads diferentes
        self._ia_fora = False
        self._ultima_checagem_ia = 0.0

        x, y, largura, altura = self._calcular_posicao()
        self.janela = webview.create_window(
            preferencias.personalidade.nome, html=self._montar_pagina(),
            js_api=ApiJanela(central, sessao, estado, self._mostrar_botoes_compactos, self._abrir_menu_compacto,
                             trocar_assistente, raciocinio, self._abrir_painel, self._alternar_debug,
                             self._mostrar_balao),
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
        dados = {"personalidade": dados_da_personalidade(self._preferencias), "cartao": JANELA_LARGURA,
                 "debug": com_aba(self._preferencias, self._tem_raciocinio)}
        scripts = "".join(f"<script>{arquivo.read_text(encoding='utf-8')}</script>" for arquivo in (ARQ_THREE, ARQ_ESFERA))
        pagina = ARQ_JANELA.read_text(encoding="utf-8")
        return (pagina.replace("<!--OLHO-->", ARQ_OLHO.read_text(encoding="utf-8"))
                .replace("<!--SCRIPTS-->", scripts)
                .replace("<!--QUADRO:raciocinio-->", quadro("raciocinio", ARQ_RACIOCINIO) if self._tem_raciocinio else "")
                .replace("/*DADOS*/", json.dumps(dados, ensure_ascii=False)))

    @staticmethod
    def _calcular_posicao():
        # A posição vai na criação: janela.move() exibiria a janela escondida. Com o controle da moldura, o cartão
        # é reposicionado pela área livre da tela; esta posição só vale se esse controle falhar.
        tela = webview.screens[0]
        largura = min(JANELA_LARGURA, int(tela.width * 0.9))
        altura = min(JANELA_ALTURA, int(tela.height * 0.8))
        return tela.x + tela.width - largura - 24, tela.y + tela.height - altura - 72, largura, altura

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
                self._compactar_pagina()  # o visual novo também entra no modo da bolinha
        elif tipo is TipoEvento.ABRIR_CONFIGURACOES:
            self._central.abrir_aba("assistente")
        elif tipo is TipoEvento.ESTADO and self._visivel:
            self._chamar_pagina("definirEstado", dado.value)
        elif tipo is TipoEvento.ESTADO and self._compacta:  # modo discreto: a bolinha pensa e fala sem abrir
            self._chamar_pagina("definirEstadoBolinha", dado.value)
        elif tipo is TipoEvento.RASCUNHO and self._visivel:
            self._chamar_pagina("mostrarRascunho", dado)
        elif tipo is TipoEvento.AVISO and self._compacta:
            self._chamar_pagina("mostrarBalao", dado)
        elif tipo is TipoEvento.LEGENDA and self._visivel:
            self._chamar_pagina("definirLegenda", dado)
        elif tipo is TipoEvento.RESPOSTA and self._visivel:
            self._chamar_pagina("comecarResposta")
        elif tipo is TipoEvento.TRECHO_FALADO and self._visivel:
            self._chamar_pagina("mostrarTrecho", dado["texto"], dado["duracao"])
        elif tipo is TipoEvento.FALA_INTERROMPIDA and self._visivel:
            self._chamar_pagina("pararTexto")
        elif tipo is TipoEvento.ENVELOPE_FALA and self._visivel:
            self._chamar_pagina("falarComVolume", dado["volumes"], dado["passo"])

    def _mostrar(self):
        self._visivel = True
        self._nivel = 0.0
        self._chamar_pagina("aoMostrar")
        self._chamar_pagina("esconderBalao")
        with self._trava_forma:
            self._botoes_visiveis = self._menu_aberto = self._painel_aberto = False
            self._balao = None
            if self._compacta and self._moldura:
                self._compacta = False
                m = self._moldura
                cartao, _ = m.cartao(JANELA_LARGURA, JANELA_ALTURA)
                aba = com_aba(self._preferencias, self._tem_raciocinio)
                m.animar_cartao(m.canto(), cartao, aba, abrindo=True)  # a bolinha vira o cartão
                m.posicionar_cartao(cartao, 0, aba)  # a forma final: o cartão e, no modo debug, a aba de fora
        self.janela.show()

    def _esconder(self):
        self._visivel = False
        if self._compacta:
            self._chamar_pagina("definirEstadoBolinha", "espera")  # depois de um pedido no modo discreto
            return  # já está no canto
        if self._moldura:
            self._compactar_pagina()
            with self._trava_forma:
                m = self._moldura
                cartao, _ = m.cartao(JANELA_LARGURA, JANELA_ALTURA)
                aba = com_aba(self._preferencias, self._tem_raciocinio)
                if self._painel_aberto:  # o painel do raciocínio fecha antes, e o cartão encolhe sozinho
                    self._painel_aberto = False
                    m.animar_painel(cartao, 1, 0, aba)
                m.animar_cartao(m.canto(), cartao, aba, abrindo=False)  # volta para a bolinha
                self._compacta = True
                self._aplicar_forma_compacta()
        else:  # sem controle da moldura, a janela simplesmente some
            self._chamar_pagina("aoEsconder")  # para a animação, liberando a placa de vídeo
            self.janela.hide()

    def _ficar_em_espera(self):
        """Bolinha no canto sem animação, ao abrir o programa."""
        if self._moldura and not self._compacta:
            self._compactar_pagina()
            with self._trava_forma:
                self._compacta = True
                self._aplicar_forma_compacta()
            self.janela.show()

    def _mostrar_botoes_compactos(self, visiveis: bool):
        with self._trava_forma:
            self._botoes_visiveis = visiveis
            self._aplicar_forma_compacta()

    def _abrir_painel(self, aberto: bool):
        with self._trava_forma:
            if self._compacta or not self._moldura:
                return
            aba = com_aba(self._preferencias, self._tem_raciocinio)
            aberto = aberto and aba
            if aberto == self._painel_aberto:
                return
            cartao, _ = self._moldura.cartao(JANELA_LARGURA, JANELA_ALTURA)
            self._moldura.animar_painel(cartao, int(self._painel_aberto), int(aberto), aba)
            self._painel_aberto = aberto

    def _alternar_debug(self) -> bool:
        self._preferencias.modo_debug = not self._preferencias.modo_debug
        ligado = com_aba(self._preferencias, self._tem_raciocinio)
        logger.info("[INFO] Modo debug %s.", "ligado" if ligado else "desligado")
        with self._trava_forma:
            if not self._compacta and self._moldura:  # o cartão aberto ganha (ou perde) a aba na hora
                self._painel_aberto = False
                cartao, _ = self._moldura.cartao(JANELA_LARGURA, JANELA_ALTURA)
                self._moldura.posicionar_cartao(cartao, False, ligado)
        return ligado

    def _mostrar_balao(self, caixa):
        with self._trava_forma:
            self._balao = caixa
            self._aplicar_forma_compacta()

    def _abrir_menu_compacto(self, aberto: bool, altura: int = 0):
        with self._trava_forma:
            de = self._altura_menu if self._menu_aberto else 0
            para = altura if aberto else 0
            if self._compacta and self._moldura and de != para:
                self._moldura.animar_lista(de, para, self._botoes_visiveis)
            self._menu_aberto = aberto
            self._altura_menu = para
            self._aplicar_forma_compacta()

    def _aplicar_forma_compacta(self):
        if self._compacta and self._moldura:
            m = self._moldura
            extra = self._altura_menu if self._menu_aberto else 0
            m.posicionar_compacta(m.canto(extra), self._botoes_visiveis, self._menu_aberto, self._balao)

    def _checar_ia(self):
        """O Ollama responde? Se cair (ou voltar), o anel da bolinha muda de cor."""
        try:
            listar_modelos()
            fora = False
        except Exception:
            fora = True
        if fora != self._ia_fora:
            self._ia_fora = fora
            self._chamar_pagina("definirIaFora", fora)

    def _talvez_checar_ia(self):
        agora = time.time()
        if agora - self._ultima_checagem_ia >= INTERVALO_CHECAR_IA:
            self._ultima_checagem_ia = agora
            threading.Thread(target=self._checar_ia, name="checar-ia", daemon=True).start()

    def _compactar_pagina(self):
        """A página monta a bolinha, o nome e os botões em volta no mesmo desenho do recorte da janela."""
        self._chamar_pagina("aoCompactar", desenho_compacto())

    def _criar_moldura(self):
        try:
            self._moldura = Moldura(self.janela.native.Handle.ToInt32())
            # Sem barra de título nunca: tanto a bolinha quanto o cartão são desenhados pela página
            self._moldura.sem_moldura()
            if self._estado.ativo.is_set():
                cartao, _ = self._moldura.cartao(JANELA_LARGURA, JANELA_ALTURA)
                self._moldura.posicionar_cartao(cartao, False, com_aba(self._preferencias, self._tem_raciocinio))
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
                self._talvez_checar_ia()
                self._tratar_evento(tipo, dado)
            except Exception as erro:
                logger.error("[JANELA] %s", erro)
        self._central.fechar()  # se ela ficasse aberta, o programa não terminaria
        self.janela.destroy()
