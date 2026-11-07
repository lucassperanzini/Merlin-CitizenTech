"""Transforma texto em arquivo de áudio: com o Piper (vozes prontas) ou, se a voz for clonada, com o motor de
clonagem. Se a voz clonada falhar, fala com a voz reserva do Piper: o assistente nunca fica mudo."""
import io
import logging
import threading
import wave

import numpy as np
from piper import PiperVoice, SynthesisConfig

from merlin.config import PASTA_VOZES, VOZ_RESERVA
from merlin.voz.catalogo import efeito_da_voz
from merlin.voz.clonagem import MotorClonagem, buscar_voz_clonada, e_clonada
from merlin.voz.efeitos import aplicar_efeito, cortar_silencio

logger = logging.getLogger(__name__)


class Sintetizador:
    def __init__(self, motor_clonagem=None):
        self._modelos = {}
        self._clonagem = motor_clonagem or MotorClonagem()

    def precarregar(self, voz: str) -> None:
        if e_clonada(voz):
            # Leva uns 17 s: carrega em segundo plano para o assistente já começar a escutar.
            # Se a primeira fala chegar antes, ela só espera o carregamento terminar.
            threading.Thread(target=self._precarregar_clonagem, name="carregar-clonagem", daemon=True).start()
            return
        self._obter_modelo(voz)

    def _precarregar_clonagem(self):
        try:
            self._clonagem.precarregar()
        except Exception as erro:
            logger.warning("[VOZ] Não consegui carregar a clonagem de voz (%s); vou usar a voz reserva.", erro)

    def esquecer_voz_clonada(self, voz: str) -> None:
        self._clonagem.esquecer(voz)

    def gerar(self, texto: str, voz: str, arquivo: str) -> None:
        """Sintetiza o texto em um WAV, sem o silêncio das pontas."""
        if e_clonada(voz):
            try:
                amostras, taxa = self._gerar_clonada(texto, voz)
                self._gravar(arquivo, cortar_silencio(amostras, taxa), taxa)
                return
            except Exception as erro:
                logger.warning("[VOZ] A voz clonada falhou (%s); falando com a voz reserva.", erro)
                voz = VOZ_RESERVA
        self._gerar_piper(texto, voz, arquivo)

    def _gerar_clonada(self, texto, voz):
        clonada = buscar_voz_clonada(voz)
        if clonada is None:
            raise LookupError(f"a voz {voz} não existe mais")
        return self._clonagem.gerar(texto, clonada)

    def _gerar_piper(self, texto, voz, arquivo):
        efeito = efeito_da_voz(voz)
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
        efeito = efeito_da_voz(voz)
        nome = efeito.modelo if efeito else voz
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
