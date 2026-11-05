"""Ponto de entrada: cria as peças do Merlin, conecta umas às outras e coloca tudo para rodar."""
import logging
import os
import threading
from dataclasses import dataclass

import merlin  # noqa: F401  (ativa o modo offline antes de importar as bibliotecas de modelos)
from merlin.acoes.abrir_programa import AbrirPrograma
from merlin.acoes.conversar import Conversar
from merlin.acoes.criar import CriarArquivo, CriarPasta
from merlin.acoes.fechar_programa import FecharPrograma
from merlin.acoes.locais import LocaisPermitidos, pastas_do_usuario
from merlin.acoes.sessao import Dispensar, Encerrar
from merlin.acoes.web import PesquisarWeb
from merlin.audio.ouvinte import Ouvinte
from merlin.audio.transcricao import Transcritor
from merlin.config import ARQ_PREFERENCIAS, MODELO_IA, NOME, PALAVRAS_ATIVACAO
from merlin.estado import EstadoAssistente
from merlin.ia.cliente import ClienteIA
from merlin.ia.confirmacao import ClassificadorConfirmacao
from merlin.ia.conversa import Conversa
from merlin.ia.despedida import GeradorDespedida, GeradorEncerramento
from merlin.ia.divisao import DivisorTarefas
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
from merlin.voz.som_ativacao import SomAtivacao

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


def construir_acoes(sessao, estado, cliente_ia):
    """Para o Merlin aprender algo novo: crie a ação em merlin/acoes, registre aqui e descreva a intenção à IA.

    Cada ação só executa e devolve um Resultado; o processador monta a resposta falada de todas as tarefas.
    """
    pesquisa = PesquisarWeb()
    locais = LocaisPermitidos(pastas_do_usuario())
    return {
        TipoIntencao.DISPENSAR: Dispensar(sessao, GeradorDespedida(cliente_ia)),
        TipoIntencao.ENCERRAR: Encerrar(estado, GeradorEncerramento(cliente_ia)),
        TipoIntencao.FECHAR_PROGRAMA: FecharPrograma(),
        TipoIntencao.ABRIR_PROGRAMA: AbrirPrograma(pesquisa),
        TipoIntencao.PESQUISAR_WEB: pesquisa,
        TipoIntencao.CRIAR_PASTA: CriarPasta(locais),
        TipoIntencao.CRIAR_ARQUIVO: CriarArquivo(locais),
        TipoIntencao.CONVERSAR: Conversar(Conversa(cliente_ia)),
    }


def construir_aplicacao() -> Aplicacao:
    estado = EstadoAssistente()
    canal = CanalInterface()
    preferencias = Preferencias(ARQ_PREFERENCIAS)
    sessao = Sessao(estado, canal, SomAtivacao(estado))
    sintetizador = Sintetizador()
    locutor = Locutor(estado, canal, sintetizador, preferencias)
    transcritor = Transcritor()
    cliente_ia = ClienteIA(MODELO_IA)

    processador = ProcessadorComandos(
        estado, sessao, canal, locutor,
        divisor=DivisorTarefas(cliente_ia),
        classificador=ClassificadorIntencao(cliente_ia),
        confirmador=ClassificadorConfirmacao(cliente_ia),
        saudacao=GeradorSaudacao(cliente_ia),
        acoes=construir_acoes(sessao, estado, cliente_ia),
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
