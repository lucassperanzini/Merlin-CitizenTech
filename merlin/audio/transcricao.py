"""Reconhecimento de fala offline com faster-whisper."""
import numpy as np
import speech_recognition as sr
from faster_whisper import WhisperModel

from merlin.config import MODELO_WHISPER

TAXA_WHISPER = 16000
LARGURA_AMOSTRA = 2
PROBABILIDADE_MAX_SEM_FALA = 0.6
DICA_DE_VOCABULARIO = "Merlin, abra o navegador. Merlin, pesquise na internet."


class Transcritor:
    def __init__(self):
        self._modelo = None

    def precarregar(self) -> None:
        self.transcrever(sr.AudioData(b"\x00\x00" * TAXA_WHISPER, TAXA_WHISPER, LARGURA_AMOSTRA))

    def transcrever(self, audio: sr.AudioData) -> str:
        if self._modelo is None:
            self._modelo = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
        bruto = audio.get_raw_data(convert_rate=TAXA_WHISPER, convert_width=LARGURA_AMOSTRA)
        amostras = np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0
        segmentos, _ = self._modelo.transcribe(
            amostras, language="pt", beam_size=1, vad_filter=True,
            initial_prompt=DICA_DE_VOCABULARIO, condition_on_previous_text=False,
        )
        partes = (s.text.strip() for s in segmentos if s.no_speech_prob < PROBABILIDADE_MAX_SEM_FALA)
        return " ".join(partes).strip().lower()
