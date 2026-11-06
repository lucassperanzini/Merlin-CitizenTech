"""Escuta contínua em segundo plano: ouve enquanto há voz humana, e quando a voz para, transcreve a frase
e entrega à fila o que for para o assistente.

O microfone é lido em trechos de 32 ms; o detector de voz diz se há gente falando em cada um, e o segmentador
decide onde a frase começa e termina. A transcrição roda em outra thread, para a escuta não parar."""
import logging
import queue
import threading

import speech_recognition as sr

from merlin.audio.detector_voz import AMOSTRAS, TAXA, DetectorVoz
from merlin.audio.microfone import MicrofoneComMedidor
from merlin.audio.segmentador import Segmentador
from merlin.config import LIMITE_FRASE, PAUSA_FIM_FRASE
from merlin.interface.eventos import EstadoVisual
from merlin.texto import tem_palavra_ativacao

logger = logging.getLogger(__name__)

DURACAO_CALIBRAGEM = 2
LARGURA_AMOSTRA = 2  # 16 bits


class Ouvinte:
    def __init__(self, estado, canal, transcritor, preferencias):
        self._preferencias = preferencias
        self._estado = estado
        self._canal = canal
        self._transcritor = transcritor
        self._recognizer = sr.Recognizer()
        self._microfone = None
        self._frases = queue.Queue()

    def calibrar(self) -> None:
        """Mede o ruído ambiente: o limiar de volume ainda serve para as ondas e para a interrupção da fala."""
        self._microfone = MicrofoneComMedidor(self._recognizer, self._estado, sample_rate=TAXA, chunk_size=AMOSTRAS)
        with self._microfone as fonte:
            logger.info("Calibrando o ruído ambiente...")
            self._recognizer.adjust_for_ambient_noise(fonte, duration=DURACAO_CALIBRAGEM)

    def escutar(self) -> None:
        threading.Thread(target=self._escutar, name="escuta", daemon=True).start()
        threading.Thread(target=self._transcrever_frases, name="transcricao", daemon=True).start()

    def _escutar(self):
        detector = DetectorVoz()
        segmentador = Segmentador(PAUSA_FIM_FRASE, LIMITE_FRASE)
        with self._microfone as fonte:
            while not self._estado.encerrando.is_set():
                dados = fonte.stream.read(AMOSTRAS)
                try:
                    frase = segmentador.adicionar(dados, detector.probabilidade(dados))
                except Exception as erro:  # um trecho com problema não pode derrubar a escuta
                    logger.error("Erro no detector de voz: %s", erro)
                    detector.reiniciar()
                    segmentador.descartar()
                    continue
                if frase:
                    self._frases.put(sr.AudioData(frase, TAXA, LARGURA_AMOSTRA))

    def _transcrever_frases(self):
        while not self._estado.encerrando.is_set():
            try:
                audio = self._frases.get(timeout=0.5)
            except queue.Empty:
                continue
            self._ao_ouvir(audio)

    def _ao_ouvir(self, audio):
        if self._estado.ativo.is_set() and not self._estado.falando.is_set():
            self._canal.estado(EstadoVisual.PENSANDO)  # a frase terminou e está sendo transcrita
        try:
            personalidade = self._preferencias.personalidade
            frase = self._transcritor.transcrever(audio, personalidade.dica_vocabulario)
            if frase:
                logger.info("[OUVI]: %s", frase)
                if self._estado.ativo.is_set() or tem_palavra_ativacao(frase, personalidade.palavras_ativacao):
                    self._estado.fila_comandos.put(frase)
                    return
        except Exception as erro:
            logger.error("Erro no reconhecimento: %s", erro)
        if self._estado.ativo.is_set():
            self._canal.estado(EstadoVisual.OUVINDO)  # era só ruído: volta a ouvir
