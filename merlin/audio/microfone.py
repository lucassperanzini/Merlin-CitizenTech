"""Microfone com medidor: mede o volume no caminho e esconde do reconhecimento a voz do próprio Merlin."""
import logging
import time
from collections import deque

import speech_recognition as sr

from merlin.audio.medicao import DetectorInterrupcao, calcular_nivel, volume

logger = logging.getLogger(__name__)

BLOCOS_RECENTES = 64


class FluxoComMedidor:
    """Fica entre o microfone e o reconhecimento: mede o volume e, enquanto o Merlin fala, entrega silêncio."""

    def __init__(self, fluxo, recognizer, estado):
        self.fluxo = fluxo
        self.recognizer = recognizer
        self.estado = estado
        self.detector = DetectorInterrupcao()
        self.recentes = deque(maxlen=BLOCOS_RECENTES)  # para não perder o começo da frase que interrompeu
        self.atrasados = deque()
        self.inicio_da_voz = 0.0

    def read(self, tamanho):
        dados = self.fluxo.read(tamanho)
        if self.estado.microfone_desligado.is_set():
            return self._desligado(dados)
        if self.estado.microfone_mudo():
            return self._durante_a_fala(dados)

        self.recognizer.dynamic_energy_threshold = True
        self._recuperar_voz_que_interrompeu()
        if self.estado.ativo.is_set():
            self.estado.registrar_nivel(calcular_nivel(dados, self.recognizer.energy_threshold))
        if self.atrasados:
            self.atrasados.append(dados)
            return self.atrasados.popleft()
        return dados

    def close(self):
        self.fluxo.close()

    def _desligado(self, dados):
        # Mudo pela pessoa: só silêncio sai daqui, nem volume, nem interrupção da fala
        self.recognizer.dynamic_energy_threshold = False
        self.recentes.clear()
        self.atrasados.clear()
        self.detector.reiniciar()
        return bytes(len(dados))

    def _durante_a_fala(self, dados):
        # O limiar automático desabaria se recebesse silêncio artificial
        self.recognizer.dynamic_energy_threshold = False
        agora = time.time()
        self.recentes.append((agora, dados))
        self.atrasados.clear()
        if not self.estado.reproduzindo.is_set():
            self.detector.reiniciar()
        elif not self.estado.interromper.is_set():
            self._verificar_interrupcao(dados, agora)
        return bytes(len(dados))

    def _verificar_interrupcao(self, dados, agora):
        som = volume(dados)
        if self.detector.analisar(som, self.recognizer.energy_threshold, agora):
            logger.info("[INFO] Voz por cima da fala (eco medido: %.0f, som: %.0f).", self.detector.eco, som)
            self.inicio_da_voz = self.detector.acima_desde
            self.estado.interromper.set()

    def _recuperar_voz_que_interrompeu(self):
        if not self.recentes:
            return
        if self.estado.interromper.is_set():
            # Só o que veio depois de a voz começar: o trecho anterior tem o eco do próprio Merlin
            self.atrasados.extend(dados for momento, dados in self.recentes if momento >= self.inicio_da_voz)
            self.estado.interromper.clear()
        self.recentes.clear()


class MicrofoneComMedidor(sr.Microphone):
    """O listen_in_background só avisa ao fim da frase; o medidor permite reagir enquanto a pessoa fala."""

    def __init__(self, recognizer, estado, sample_rate=None, chunk_size=1024):
        super().__init__(sample_rate=sample_rate, chunk_size=chunk_size)
        self.recognizer = recognizer
        self.estado = estado

    def __enter__(self):
        super().__enter__()
        self.stream = FluxoComMedidor(self.stream, self.recognizer, self.estado)
        return self
