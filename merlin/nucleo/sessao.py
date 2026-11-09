"""Ciclo de uso do Merlin: ativado ou em espera, e a pergunta que estiver aguardando resposta."""
import logging
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Pendencia:
    """Uma ação que só acontece se a pessoa autorizar. Qualquer ação nova pode usar este mesmo mecanismo."""

    pergunta: str
    ao_confirmar: Callable[[], object]  # executa a ação e devolve o Resultado a ser falado
    resposta_recusa: str
    expira_em: float
    copiar: Callable[[], object] | None = None  # botão Copiar do cartão, quando a ação oferece essa saída


class Sessao:
    def __init__(self, estado, canal, som_ativacao=None, memoria=None):
        self._estado = estado
        self._canal = canal
        self._memoria = memoria
        self._som_ativacao = som_ativacao
        self._pendencia = None
        self._cartao_aberto = False

    def ativar(self, mostrar: bool = True) -> None:
        """mostrar=False é o modo discreto: ativa (e toca o som) sem abrir o cartão, para um pedido rápido.
        Chamar de novo com mostrar=True abre o cartão, se ele ainda estiver fechado."""
        self._estado.registrar_atividade()
        if not self._estado.ativo.is_set():
            self._estado.ativo.set()
            self._abrir_cartao(mostrar)
            if self._som_ativacao:
                self._som_ativacao.tocar()
        else:
            self._abrir_cartao(mostrar)

    def _abrir_cartao(self, mostrar: bool) -> None:
        if mostrar and not self._cartao_aberto:
            self._cartao_aberto = True
            self._canal.mostrar()

    def desativar(self) -> None:
        self._pendencia = None  # ao sair, nenhuma pergunta continua valendo
        if self._memoria:
            self._memoria.limpar()  # a próxima ativação começa uma conversa nova
        self._estado.ativo.clear()
        self._cartao_aberto = False
        self._canal.esconder()

    def aguardar_confirmacao(self, pendencia: Pendencia) -> None:
        self._pendencia = pendencia

    def aguardando_decisao(self) -> bool:
        """Há uma pergunta ainda no prazo: o cartão não fecha sozinho enquanto a pessoa decide."""
        return self._pendencia is not None and time.time() <= self._pendencia.expira_em

    def tem_pendencia(self) -> bool:
        return self._pendencia is not None

    def pegar_pendencia(self) -> Pendencia | None:
        """Entrega a pendência uma única vez; se o prazo acabou, ela é descartada sem agir."""
        pendencia, self._pendencia = self._pendencia, None
        if pendencia and time.time() > pendencia.expira_em:
            logger.info("[INFO] Confirmação expirada.")
            return None
        return pendencia
