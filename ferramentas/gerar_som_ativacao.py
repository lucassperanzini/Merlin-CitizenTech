"""Gera recursos/ativacao.wav, o som de ativação do Merlin. Para mudar o som, ajuste os valores e rode de novo:

    .venv\\Scripts\\python.exe ferramentas\\gerar_som_ativacao.py
"""
import wave
from pathlib import Path

import numpy as np

TAXA = 44100
DURACAO = 1.5
SAIDA = Path(__file__).resolve().parent.parent / "recursos" / "ativacao.wav"

# Arpejo de lá maior subindo: (frequência em Hz, início em segundos, volume)
NOTAS = [(440.0, 0.00, 0.55), (659.3, 0.09, 0.50), (880.0, 0.18, 0.50), (1108.7, 0.27, 0.42), (1318.5, 0.36, 0.42)]
PARCIAIS_DO_SINO = [(1.0, 1.0), (2.0, 0.35), (2.76, 0.18), (5.4, 0.06)]  # múltiplos não inteiros soam como metal
GRAVE = 110.0
BRILHOS = 26
ECOS = [(0.11, 0.30), (0.19, 0.22), (0.29, 0.15), (0.43, 0.09)]
PICO = 0.7


def sino(frequencia, inicio, volume, tempo):
    ativo = tempo >= inicio
    t = np.where(ativo, tempo - inicio, 0.0)
    ataque = np.clip(t / 0.004, 0, 1)  # evita o estalo no início da nota
    som = np.zeros_like(tempo)
    for multiplo, peso in PARCIAIS_DO_SINO:
        # Os parciais agudos somem mais rápido, como em um sino de verdade
        som += peso * np.sin(2 * np.pi * frequencia * multiplo * t) * np.exp(-t * (3.2 + multiplo * 1.3))
    return ativo * volume * ataque * som


def base_grave(tempo):
    """Uma onda quente e discreta embaixo do arpejo."""
    envelope = np.clip(tempo / 0.25, 0, 1) * np.exp(-np.maximum(tempo - 0.25, 0) * 3.0)
    return 0.16 * envelope * (np.sin(2 * np.pi * GRAVE * tempo) + 0.5 * np.sin(2 * np.pi * GRAVE * 1.5 * tempo))


def brilhos(tempo, gerador):
    """Pequenas faíscas agudas depois do arpejo, o toque de magia."""
    som = np.zeros_like(tempo)
    for _ in range(BRILHOS):
        inicio = gerador.uniform(0.25, 0.95)
        frequencia = gerador.uniform(2600, 6200)
        som += sino(frequencia, inicio, gerador.uniform(0.02, 0.05), tempo)
    return som


def aplicar_ecos(som):
    saida = som.copy()
    for atraso, ganho in ECOS:
        amostras = int(atraso * TAXA)
        saida[amostras:] += som[:-amostras] * ganho
    return saida


def gerar():
    tempo = np.arange(int(DURACAO * TAXA)) / TAXA
    gerador = np.random.default_rng(11)
    esquerda = direita = base_grave(tempo)
    for i, (frequencia, inicio, volume) in enumerate(NOTAS):
        nota = sino(frequencia, inicio, volume, tempo)
        posicao = i / (len(NOTAS) - 1)  # o arpejo atravessa da esquerda para a direita
        esquerda = esquerda + nota * (1 - 0.5 * posicao)
        direita = direita + nota * (0.5 + 0.5 * posicao)
    esquerda = esquerda + brilhos(tempo, gerador)
    direita = direita + brilhos(tempo, gerador)

    estereo = np.stack([aplicar_ecos(esquerda), aplicar_ecos(direita)], axis=1)
    saida_suave = np.clip((DURACAO - tempo) / 0.25, 0, 1)[:, None]  # termina em silêncio, sem corte
    estereo = estereo * saida_suave
    return estereo * (PICO / np.max(np.abs(estereo)))


def salvar(estereo):
    with wave.open(str(SAIDA), "wb") as arquivo:
        arquivo.setnchannels(2)
        arquivo.setsampwidth(2)
        arquivo.setframerate(TAXA)
        arquivo.writeframes((estereo * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    salvar(gerar())
    print(f"Som criado em {SAIDA}")
