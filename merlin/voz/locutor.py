"""Faz o Merlin falar: gera o áudio, toca e para se a pessoa interromper."""
import logging
import os
import tempfile
import time

import pygame

from merlin.interface.eventos import EstadoVisual
from merlin.voz.envelope import PASSO, envelope_do_audio

logger = logging.getLogger(__name__)

INTERVALO_VERIFICACAO = 0.02


class Locutor:
    def __init__(self, estado, canal, sintetizador, preferencias):
        self._estado = estado
        self._canal = canal
        self._sintetizador = sintetizador
        self._preferencias = preferencias
        pygame.mixer.init()

    def falar(self, texto: str) -> None:
        """Fala em voz alta (e registra no terminal para debug)."""
        logger.info("%s: %s", self._preferencias.personalidade.nome, texto)  # a fala aparece só no terminal
        self._canal.estado(EstadoVisual.FALANDO)
        self._estado.interromper.clear()
        arquivo = os.path.join(tempfile.gettempdir(), f"merlin_{os.getpid()}_{time.time_ns()}.wav")
        try:
            self._sintetizador.gerar(texto, self._preferencias.voz, arquivo)
            self._canal.envelope_fala(envelope_do_audio(arquivo), PASSO)
            self._estado.falando.set()
            self._tocar(arquivo)
        except Exception as erro:
            logger.warning("[TTS] Piper falhou (%s); usando voz do Windows.", erro)
            self._estado.reproduzindo.clear()
            self._estado.falando.set()
            self._falar_com_voz_do_windows(texto)
        finally:
            self._apagar(arquivo)
            self._estado.falando.clear()
            self._estado.registrar_atividade()
            self._canal.estado(EstadoVisual.OUVINDO if self._estado.ativo.is_set() else EstadoVisual.ESPERA)

    def _tocar(self, arquivo):
        pygame.mixer.music.load(arquivo)
        pygame.mixer.music.play()
        self._estado.reproduzindo.set()
        while pygame.mixer.music.get_busy():
            if self._estado.interromper.is_set():
                pygame.mixer.music.stop()
                logger.info("[INFO] Fala interrompida.")
                break
            time.sleep(INTERVALO_VERIFICACAO)
        self._estado.reproduzindo.clear()
        pygame.mixer.music.unload()

    @staticmethod
    def _falar_com_voz_do_windows(texto):
        """Plano B, também offline, caso o Piper falhe."""
        try:
            import pyttsx3

            motor = pyttsx3.init()
            for voz in motor.getProperty("voices"):
                if "brazil" in voz.name.lower() or "portuguese" in voz.name.lower():
                    motor.setProperty("voice", voz.id)
                    break
            motor.say(texto)
            motor.runAndWait()
        except Exception as erro:
            logger.error("[TTS fallback] %s", erro)

    @staticmethod
    def _apagar(arquivo):
        try:
            os.remove(arquivo)
        except OSError:
            pass
