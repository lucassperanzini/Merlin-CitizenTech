"""Quando a frase não pede nenhuma ação, a IA simplesmente responde."""


class Conversar:
    def __init__(self, locutor, conversa):
        self._locutor = locutor
        self._conversa = conversa

    def __call__(self, intencao) -> None:
        self._locutor.falar(self._conversa.responder(intencao.comando) or "Desculpe, não entendi.")
