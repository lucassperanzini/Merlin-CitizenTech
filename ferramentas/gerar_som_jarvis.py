"""Gera recursos/ativacao_jarvis.wav, o som de ativação do Jarvis. Para mudar o som, ajuste e rode de novo:

    .venv\\Scripts\\python.exe ferramentas\\gerar_som_jarvis.py
"""
import wave
from pathlib import Path

import numpy as np

TAXA = 44100
DURACAO = 1.1
SAIDA = Path(__file__).resolve().parent.parent / "recursos" / "ativacao_jarvis.wav"

VARREDURA = (260.0, 1180.0, 0.0, 0.42)  # de Hz, até Hz, início, duração: a energia subindo
BIPES = [(1568.0, 0.42, 0.07), (2093.0, 0.52, 0.11)]  # frequência, início, duração
ZUMBIDO = 98.0
PICO = 0.7


def envelope(tempo, inicio, duracao, ataque=0.006, queda=6.0):
    t = tempo - inicio
    dentro = (t >= 0) & (t <= duracao + 0.5)
    subida = np.clip(t / ataque, 0, 1)
    descida = np.where(t > duracao, np.exp(-(t - duracao) * queda * 4), 1.0)
    return dentro * subida * descida


def varredura(tempo):
    inicio_f, fim_f, inicio, duracao = VARREDURA
    t = np.clip(tempo - inicio, 0, duracao)
    # Frequência subindo de forma exponencial; a fase é a integral da frequência
    k = np.log(fim_f / inicio_f) / duracao
    fase = 2 * np.pi * inicio_f * (np.exp(k * t) - 1) / k
    som = np.sin(fase) + 0.3 * np.sin(2 * fase) + 0.12 * np.sin(3 * fase)
    return 0.32 * som * envelope(tempo, inicio, duracao, queda=3.0) * (0.4 + 0.6 * t / duracao)


def bipes(tempo):
    som = np.zeros_like(tempo)
    for frequencia, inicio, duracao in BIPES:
        t = tempo - inicio
        tom = np.sin(2 * np.pi * frequencia * t) + 0.25 * np.sin(2 * np.pi * frequencia * 2 * t)
        som += 0.28 * tom * envelope(tempo, inicio, duracao)
    return som


def zumbido(tempo):
    forma = np.clip(tempo / 0.15, 0, 1) * np.exp(-np.maximum(tempo - 0.5, 0) * 4)
    return 0.12 * forma * (np.sin(2 * np.pi * ZUMBIDO * tempo) + 0.4 * np.sin(2 * np.pi * ZUMBIDO * 2.01 * tempo))


def gerar():
    tempo = np.arange(int(DURACAO * TAXA)) / TAXA
    mono = varredura(tempo) + bipes(tempo) + zumbido(tempo)
    atraso = int(0.012 * TAXA)  # um lado um pouco atrasado dá sensação de espaço
    esquerda = mono
    direita = np.concatenate([np.zeros(atraso), mono[:-atraso]]) * 0.9 + mono * 0.1
    estereo = np.stack([esquerda, direita], axis=1)
    estereo *= np.clip((DURACAO - tempo) / 0.15, 0, 1)[:, None]  # termina em silêncio, sem corte
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
