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
ESPERA_NO_MUDO = 0.1  # segundos entre as olhadas no botão de mudo, com o microfone fechado
ESPERA_APOS_FALHA = 2  # segundos antes de tentar reabrir um microfone que não abriu (ex.: headset desconectado)


class Ouvinte:
    def __init__(self, estado, canal, transcritor, preferencias):
        self._preferencias = preferencias
        self._estado = estado
        self._canal = canal
        self._transcritor = transcritor
        self._recognizer = sr.Recognizer()
        self._microfone = None
        self._frases = queue.Queue()
        self._gravacao = None  # enquanto grava uma amostra de voz: os trechos vão para cá, e não viram comandos
        self._gravacao_pronta = threading.Event()
        self._trava_gravacao = threading.Lock()

    def calibrar(self) -> None:
        """Mede o ruído ambiente: o limiar de volume ainda serve para as ondas e para a interrupção da fala."""
        self._microfone = MicrofoneComMedidor(self._recognizer, self._estado, sample_rate=TAXA, chunk_size=AMOSTRAS)
        with self._microfone as fonte:
            logger.info("Calibrando o ruído ambiente...")
            self._recognizer.adjust_for_ambient_noise(fonte, duration=DURACAO_CALIBRAGEM)

    def escutar(self) -> None:
        threading.Thread(target=self._escutar, name="escuta", daemon=True).start()
        threading.Thread(target=self._transcrever_frases, name="transcricao", daemon=True).start()

    def gravar(self, segundos: float) -> bytes:
        """Grava do mesmo microfone da escuta (16 kHz, 16 bits). Durante a gravação nada é tratado como comando."""
        if self._microfone is None:
            raise RuntimeError("o microfone ainda não está pronto")
        if self._estado.microfone_desligado.is_set():
            raise RuntimeError("o microfone está no mudo. Ligue-o no botão da janela do assistente")
        trechos_necessarios = int(segundos * TAXA / AMOSTRAS)
        with self._trava_gravacao:
            self._gravacao, self._necessarios = [], trechos_necessarios
            self._gravacao_pronta.clear()
        self._gravacao_pronta.wait(segundos + 5)
        with self._trava_gravacao:
            trechos, self._gravacao = self._gravacao or [], None
        return b"".join(trechos)

    def _desviar_para_gravacao(self, dados) -> bool:
        with self._trava_gravacao:
            if self._gravacao is None:
                return False
            self._gravacao.append(dados)
            if len(self._gravacao) >= self._necessarios:
                self._gravacao_pronta.set()
            return True

    def _escutar(self):
        """No mudo, o microfone fica FECHADO: nenhum áudio chega ao programa (e o Windows deixa de mostrar o
        assistente como usando o microfone). Ao sair do mudo, ele é aberto de novo."""
        detector = DetectorVoz()
        segmentador = Segmentador(PAUSA_FIM_FRASE, LIMITE_FRASE)
        encerrando, mudo = self._estado.encerrando, self._estado.microfone_desligado
        while not encerrando.is_set():
            if mudo.is_set():
                encerrando.wait(ESPERA_NO_MUDO)
                continue
            try:
                with self._microfone as fonte:
                    logger.info("[MICROFONE] Aberto.")
                    self._ouvir_ate_o_mudo(fonte, detector, segmentador)
                if mudo.is_set():
                    logger.info("[MICROFONE] Fechado (mudo).")
            except Exception as erro:  # sem microfone, o assistente segue aberto e tenta de novo
                logger.error("[MICROFONE] Não consegui usar o microfone: %s", erro)
                encerrando.wait(ESPERA_APOS_FALHA)
            # O que estava pela metade quando o microfone fechou não vira comando
            detector.reiniciar()
            segmentador.descartar()

    def _ouvir_ate_o_mudo(self, fonte, detector, segmentador):
        while not self._estado.encerrando.is_set() and not self._estado.microfone_desligado.is_set():
            dados = fonte.stream.read(AMOSTRAS)
            if self._desviar_para_gravacao(dados):
                segmentador.descartar()  # a leitura da amostra não pode virar comando
                continue
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
        if self._estado.microfone_desligado.is_set():
            return  # uma frase de pouco antes do mudo, ainda na fila: não é transcrita
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
