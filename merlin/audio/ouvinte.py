"""Escuta contínua em segundo plano: transcreve cada frase e entrega à fila o que for para o Merlin."""
import logging

import speech_recognition as sr

from merlin.audio.microfone import MicrofoneComMedidor
from merlin.config import LIMITE_FRASE
from merlin.interface.eventos import EstadoVisual
from merlin.texto import tem_palavra_ativacao

logger = logging.getLogger(__name__)

DURACAO_CALIBRAGEM = 2


class Ouvinte:
    def __init__(self, estado, canal, transcritor):
        self._estado = estado
        self._canal = canal
        self._transcritor = transcritor
        self._recognizer = sr.Recognizer()
        self._microfone = None

    def calibrar(self) -> None:
        self._microfone = MicrofoneComMedidor(self._recognizer, self._estado)
        with self._microfone as fonte:
            logger.info("Calibrando o ruído ambiente...")
            self._recognizer.adjust_for_ambient_noise(fonte, duration=DURACAO_CALIBRAGEM)

    def escutar(self) -> None:
        self._recognizer.listen_in_background(self._microfone, self._ao_ouvir, phrase_time_limit=LIMITE_FRASE)

    def _ao_ouvir(self, _recognizer, audio):
        if self._estado.ativo.is_set() and not self._estado.falando.is_set():
            self._canal.estado(EstadoVisual.PENSANDO)  # a frase terminou e está sendo transcrita
        try:
            frase = self._transcritor.transcrever(audio)
            if frase:
                logger.info("[OUVI]: %s", frase)
                if self._estado.ativo.is_set() or tem_palavra_ativacao(frase):
                    self._estado.fila_comandos.put(frase)
                    return
        except Exception as erro:
            logger.error("Erro no reconhecimento: %s", erro)
        if self._estado.ativo.is_set():
            self._canal.estado(EstadoVisual.OUVINDO)  # era só ruído: volta a ouvir
