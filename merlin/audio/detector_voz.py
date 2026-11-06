"""Detector de voz humana (Silero VAD, o mesmo que vem com o faster-whisper): diz se um trecho de áudio tem gente
falando. Diferente do volume, não confunde ventilador, teclado ou música com voz. Roda no processador, offline."""
import numpy as np
from faster_whisper.vad import get_vad_model

TAXA = 16000  # o modelo só aceita 16 kHz
AMOSTRAS = 512  # 32 ms por trecho
CONTEXTO = 64  # o modelo olha um pedacinho do trecho anterior


class DetectorVoz:
    def __init__(self):
        self._sessao = get_vad_model().session
        self.reiniciar()

    def reiniciar(self) -> None:
        """Esquece o áudio anterior (estado interno do modelo)."""
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._contexto = np.zeros(CONTEXTO, dtype=np.float32)

    def probabilidade(self, dados: bytes) -> float:
        """Chance (0 a 1) de haver voz em um trecho de 512 amostras de 16 bits a 16 kHz."""
        audio = np.frombuffer(dados, dtype=np.int16).astype(np.float32) / 32768.0
        entrada = np.concatenate([self._contexto, audio])[np.newaxis, :]
        saida, self._h, self._c = self._sessao.run(None, {"input": entrada, "h": self._h, "c": self._c})
        self._contexto = audio[-CONTEXTO:]
        return float(saida.reshape(-1)[0])
