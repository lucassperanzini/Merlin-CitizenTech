"""Reconhecimento de fala offline com faster-whisper: usa a placa de vídeo e, se ela falhar, a CPU."""
import logging
import os
import sys
from pathlib import Path

import numpy as np
import speech_recognition as sr
from faster_whisper import WhisperModel

from merlin.config import MODELO_WHISPER_CPU, MODELO_WHISPER_GPU, PASTA_MODELOS

logger = logging.getLogger(__name__)

TAXA_WHISPER = 16000
LARGURA_AMOSTRA = 2
PROBABILIDADE_MAX_SEM_FALA = 0.6


def registrar_bibliotecas_nvidia() -> None:
    """As bibliotecas da NVIDIA ficam na .venv, onde o Windows não as procura sozinho."""
    pasta_nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    pastas = [str(p) for p in (pasta_nvidia / "cublas" / "bin", pasta_nvidia / "cudnn" / "bin") if p.is_dir()]
    if pastas:
        os.environ["PATH"] = os.pathsep.join([*pastas, os.environ.get("PATH", "")])


def carregar_na_placa_de_video() -> WhisperModel:
    modelo = WhisperModel(str(PASTA_MODELOS / MODELO_WHISPER_GPU), device="cuda", compute_type="float16")
    # A falta de uma biblioteca só aparece ao usar o modelo, então é preciso transcrever de verdade aqui.
    # Sem o filtro de voz, porque ele pularia o silêncio e a placa nem seria usada.
    segmentos, _ = modelo.transcribe(np.zeros(TAXA_WHISPER, dtype=np.float32), language="pt", beam_size=1, vad_filter=False)
    list(segmentos)
    return modelo


def carregar_na_cpu() -> WhisperModel:
    return WhisperModel(str(PASTA_MODELOS / MODELO_WHISPER_CPU), device="cpu", compute_type="int8")


class Transcritor:
    def __init__(self):
        self._modelo = None
        self.dispositivo = ""  # "gpu" ou "cpu" depois de carregado: aparece no status das configurações

    def precarregar(self) -> None:
        self._obter_modelo()

    def transcrever(self, audio: sr.AudioData, dica: str = "") -> str:
        """A dica (frases com o nome do assistente) ajuda o Whisper a reconhecer palavras incomuns."""
        bruto = audio.get_raw_data(convert_rate=TAXA_WHISPER, convert_width=LARGURA_AMOSTRA)
        amostras = np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0
        segmentos, _ = self._obter_modelo().transcribe(
            amostras, language="pt", beam_size=1, vad_filter=True,
            initial_prompt=dica or None, condition_on_previous_text=False,
        )
        partes = (s.text.strip() for s in segmentos if s.no_speech_prob < PROBABILIDADE_MAX_SEM_FALA)
        return " ".join(partes).strip().lower()

    def _obter_modelo(self) -> WhisperModel:
        if self._modelo is None:
            self._modelo = self._carregar()
        return self._modelo

    def _carregar(self) -> WhisperModel:
        registrar_bibliotecas_nvidia()
        try:
            modelo = carregar_na_placa_de_video()
            logger.info("[VOZ] Reconhecimento na placa de vídeo (%s).", MODELO_WHISPER_GPU)
            self.dispositivo = "gpu"
            return modelo
        except Exception as erro:
            logger.warning("[VOZ] Placa de vídeo indisponível (%s); usando a CPU (%s).", erro, MODELO_WHISPER_CPU)
            self.dispositivo = "cpu"
            return carregar_na_cpu()
