"""Ponto de entrada: cria as peças do Merlin, conecta umas às outras e coloca tudo para rodar."""
import logging
import os
import threading
from dataclasses import dataclass

import merlin  # noqa: F401  (ativa o modo offline antes de importar as bibliotecas de modelos)
from merlin.audio.ouvinte import Ouvinte
from merlin.audio.transcricao import Transcritor
from merlin.config import ARQ_PREFERENCIAS, ARQ_ULTIMA_CONSULTA, DIAS_DE_REGISTRO, PASTA_REGISTROS
from merlin.estado import EstadoAssistente
from merlin.habilidades import HABILIDADES
from merlin.habilidades.base import Recursos
from merlin.ia.cliente import ClienteIA
from merlin.ia.confirmacao import ClassificadorConfirmacao
from merlin.ia.divisao import DivisorTarefas
from merlin.ia.intencoes import ClassificadorIntencao, TipoIntencao
from merlin.ia.frases import GeradorFrases
from merlin.interface.assistentes import ApiAssistentes, ServicoAssistentes
from merlin.interface.central import ApiCentral, JanelaCentral
from merlin.interface.configuracoes import ApiConfiguracoes, ServicoConfiguracoes
from merlin.interface.painel_alertas import ApiAlertas, ServicoAlertas
from merlin.interface.painel_habilidades import ApiPainelHabilidades, ServicoPainelHabilidades
from merlin.interface.eventos import CanalInterface
from merlin.interface.janela import JanelaMerlin
from merlin.interface.janela_raciocinio import ApiRaciocinio
from merlin.nucleo.memoria_conversa import MemoriaConversa
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.gravador_raciocinio import GravadorRaciocinio
from merlin.nucleo.raciocinio import Raciocinio
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


def construir_acoes(recursos: Recursos) -> dict:
    """Uma ação para cada habilidade de merlin/habilidades/. Para o assistente aprender algo novo, crie um arquivo
    lá (com a ação em merlin/acoes/): ele entra aqui, no prompt da IA e nas regras sozinho.

    Cada ação só executa e devolve um Resultado; o processador monta a resposta falada de todas as tarefas.
    """
    return {TipoIntencao(h.nome): h.criar_acao(recursos) for h in HABILIDADES}


def construir_aplicacao() -> Aplicacao:
    estado = EstadoAssistente()
    canal = CanalInterface()
    preferencias = Preferencias(ARQ_PREFERENCIAS)
    memoria = MemoriaConversa()
    sessao = Sessao(estado, canal, SomAtivacao(estado, preferencias), memoria)
    sintetizador = Sintetizador()
    locutor = Locutor(estado, canal, sintetizador, preferencias)
    transcritor = Transcritor()
    ouvinte = Ouvinte(estado, canal, transcritor, preferencias)
    cliente_ia = ClienteIA(lambda: preferencias.modelo_ia)
    # O que a IA entendeu e fez: na memória para a janela de raciocínio, e no arquivo do dia em registros/
    gravador = GravadorRaciocinio(PASTA_REGISTROS, DIAS_DE_REGISTRO)
    gravador.apagar_antigos()
    raciocinio = Raciocinio(gravador=gravador)
    servico_configuracoes = ServicoConfiguracoes(preferencias, locutor, canal, memoria, cliente_ia, estado, transcritor)
    # Central: uma janela só, com abas, para configurar e investigar
    central = JanelaCentral(ApiCentral(
        ajustes=ApiConfiguracoes(servico_configuracoes),
        assistentes=ApiAssistentes(
            ServicoAssistentes(preferencias, canal, cliente_ia, servico_configuracoes.trocar_personalidade)),
        habilidades=ApiPainelHabilidades(ServicoPainelHabilidades(cliente_ia)),
        alertas=ApiAlertas(ServicoAlertas(arquivo_ultima=ARQ_ULTIMA_CONSULTA)),
    ))

    processador = ProcessadorComandos(
        estado, sessao, canal, locutor,
        divisor=DivisorTarefas(cliente_ia),
        classificador=ClassificadorIntencao(cliente_ia),
        confirmador=ClassificadorConfirmacao(cliente_ia),
        saudacao=GeradorFrases(cliente_ia, lambda: preferencias.personalidade.saudacao),
        acoes=construir_acoes(Recursos(estado, sessao, canal, cliente_ia, memoria, preferencias, raciocinio)),
        memoria=memoria,
        preferencias=preferencias,
        raciocinio=raciocinio,
    )
    return Aplicacao(
        estado=estado,
        sessao=sessao,
        preferencias=preferencias,
        locutor=locutor,
        sintetizador=sintetizador,
        transcritor=transcritor,
        ouvinte=ouvinte,
        processador=processador,
        trabalhador=TrabalhadorComandos(estado, sessao, canal, processador),
        janela=JanelaMerlin(estado, canal, sessao, preferencias, central,
                            trocar_assistente=servico_configuracoes.trocar_personalidade,
                            raciocinio=ApiRaciocinio(raciocinio, gravador.pasta)),
    )


def iniciar_escuta(app: Aplicacao) -> None:
    app.ouvinte.calibrar()
    logger.info("Carregando modelos offline...")
    app.transcritor.precarregar()
    app.sintetizador.precarregar(app.preferencias.voz)
    personalidade = app.preferencias.personalidade
    logger.info("%s em modo de espera. Diga '%s' para ativar.", personalidade.nome, personalidade.palavras_ativacao[0])
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
