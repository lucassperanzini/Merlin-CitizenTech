"""Respostas livres da IA. Aqui ela só responde: as ações passam pelas intenções."""
from merlin.ia.prompts import PROMPT_CONVERSA


class Conversa:
    def __init__(self, cliente):
        self._cliente = cliente

    def responder(self, comando: str) -> str:
        return self._cliente.perguntar(
            [{"role": "system", "content": PROMPT_CONVERSA}, {"role": "user", "content": comando}]
        )
