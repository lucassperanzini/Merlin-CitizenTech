"""Transforma texto em arquivo de áudio com os modelos do Piper."""
import io
import wave

import numpy as np
from piper import PiperVoice, SynthesisConfig

from merlin.config import EFEITOS_VOZ, PASTA_VOZES
from merlin.voz.efeitos import aplicar_efeito, cortar_silencio


class Sintetizador:
    def __init__(self):
        self._modelos = {}

    def precarregar(self, voz: str) -> None:
        self._obter_modelo(voz)

    def gerar(self, texto: str, voz: str, arquivo: str) -> None:
        """Sintetiza o texto em um WAV, sem o silêncio das pontas, aplicando o efeito quando a voz tiver um."""
        efeito = EFEITOS_VOZ.get(voz)
        configuracao = SynthesisConfig(length_scale=efeito.lentidao) if efeito else None
        memoria = io.BytesIO()
        with wave.open(memoria, "wb") as saida:
            self._obter_modelo(voz).synthesize_wav(texto, saida, syn_config=configuracao)
        memoria.seek(0)
        with wave.open(memoria, "rb") as entrada:
            taxa = entrada.getframerate()
            amostras = np.frombuffer(entrada.readframes(entrada.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        # Algumas vozes (Cadu, Jeff) começam com quase 1 s de silêncio: atrasava a resposta e confundia o
        # detector de interrupção, que tomava o silêncio como o eco da voz e depois cortava a própria fala
        amostras = cortar_silencio(amostras, taxa)
        self._gravar(arquivo, aplicar_efeito(amostras, taxa, efeito) if efeito else amostras, taxa)

    def _obter_modelo(self, voz):
        nome = EFEITOS_VOZ[voz].modelo if voz in EFEITOS_VOZ else voz
        if nome not in self._modelos:
            self._modelos[nome] = PiperVoice.load(str(PASTA_VOZES / f"{nome}.onnx"))
        return self._modelos[nome]

    @staticmethod
    def _gravar(arquivo, audio, taxa):
        with wave.open(arquivo, "wb") as saida:
            saida.setnchannels(1)
            saida.setsampwidth(2)
            saida.setframerate(taxa)
            saida.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
