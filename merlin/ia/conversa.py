"""Respostas livres da IA. Aqui ela só responde: as ações passam pelas intenções."""
from merlin.personalidades import PERSONALIDADE_PADRAO


class Conversa:
    def __init__(self, cliente, memoria, preferencias=None):
        self._cliente = cliente
        self._memoria = memoria
        self._preferencias = preferencias

    def responder(self, comando: str) -> str:
        """A conversa recente vai junto, para entender perguntas como "e a da Itália?"."""
        personalidade = self._preferencias.personalidade if self._preferencias else PERSONALIDADE_PADRAO
        return self._cliente.perguntar(
            [{"role": "system", "content": personalidade.prompt_conversa}, *self._memoria.como_mensagens(),
             {"role": "user", "content": comando}]
        )
