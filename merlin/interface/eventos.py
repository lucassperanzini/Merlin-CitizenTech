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
    ENVELOPE_FALA = "envelope_fala"
    PERSONALIDADE = "personalidade"
    ABRIR_CONFIGURACOES = "abrir_configuracoes"


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

    def envelope_fala(self, volumes: list[float], passo: float) -> None:
        """Volume da fala que vai começar, para a aparência acompanhar a voz."""
        self._fila.put((TipoEvento.ENVELOPE_FALA, {"volumes": volumes, "passo": passo}))

    def personalidade(self) -> None:
        self._fila.put((TipoEvento.PERSONALIDADE, None))

    def abrir_configuracoes(self) -> None:
        self._fila.put((TipoEvento.ABRIR_CONFIGURACOES, None))

    def proximo(self, tempo_limite: float):
        """Retorna (tipo, dado), ou (None, None) se nada chegar dentro do tempo limite."""
        try:
            return self._fila.get(timeout=tempo_limite)
        except queue.Empty:
            return None, None
