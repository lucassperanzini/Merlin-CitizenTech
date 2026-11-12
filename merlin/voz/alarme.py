"""Alarme dos focos de incêndio em alerta: toca em ciclos, com uma pausa entre eles, até a pessoa abrir os alertas.

- Nunca toca por cima da voz do Merlin: espera ele terminar de falar (e a fala do alerta pausa o alarme antes).
- O microfone fica mudo durante cada ciclo, como no som de ativação, para o alarme não virar "comando".
"""
import logging
import threading
import time

import pygame

from merlin.config import ARQ_ALARME, PAUSA_ALARME, VOLUME_ALARME

logger = logging.getLogger(__name__)

ESPERA = 0.1  # segundos entre as conferências do laço


def _carregar_som(arquivo):
    pygame.mixer.init()
    som = pygame.mixer.Sound(str(arquivo))
    som.set_volume(VOLUME_ALARME)
    return som


class Alarme:
    def __init__(self, estado, arquivo=ARQ_ALARME, pausa=PAUSA_ALARME, carregar=_carregar_som):
        self._estado = estado
        self._arquivo = arquivo
        self._pausa = pausa
        self._carregar = carregar
        self._som = None
        self._canal = None
        self._ligado = threading.Event()
        self._pausado = threading.Event()  # a fala do alerta segura o alarme enquanto fala
        self._tocando_ate = 0.0
        self._thread = None
        self._trava = threading.Lock()

    @property
    def ligado(self) -> bool:
        return self._ligado.is_set()

    def tocar(self) -> None:
        """Liga o alarme (se já estiver tocando, continua do jeito que está)."""
        if self._ligado.is_set():
            return
        if self._som is None:
            try:
                self._som = self._carregar(self._arquivo)
            except Exception as erro:  # sem caixa de som ou sem o arquivo: o aviso visual e a fala continuam
                logger.warning("[ALARME] Não consegui carregar o alarme (%s): %s", self._arquivo, erro)
                return
        self._ligado.set()
        logger.info("[ALARME] Tocando até alguém abrir os alertas.")
        self._thread = threading.Thread(target=self._laco, name="alarme", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        if not self._ligado.is_set():
            return
        self._ligado.clear()
        with self._trava:
            if self._canal is not None:
                self._canal.stop()
            self._canal = None
            self._tocando_ate = 0.0
        logger.info("[ALARME] Desligado: os alertas foram vistos.")

    def pausar(self, limite: float = 3.0) -> None:
        """Segura o próximo ciclo e espera o atual terminar (até o limite): a fala do alerta entra limpa."""
        self._pausado.set()
        fim = time.monotonic() + limite
        while time.time() < self._tocando_ate and time.monotonic() < fim:
            time.sleep(0.02)

    def retomar(self) -> None:
        self._pausado.clear()

    def _pode_tocar(self) -> bool:
        return (self._ligado.is_set() and not self._pausado.is_set() and not self._estado.falando.is_set()
                and not self._estado.encerrando.is_set())

    def _laco(self) -> None:
        proximo = 0.0  # o primeiro ciclo toca na hora
        while self._ligado.is_set() and not self._estado.encerrando.is_set():
            if time.time() >= proximo and self._pode_tocar():
                duracao = self._som.get_length()
                with self._trava:
                    if not self._ligado.is_set():
                        break
                    self._estado.silenciar_microfone(duracao + 0.2)
                    self._tocando_ate = time.time() + duracao
                    self._canal = self._som.play()
                proximo = time.time() + duracao + self._pausa
            time.sleep(ESPERA)
