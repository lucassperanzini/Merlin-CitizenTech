"""Gera recursos/alarme.wav, o alarme dos focos de incêndio em alerta. Para mudar o som, ajuste e rode de novo:

    .venv\\Scripts\\python.exe ferramentas\\gerar_som_alarme.py

Um ciclo curto de bipes alternando agudo e grave, como uma sirene de emergência. O Merlin repete o ciclo,
com uma pausa entre um e outro, até a pessoa abrir os alertas (merlin/voz/alarme.py).
"""
import wave
from pathlib import Path

import numpy as np

TAXA = 44100
SAIDA = Path(__file__).resolve().parent.parent / "recursos" / "alarme.wav"

AGUDO, GRAVE = 1046.5, 784.0  # dó e sol: um intervalo que chama atenção sem ser estridente
BIPES = (AGUDO, GRAVE, AGUDO, GRAVE)
DURACAO_BIPE = 0.17
INTERVALO = 0.06
FIM = 0.12  # silêncio no fim, para o ciclo não emendar seco no próximo
PICO = 0.8


def bipe(frequencia):
    tempo = np.arange(int(DURACAO_BIPE * TAXA)) / TAXA
    # Onda quase quadrada (a fundamental e algumas harmônicas ímpares): corta o barulho do ambiente
    onda = sum(np.sin(2 * np.pi * frequencia * n * tempo) / n for n in (1, 3, 5, 7))
    # Ataque e queda curtos: sem estalo no começo e no fim de cada bipe
    forma = np.clip(tempo / 0.008, 0, 1) * np.clip((DURACAO_BIPE - tempo) / 0.02, 0, 1)
    return onda * forma


def gerar():
    pausa = np.zeros(int(INTERVALO * TAXA))
    partes = []
    for frequencia in BIPES:
        partes += [bipe(frequencia), pausa]
    partes.append(np.zeros(int(FIM * TAXA)))
    mono = np.concatenate(partes)
    return mono * (PICO / np.max(np.abs(mono)))


def salvar(mono):
    estereo = np.stack([mono, mono], axis=1)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(SAIDA), "wb") as arquivo:
        arquivo.setnchannels(2)
        arquivo.setsampwidth(2)
        arquivo.setframerate(TAXA)
        arquivo.writeframes((estereo * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    salvar(gerar())
    print(f"Alarme criado em {SAIDA}")
