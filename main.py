"""Ponto de entrada: cria as peças do Merlin, conecta umas às outras e coloca tudo para rodar."""
import logging
import os
import threading
from dataclasses import dataclass

import merlin  # noqa: F401  (ativa o modo offline antes de importar as bibliotecas de modelos)
from merlin.acoes.abrir_programa import AbrirPrograma
from merlin.acoes.conversar import Conversar
from merlin.acoes.fechar_programa import FecharPrograma
from merlin.acoes.sessao import Dispensar, Encerrar
from merlin.acoes.web import PesquisarWeb
from merlin.audio.ouvinte import Ouvinte
from merlin.audio.transcricao import Transcritor
from merlin.config import ARQ_PREFERENCIAS, MODELO_IA, NOME, PALAVRAS_ATIVACAO
from merlin.estado import EstadoAssistente
from merlin.ia.cliente import ClienteIA
from merlin.ia.confirmacao import ClassificadorConfirmacao
from merlin.ia.conversa import Conversa
from merlin.ia.intencoes import ClassificadorIntencao, TipoIntencao
from merlin.ia.saudacao import GeradorSaudacao
from merlin.interface.eventos import CanalInterface
from merlin.interface.janela import JanelaMerlin
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.sessao import Sessao
from merlin.nucleo.trabalhador import TrabalhadorComandos
from merlin.preferencias import Preferencias
from merlin.voz.locutor import Locutor
from merlin.voz.sintese import Sintetizador

logger = logging.getLogger("merlin.main")


@dataclass
class Aplicacao:
    estado: EstadoAssistente
    sessao: Sessao
    preferencias: Preferencias
    locutor: Locutor
    sintetizador: Sintetizador
    transcritor: Transcritor
    ouvinte: Ouvinte
    processador: ProcessadorComandos
    trabalhador: TrabalhadorComandos
    janela: JanelaMerlin


def construir_acoes(locutor, sessao, estado, conversa):
    """Para o Merlin aprender algo novo: crie a ação em merlin/acoes, registre aqui e descreva a intenção à IA."""
    pesquisa = PesquisarWeb(locutor)
    return {
        TipoIntencao.DISPENSAR: Dispensar(locutor, sessao),
        TipoIntencao.ENCERRAR: Encerrar(locutor, estado),
        TipoIntencao.FECHAR_PROGRAMA: FecharPrograma(locutor, sessao),
        TipoIntencao.ABRIR_PROGRAMA: AbrirPrograma(locutor, pesquisa),
        TipoIntencao.PESQUISAR_WEB: pesquisa,
        TipoIntencao.CONVERSAR: Conversar(locutor, conversa),
    }


def construir_aplicacao() -> Aplicacao:
    estado = EstadoAssistente()
    canal = CanalInterface()
    preferencias = Preferencias(ARQ_PREFERENCIAS)
    sessao = Sessao(estado, canal)
    sintetizador = Sintetizador()
    locutor = Locutor(estado, canal, sintetizador, preferencias)
    transcritor = Transcritor()
    cliente_ia = ClienteIA(MODELO_IA)

    processador = ProcessadorComandos(
        estado, sessao, canal, locutor,
        classificador=ClassificadorIntencao(cliente_ia),
        confirmador=ClassificadorConfirmacao(cliente_ia),
        saudacao=GeradorSaudacao(cliente_ia),
        acoes=construir_acoes(locutor, sessao, estado, Conversa(cliente_ia)),
    )
    return Aplicacao(
        estado=estado,
        sessao=sessao,
        preferencias=preferencias,
        locutor=locutor,
        sintetizador=sintetizador,
        transcritor=transcritor,
        ouvinte=Ouvinte(estado, canal, transcritor),
        processador=processador,
        trabalhador=TrabalhadorComandos(estado, sessao, canal, processador),
        janela=JanelaMerlin(estado, canal, sessao, preferencias, locutor),
    )


def iniciar_escuta(app: Aplicacao) -> None:
    app.ouvinte.calibrar()
    logger.info("Carregando modelos offline...")
    app.transcritor.precarregar()
    app.sintetizador.precarregar(app.preferencias.voz)
    logger.info("%s em modo de espera. Diga '%s' para ativar.", NOME, PALAVRAS_ATIVACAO[0])
    threading.Thread(target=app.trabalhador.executar, daemon=True).start()
    app.ouvinte.escutar()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("merlin").setLevel(logging.INFO)  # as bibliotecas só aparecem se algo der errado
    app = construir_aplicacao()
    threading.Thread(target=iniciar_escuta, args=(app,), daemon=True).start()
    app.janela.executar()
    os._exit(0)  # as threads de áudio não têm como ser interrompidas de forma limpa


if __name__ == "__main__":
    main()
