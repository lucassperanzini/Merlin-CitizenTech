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
    ao_confirmar: Callable[[], None]
    resposta_recusa: str
    expira_em: float


class Sessao:
    def __init__(self, estado, canal):
        self._estado = estado
        self._canal = canal
        self._pendencia = None

    def ativar(self) -> None:
        self._estado.registrar_atividade()
        if not self._estado.ativo.is_set():
            self._estado.ativo.set()
            self._canal.mostrar()

    def desativar(self) -> None:
        self._pendencia = None  # ao sair, nenhuma pergunta continua valendo
        self._estado.ativo.clear()
        self._canal.esconder()

    def aguardar_confirmacao(self, pendencia: Pendencia) -> None:
        self._pendencia = pendencia

    def tem_pendencia(self) -> bool:
        return self._pendencia is not None

    def pegar_pendencia(self) -> Pendencia | None:
        """Entrega a pendência uma única vez; se o prazo acabou, ela é descartada sem agir."""
        pendencia, self._pendencia = self._pendencia, None
        if pendencia and time.time() > pendencia.expira_em:
            logger.info("[INFO] Confirmação expirada.")
            return None
        return pendencia
