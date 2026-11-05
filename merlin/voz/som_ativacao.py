"""Toca o som de ativação. Se algo falhar, o Merlin segue normalmente, só que sem o som."""
import logging

import pygame

from merlin.config import ARQ_SOM_ATIVACAO, VOLUME_SOM_ATIVACAO

logger = logging.getLogger(__name__)


class SomAtivacao:
    def __init__(self, estado):
        self._estado = estado
        self._som = None
        try:
            pygame.mixer.init()
            self._som = pygame.mixer.Sound(str(ARQ_SOM_ATIVACAO))
            self._som.set_volume(VOLUME_SOM_ATIVACAO)
        except (pygame.error, FileNotFoundError) as erro:
            logger.warning("[SOM] Som de ativação indisponível: %s", erro)

    def tocar(self) -> None:
        """Não bloqueia. O microfone fica mudo durante o som, para o Merlin não tentar transcrevê-lo."""
        if self._som:
            self._estado.silenciar_microfone(self._som.get_length())
            self._som.play()
