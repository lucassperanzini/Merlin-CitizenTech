"""Decide o que fazer com cada frase: ativar, resolver uma confirmação ou executar as tarefas pedidas."""
import logging
from typing import Callable, Mapping

from merlin.config import MAX_TAREFAS_POR_FRASE
from merlin.ia.confirmacao import RespostaConfirmacao
from merlin.ia.intencoes import ACOES_NO_COMPUTADOR, Intencao, TipoIntencao
from merlin.interface.eventos import EstadoVisual
from merlin.nucleo.resposta import Resultado, montar_resposta
from merlin.texto import remover_palavra_ativacao, tem_palavra_ativacao

logger = logging.getLogger(__name__)

Acao = Callable[[Intencao], Resultado]

AVISO_SEM_IA = "Não consegui falar com o meu cérebro. Verifique se o Ollama está rodando."


class ProcessadorComandos:
    def __init__(self, estado, sessao, canal, locutor, divisor, classificador, confirmador, saudacao,
                 acoes: Mapping[TipoIntencao, Acao], memoria=None):
        self._memoria = memoria
        self._estado = estado
        self._sessao = sessao
        self._canal = canal
        self._locutor = locutor
        self._divisor = divisor
        self._classificador = classificador
        self._confirmador = confirmador
        self._saudacao = saudacao
        self._acoes = acoes

    def processar(self, frase: str) -> None:
        ativou_agora = not self._estado.ativo.is_set()
        if ativou_agora:
            if not tem_palavra_ativacao(frase):
                return
            self._sessao.ativar()

        comando = remover_palavra_ativacao(frase)
        self._canal.estado(EstadoVisual.PENSANDO)

        # Qualquer frase depois da pergunta encerra a espera: só um "sim" claro executa a ação
        pendencia = self._sessao.pegar_pendencia()

        if not comando:
            self._locutor.falar(self._saudacao.gerar() if ativou_agora else "Pois não?")
            return

        try:
            if pendencia and self._resolver_pendencia(pendencia, comando):
                return
            tarefas = self._divisor.dividir(comando)
        except Exception as erro:
            logger.error("[IA] Erro: %s", erro)
            self._locutor.falar(AVISO_SEM_IA)
            return
        self._responder(self._executar_tarefas(comando, tarefas), comando)

    def _resolver_pendencia(self, pendencia, comando) -> bool:
        """Retorna True se a frase respondeu à pergunta; caso contrário, ela segue como um comando normal."""
        resposta = self._confirmador.classificar(pendencia.pergunta, comando)
        logger.info("[CONFIRMAÇÃO]: %s", resposta.value)
        if resposta is RespostaConfirmacao.SIM:
            self._responder([pendencia.ao_confirmar()], comando)
            return True
        if resposta is RespostaConfirmacao.NAO:
            self._locutor.falar(pendencia.resposta_recusa)
            return True
        return False

    def _executar_tarefas(self, comando: str, tarefas: list[str]) -> list[Resultado]:
        resultados = []
        if len(tarefas) > MAX_TAREFAS_POR_FRASE:
            resultados.append(Resultado(f"Vou fazer só as {MAX_TAREFAS_POR_FRASE} primeiras tarefas.", frase_completa=True))
            tarefas = tarefas[:MAX_TAREFAS_POR_FRASE]
        try:
            intencoes = self._entender(comando, tarefas)
        except Exception as erro:
            logger.error("[IA] Erro: %s", erro)
            return [Resultado(AVISO_SEM_IA, frase_completa=True)]
        if len(intencoes) == 1:
            resultados = []  # a frase voltou a ser um pedido só: o aviso de limite não vale mais

        for intencao in intencoes:
            try:
                resultado = self._executar_intencao(intencao)
            except Exception as erro:
                # O que já foi feito continua na resposta
                logger.error("[IA] Erro: %s", erro)
                resultados.append(Resultado(AVISO_SEM_IA, frase_completa=True))
                break
            resultados.append(resultado)
            if resultado.finaliza:
                break
        return resultados

    def _entender(self, comando: str, tarefas: list[str]) -> list[Intencao]:
        """Só vale separar a frase se alguma parte mexer no computador. "Fala aí, tudo bem?" é uma conversa só:
        separada, o "tudo bem" sozinho chegou a ser entendido como despedida."""
        intencoes = [self._classificar(tarefa) for tarefa in tarefas]
        if len(intencoes) == 1:
            return intencoes
        logger.info("[TAREFAS]: %s", tarefas)
        if any(i.tipo in ACOES_NO_COMPUTADOR for i in intencoes):
            return intencoes
        logger.info("[TAREFAS]: nenhuma parte é uma ação; a frase segue inteira")
        return [self._classificar(comando)]

    def _classificar(self, comando: str) -> Intencao:
        intencao = self._classificador.classificar(comando)
        logger.info("[INTENÇÃO]: %s (alvo: %s, local: %s)", intencao.tipo.value, intencao.alvo, intencao.local)
        return intencao

    def _executar_intencao(self, intencao: Intencao) -> Resultado:
        resultado = self._acoes[intencao.tipo](intencao)
        if resultado.registro:
            logger.info("[LOG]: %s", resultado.registro)
        return resultado

    def _responder(self, resultados: list[Resultado], comando: str) -> None:
        resposta = montar_resposta(resultados)
        if self._memoria:
            self._memoria.registrar(comando, resposta)
        self._locutor.falar(resposta)
        for resultado in resultados:
            if resultado.depois:
                resultado.depois()
