"""Atende a fila de comandos, um por vez, e devolve o Merlin à espera depois de um tempo sem uso."""
import logging
import queue

from merlin.config import TEMPO_INATIVIDADE
from merlin.interface.eventos import EstadoVisual

logger = logging.getLogger(__name__)

ESPERA_COMANDO = 0.5


class TrabalhadorComandos:
    def __init__(self, estado, sessao, canal, processador, locutor=None):
        self._estado = estado
        self._sessao = sessao
        self._canal = canal
        self._processador = processador
        self._locutor = locutor
        self._avisos = queue.Queue()

    def avisar(self, fala: str, cartao: str) -> None:
        """Um aviso que não veio de um pedido (script agendado). Pode ser chamado de qualquer thread."""
        self._avisos.put((fala, cartao))

    def executar(self) -> None:
        while not self._estado.encerrando.is_set():
            try:
                frase = self._estado.fila_comandos.get(timeout=ESPERA_COMANDO)
            except queue.Empty:
                self._entregar_aviso()
                self._verificar_inatividade()
                continue
            self._atender(frase)

    def _entregar_aviso(self) -> None:
        """Aqui, e não na thread de quem avisou: é a mesma fila dos comandos, então nunca fala por cima de uma resposta."""
        if self._estado.falando.is_set():
            return
        try:
            fala, cartao = self._avisos.get_nowait()
        except queue.Empty:
            return
        try:
            self._sessao.ativar()
            self._locutor.falar(fala)
            self._canal.resultado_script(cartao)
        except Exception as erro:
            logger.error("[ERRO] Não consegui entregar o aviso: %s", erro)

    def _atender(self, frase):
        try:
            self._processador.processar(frase)
        except Exception as erro:
            logger.error("[ERRO] %s", erro)
        finally:
            # Garante que o olho não fique preso em "pensando" se nada foi falado
            if self._estado.ativo.is_set() and not self._estado.falando.is_set():
                self._canal.estado(EstadoVisual.OUVINDO)

    def _verificar_inatividade(self):
        ocioso = (self._estado.ativo.is_set() and not self._estado.falando.is_set()
                  and not self._sessao.aguardando_decisao())
        if ocioso and self._estado.segundos_sem_atividade() > TEMPO_INATIVIDADE:
            logger.info("[INFO] Inatividade, voltando ao modo de espera.")
            self._sessao.desativar()
