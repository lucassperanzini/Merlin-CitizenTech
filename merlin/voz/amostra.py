"""Prepara a amostra de uma voz a ser clonada: de um arquivo ou de uma gravação até o áudio limpo e curto."""
import numpy as np

TAXA_AMOSTRA = 24000  # a taxa usada pelo Qwen3-TTS
DURACAO_MINIMA = 3.0  # segundos de fala
DURACAO_MAXIMA = 15.0  # mais que isso não melhora a clonagem e deixa cada fala mais lenta
LIMITE_SILENCIO = 0.02  # fração do pico


class AmostraInvalida(ValueError):
    """A mensagem é mostrada à pessoa nas configurações."""


def carregar_arquivo(caminho: str) -> tuple[np.ndarray, int]:
    """WAV, MP3, M4A, OGG ou FLAC, em mono."""
    import librosa  # vem junto da instalação opcional da clonagem

    try:
        audio, taxa = librosa.load(caminho, sr=TAXA_AMOSTRA, mono=True)
    except Exception as erro:
        raise AmostraInvalida(f"Não consegui abrir esse arquivo de áudio ({erro.__class__.__name__}).") from erro
    return audio, taxa


def de_bytes_16bits(dados: bytes, taxa: int) -> tuple[np.ndarray, int]:
    return np.frombuffer(dados, dtype=np.int16).astype(np.float32) / 32768.0, taxa


def reamostrar(audio: np.ndarray, taxa: int, nova_taxa: int) -> np.ndarray:
    if taxa == nova_taxa or not len(audio):
        return audio.astype(np.float32)
    posicoes = np.arange(0, len(audio), taxa / nova_taxa)
    return np.interp(posicoes, np.arange(len(audio)), audio).astype(np.float32)


def preparar(audio: np.ndarray, taxa: int) -> tuple[np.ndarray, int]:
    """Tira o silêncio das pontas, limita a duração, normaliza o volume e converte para a taxa do modelo."""
    audio = reamostrar(np.asarray(audio, dtype=np.float32), taxa, TAXA_AMOSTRA)
    if not len(audio) or np.max(np.abs(audio)) < 1e-3:
        raise AmostraInvalida("A amostra está em silêncio. Verifique o microfone ou o arquivo.")
    audivel = np.flatnonzero(np.abs(audio) > np.max(np.abs(audio)) * LIMITE_SILENCIO)
    margem = int(0.1 * TAXA_AMOSTRA)
    audio = audio[max(0, audivel[0] - margem):audivel[-1] + margem]
    if len(audio) / TAXA_AMOSTRA < DURACAO_MINIMA:
        raise AmostraInvalida(f"A amostra tem menos de {DURACAO_MINIMA:.0f} segundos de fala. Fale um pouco mais.")
    audio = audio[:int(DURACAO_MAXIMA * TAXA_AMOSTRA)]
    return (audio / np.max(np.abs(audio)) * 0.9).astype(np.float32), TAXA_AMOSTRA


def para_16bits(audio: np.ndarray, taxa: int, nova_taxa: int = 16000) -> bytes:
    """Para o Whisper transcrever a amostra."""
    return (np.clip(reamostrar(audio, taxa, nova_taxa), -1, 1) * 32767).astype(np.int16).tobytes()
