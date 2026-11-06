"""Volume de um áudio ao longo do tempo, para a esfera pulsar junto com a fala."""
import wave

import numpy as np

PASSO = 0.05  # segundos entre dois valores


def envelope_do_audio(arquivo: str) -> list[float]:
    """Um valor de 0 a 1 a cada PASSO segundos, normalizado pelo trecho mais alto."""
    with wave.open(arquivo, "rb") as entrada:
        taxa, canais = entrada.getframerate(), entrada.getnchannels()
        amostras = np.frombuffer(entrada.readframes(entrada.getnframes()), dtype=np.int16).astype(np.float32)
    if canais > 1:
        amostras = amostras.reshape(-1, canais).mean(axis=1)
    tamanho = max(1, int(taxa * PASSO))
    blocos = len(amostras) // tamanho
    if blocos == 0:
        return []
    rms = np.sqrt(np.mean(np.square(amostras[:blocos * tamanho].reshape(blocos, tamanho)), axis=1))
    pico = float(rms.max())
    return [round(float(v), 3) for v in rms / pico] if pico > 0 else [0.0] * blocos
