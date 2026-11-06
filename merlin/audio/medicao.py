"""Cálculos sobre o volume do áudio captado. Não depende de microfone, por isso é fácil de testar."""
import math

import numpy as np

from merlin.config import INTERROMPER_DURACAO, INTERROMPER_FATOR

DECIBEIS_ONDA_MAXIMA = 30
NIVEL_MINIMO_VOZ = 0.12


def volume(dados: bytes) -> float:
    """Volume (RMS) de um trecho de áudio de 16 bits."""
    amostras = np.frombuffer(dados, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(np.square(amostras)))) if amostras.size else 0.0


def calcular_nivel(dados: bytes, limiar: float) -> float:
    """Converte um trecho de áudio em um nível de 0 a 1; 0 = abaixo do limiar de voz."""
    if limiar <= 0:
        return 0.0
    razao = volume(dados) / limiar
    if razao <= 1:
        return 0.0
    decibeis = 20 * math.log10(razao)
    return min(1.0, NIVEL_MINIMO_VOZ + (1 - NIVEL_MINIMO_VOZ) * decibeis / DECIBEIS_ONDA_MAXIMA)


class DetectorInterrupcao:
    """Decide se a pessoa falou por cima do Merlin, comparando o som captado com o eco da própria voz dele."""

    # Aprende o eco durante 0,5 s de som AUDÍVEL. Contar desde o início da reprodução falhava quando a voz
    # começava em silêncio: o eco aprendido ficava quase zero e a própria fala parecia alguém interrompendo.
    APRENDIZADO = 0.5
    APRENDIZADO_MAXIMO = 1.5  # se nada audível chegar (caixas de som baixas ou fone), para de aprender aqui
    TOLERANCIA = 0.12  # pausas entre sílabas menores que isto não contam como silêncio
    QUEDA_DO_ECO = 0.998  # o eco medido baixa aos poucos, acompanhando trechos mais fracos da fala
    FOLGA_LIMIAR = 1.5

    def __init__(self):
        self.reiniciar()

    def reiniciar(self) -> None:
        self.inicio = self.audivel_desde = self.acima_desde = self.ultimo_acima = None
        self.eco = 0.0

    def analisar(self, som: float, limiar: float, agora: float) -> bool:
        if self.inicio is None:
            self.inicio = agora
        if self.audivel_desde is None and som > limiar:
            self.audivel_desde = agora
        if self._aprendendo(agora):
            self.eco = max(self.eco, som)
            return False
        if som > max(limiar * self.FOLGA_LIMIAR, self.eco * INTERROMPER_FATOR):
            if self.acima_desde is None:
                self.acima_desde = agora
            self.ultimo_acima = agora
            return agora - self.acima_desde >= INTERROMPER_DURACAO
        if self.acima_desde is not None and agora - self.ultimo_acima <= self.TOLERANCIA:
            return False  # pausa curta no meio da fala da pessoa
        self.acima_desde = None
        self.eco = max(som, self.eco * self.QUEDA_DO_ECO)
        return False

    def _aprendendo(self, agora) -> bool:
        if agora - self.inicio >= self.APRENDIZADO_MAXIMO:
            return False
        return self.audivel_desde is None or agora - self.audivel_desde < self.APRENDIZADO
