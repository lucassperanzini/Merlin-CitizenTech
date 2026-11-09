"""Faz o Merlin falar: gera o áudio, toca e para se a pessoa interromper."""
import logging
import os
import queue
import tempfile
import threading
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
        self._canal.resposta()  # a janela prepara a resposta; o texto aparece junto com a voz, trecho a trecho
        self._estado.interromper.clear()
        voz = self._preferencias.voz
        trechos = [texto]
        prontos, parar = queue.Queue(), threading.Event()
        threading.Thread(target=self._gerar_trechos, args=(trechos, voz, prontos, parar),
                         name="gerar-fala", daemon=True).start()
        tocou_algo = False
        try:
            while True:
                pronto = self._proximo_trecho(prontos)
                if pronto is None:
                    break
                if isinstance(pronto, Exception):
                    raise pronto
                arquivo, trecho = pronto
                try:
                    envelope = envelope_do_audio(arquivo)
                    self._canal.envelope_fala(envelope, PASSO)
                    self._canal.trecho_falado(trecho, len(envelope) * PASSO)  # o texto acompanha a voz
                    self._estado.falando.set()
                    tocou_algo = True
                    self._tocar(arquivo)
                finally:
                    self._apagar(arquivo)
                if self._estado.interromper.is_set():
                    logger.info("[INFO] Fala interrompida.")
                    self._canal.fala_interrompida()  # o texto para onde a voz parou
                    break
        except Exception as erro:
            if not tocou_algo:
                logger.warning("[TTS] A síntese falhou (%s); usando voz do Windows.", erro)
                self._canal.trecho_falado(texto, 0)  # sem o tempo do áudio: o texto aparece de uma vez
                self._estado.falando.set()
                self._falar_com_voz_do_windows(texto)
            else:
                logger.warning("[TTS] A síntese falhou no meio da fala (%s).", erro)
        finally:
            parar.set()  # se foi interrompida, o resto da resposta nem é gerado
            self._estado.reproduzindo.clear()
            self._estado.falando.clear()
            self._estado.registrar_atividade()
            self._canal.estado(EstadoVisual.OUVINDO if self._estado.ativo.is_set() else EstadoVisual.ESPERA)

    def _proximo_trecho(self, prontos):
        """Espera o próximo arquivo, mas desiste se a pessoa interromper enquanto ele ainda está sendo gerado."""
        while True:
            try:
                return prontos.get(timeout=INTERVALO_VERIFICACAO)
            except queue.Empty:
                if self._estado.interromper.is_set():
                    return None

    def _gerar_trechos(self, trechos, voz, prontos, parar):
        """Gera um trecho de cada vez e entrega os arquivos na ordem; a fila tem None no fim ou o erro."""
        try:
            for trecho in trechos:
                if parar.is_set():
                    break
                arquivo = os.path.join(tempfile.gettempdir(), f"merlin_{os.getpid()}_{time.time_ns()}.wav")
                self._sintetizador.gerar(trecho, voz, arquivo)
                if parar.is_set():  # a fala acabou (ou foi interrompida) enquanto este trecho era gerado
                    self._apagar(arquivo)
                    break
                prontos.put((arquivo, trecho))
            prontos.put(None)
        except Exception as erro:
            prontos.put(erro)

    def _tocar(self, arquivo):
        """Toca um arquivo até o fim ou até a pessoa falar por cima. Entre os trechos de uma mesma fala,
        "reproduzindo" continua ligado: o detector de interrupção não recomeça a cada frase."""
        pygame.mixer.music.load(arquivo)
        pygame.mixer.music.play()
        self._estado.reproduzindo.set()
        while pygame.mixer.music.get_busy():
            if self._estado.interromper.is_set():
                pygame.mixer.music.stop()
                break
            time.sleep(INTERVALO_VERIFICACAO)
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
