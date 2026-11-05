"""Quando a frase não pede nenhuma ação, a IA simplesmente responde."""
from merlin.nucleo.resposta import Resultado


class Conversar:
    def __init__(self, conversa):
        self._conversa = conversa

    def __call__(self, intencao) -> Resultado:
        return Resultado(self._conversa.responder(intencao.comando) or "Desculpe, não entendi.", frase_completa=True)
