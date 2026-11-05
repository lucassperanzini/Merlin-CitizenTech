"""Efeitos sonoros aplicados sobre um áudio já sintetizado."""
import numpy as np

from merlin.config import EfeitoVoz

FREQUENCIA_TREMOR = 5.5
PICO_MAXIMO = 0.95


def aplicar_efeito(amostras: np.ndarray, taxa: int, efeito: EfeitoVoz) -> np.ndarray:
    """Recebe áudio em float (-1 a 1) e devolve o áudio com tom, tremor e eco aplicados."""
    audio = _mudar_tom(amostras, efeito.tom)
    audio = _aplicar_tremor(audio, taxa, efeito.tremor)
    saida = _aplicar_eco(audio, taxa, efeito.eco)
    pico = np.max(np.abs(saida))
    return saida * (PICO_MAXIMO / pico) if pico > PICO_MAXIMO else saida


def _mudar_tom(amostras, tom):
    # Esticar o áudio e tocar na mesma taxa deixa a voz mais grave
    posicoes = np.linspace(0, len(amostras) - 1, int(len(amostras) / tom))
    return np.interp(posicoes, np.arange(len(amostras)), amostras)


def _aplicar_tremor(audio, taxa, intensidade):
    tempo = np.arange(len(audio)) / taxa
    return audio * (1 - intensidade * (0.5 + 0.5 * np.sin(2 * np.pi * FREQUENCIA_TREMOR * tempo)))


def _aplicar_eco(audio, taxa, intensidade):
    # Duas reflexões curtas, mais a cauda final para o eco não ser cortado
    reflexoes = [(0.09, intensidade), (0.17, intensidade * 0.55)]
    cauda = int(max(atraso for atraso, _ in reflexoes) * taxa)
    saida = np.concatenate([audio, np.zeros(cauda)])
    for atraso, ganho in reflexoes:
        inicio = int(atraso * taxa)
        saida[inicio:inicio + len(audio)] += audio * ganho
    return saida
