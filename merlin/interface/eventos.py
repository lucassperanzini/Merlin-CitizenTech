"""Canal de mensagens para a janela. O resto do programa usa isto e nunca precisa conhecer a janela em si."""
import queue
from enum import Enum


class EstadoVisual(str, Enum):
    """Os valores são os nomes usados pela página da janela."""

    ESPERA = "espera"
    OUVINDO = "ouvindo"
    PENSANDO = "pensando"
    FALANDO = "falando"


class TipoEvento(Enum):
    MOSTRAR = "mostrar"
    ESCONDER = "esconder"
    ESTADO = "estado"
    LEGENDA = "legenda"


class CanalInterface:
    def __init__(self):
        self._fila = queue.Queue()

    def mostrar(self) -> None:
        self._fila.put((TipoEvento.MOSTRAR, None))

    def esconder(self) -> None:
        self._fila.put((TipoEvento.ESCONDER, None))

    def estado(self, estado: EstadoVisual) -> None:
        self._fila.put((TipoEvento.ESTADO, estado))

    def legenda(self, texto: str) -> None:
        self._fila.put((TipoEvento.LEGENDA, texto))

    def proximo(self, tempo_limite: float):
        """Retorna (tipo, dado), ou (None, None) se nada chegar dentro do tempo limite."""
        try:
            return self._fila.get(timeout=tempo_limite)
        except queue.Empty:
            return None, None
