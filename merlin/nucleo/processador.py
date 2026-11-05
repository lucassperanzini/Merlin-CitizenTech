"""Decide o que fazer com cada frase: ativar, resolver uma confirmação ou encaminhar à ação da intenção."""
import logging
from typing import Callable, Mapping

from merlin.ia.confirmacao import RespostaConfirmacao
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.interface.eventos import EstadoVisual
from merlin.texto import remover_palavra_ativacao, tem_palavra_ativacao

logger = logging.getLogger(__name__)

Acao = Callable[[Intencao], str | None]


class ProcessadorComandos:
    def __init__(self, estado, sessao, canal, locutor, classificador, confirmador, saudacao,
                 acoes: Mapping[TipoIntencao, Acao]):
        self._estado = estado
        self._sessao = sessao
        self._canal = canal
        self._locutor = locutor
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
            self._executar_intencao(comando)
        except Exception as erro:
            logger.error("[IA] Erro: %s", erro)
            self._locutor.falar("Não consegui falar com o meu cérebro. Verifique se o Ollama está rodando.")

    def _resolver_pendencia(self, pendencia, comando) -> bool:
        """Retorna True se a frase respondeu à pergunta; caso contrário, ela segue como um comando normal."""
        resposta = self._confirmador.classificar(pendencia.pergunta, comando)
        logger.info("[CONFIRMAÇÃO]: %s", resposta.value)
        if resposta is RespostaConfirmacao.SIM:
            pendencia.ao_confirmar()
            return True
        if resposta is RespostaConfirmacao.NAO:
            self._locutor.falar(pendencia.resposta_recusa)
            return True
        return False

    def _executar_intencao(self, comando):
        intencao = self._classificador.classificar(comando)
        logger.info("[INTENÇÃO]: %s (alvo: %s)", intencao.tipo.value, intencao.alvo)
        resultado = self._acoes[intencao.tipo](intencao)
        if resultado:
            logger.info("[LOG]: %s", resultado)
