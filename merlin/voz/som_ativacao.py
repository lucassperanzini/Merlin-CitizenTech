"""Toca o som de ativação da personalidade escolhida. Se algo falhar, o assistente segue, só que sem o som."""
import logging

import pygame

from merlin.config import VOLUME_SOM_ATIVACAO

logger = logging.getLogger(__name__)


class SomAtivacao:
    def __init__(self, estado, preferencias):
        self._estado = estado
        self._preferencias = preferencias
        self._sons = {}

    def tocar(self) -> None:
        """Não bloqueia. O microfone fica mudo durante o som, para o assistente não tentar transcrevê-lo."""
        som = self._carregar(self._preferencias.personalidade.som_ativacao)
        if som:
            self._estado.silenciar_microfone(som.get_length())
            som.play()

    def _carregar(self, arquivo):
        if arquivo not in self._sons:
            try:
                pygame.mixer.init()
                som = pygame.mixer.Sound(str(arquivo))
                som.set_volume(VOLUME_SOM_ATIVACAO)
                self._sons[arquivo] = som
            except (pygame.error, FileNotFoundError) as erro:
                logger.warning("[SOM] Som de ativação indisponível (%s): %s", arquivo.name, erro)
                self._sons[arquivo] = None
        return self._sons[arquivo]
