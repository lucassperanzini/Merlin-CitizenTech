"""Respostas livres da IA. Aqui ela só responde: as ações passam pelas intenções."""
from merlin.ia.prompts import PROMPT_CONVERSA


class Conversa:
    def __init__(self, cliente, memoria):
        self._cliente = cliente
        self._memoria = memoria

    def responder(self, comando: str) -> str:
        """A conversa recente vai junto, para entender perguntas como "e a da Itália?"."""
        return self._cliente.perguntar(
            [{"role": "system", "content": PROMPT_CONVERSA}, *self._memoria.como_mensagens(),
             {"role": "user", "content": comando}]
        )
