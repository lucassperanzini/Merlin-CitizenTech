"""Decide onde começa e termina cada frase, trecho a trecho, pela chance de haver voz humana em cada um.

Começa quando há voz de verdade por alguns trechos seguidos; termina quando a voz para por PAUSA_FIM_FRASE.
Guarda um pouco do áudio de antes do início, para não cortar a primeira sílaba."""
from collections import deque

from merlin.audio.detector_voz import AMOSTRAS, TAXA

DURACAO_TRECHO = AMOSTRAS / TAXA  # 0,032 s
LIMIAR_VOZ = 0.5  # a partir daqui, o trecho conta como voz
LIMIAR_SILENCIO = 0.35  # abaixo daqui, conta como pausa (entre os dois, mantém o que estava)
VOZ_PARA_COMECAR = 0.096  # segundos de voz seguida para abrir uma frase: estalos e tosses curtas não abrem
VOZ_MINIMA = 0.25  # frases com menos voz que isso são descartadas
ANTES_DO_INICIO = 0.3  # segundos guardados de antes da voz começar
FOLGA_FINAL = 0.15  # silêncio mantido no fim da frase


def trechos(segundos: float) -> int:
    return max(1, round(segundos / DURACAO_TRECHO))


class Segmentador:
    def __init__(self, pausa_fim: float, duracao_maxima: float):
        self._pausa_fim = trechos(pausa_fim)
        self._maximo = trechos(duracao_maxima)
        self._para_comecar = trechos(VOZ_PARA_COMECAR)
        self._voz_minima = trechos(VOZ_MINIMA)
        self._folga_final = trechos(FOLGA_FINAL)
        self._antes = deque(maxlen=trechos(ANTES_DO_INICIO))
        self._reiniciar()

    @property
    def ouvindo_frase(self) -> bool:
        return self._frase is not None

    def adicionar(self, dados: bytes, chance_voz: float) -> bytes | None:
        """Recebe um trecho e a chance de ter voz nele. Devolve o áudio da frase quando ela termina."""
        voz = chance_voz >= LIMIAR_VOZ
        silencio = chance_voz < LIMIAR_SILENCIO
        if self._frase is None:
            return self._esperar_comeco(dados, voz)

        self._frase.append(dados)
        if voz:
            self._voz += 1
            self._silencio = 0
        elif silencio:
            self._silencio += 1
        if self._silencio >= self._pausa_fim or len(self._frase) >= self._maximo:
            return self._terminar()
        return None

    def descartar(self) -> None:
        """Joga fora a frase em andamento (por exemplo, quando o microfone é silenciado)."""
        self._antes.clear()
        self._reiniciar()

    def _esperar_comeco(self, dados, voz):
        self._antes.append(dados)
        self._seguidos = self._seguidos + 1 if voz else 0
        if self._seguidos >= self._para_comecar:
            self._frase = list(self._antes)
            self._voz = self._seguidos
            self._silencio = 0
            self._antes.clear()
        return None

    def _terminar(self):
        frase, voz, silencio = self._frase, self._voz, self._silencio
        self._reiniciar()
        if voz < self._voz_minima:
            return None
        # Tira a pausa final (ela só servia para saber que a pessoa terminou), deixando uma folga para o Whisper
        sobra = max(0, silencio - self._folga_final)
        return b"".join(frase[:len(frase) - sobra])

    def _reiniciar(self):
        self._frase = None
        self._seguidos = 0
        self._voz = 0
        self._silencio = 0
