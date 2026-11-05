"""Separa uma frase em tarefas independentes, como "abre o chrome e pesquisa gatos"."""
import json
import logging
import re

from merlin.ia.prompts import PROMPT_DIVISAO
from merlin.texto import normalizar

logger = logging.getLogger(__name__)

# Sem um destes conectivos só há uma tarefa, e a consulta à IA é evitada
CONECTIVOS = re.compile(r",|\b(?:e|depois|seguida|a[ií]|tamb[eé]m|ent[aã]o)\b", re.IGNORECASE)

ESQUEMA_DIVISAO = {
    "type": "object",
    "properties": {"tarefas": {"type": "array", "items": {"type": "string"}}},
    "required": ["tarefas"],
}


def _palavras(texto: str) -> set[str]:
    return {normalizar(p) for p in texto.split()} - {""}


class DivisorTarefas:
    def __init__(self, cliente):
        self._cliente = cliente

    def dividir(self, comando: str) -> list[str]:
        """Devolve as tarefas em ordem. Em qualquer dúvida, a frase segue inteira, como uma tarefa só."""
        if not CONECTIVOS.search(comando):
            return [comando]
        resposta = self._cliente.perguntar(
            [{"role": "system", "content": PROMPT_DIVISAO}, {"role": "user", "content": comando}],
            formato=ESQUEMA_DIVISAO,
            opcoes={"temperature": 0},
        )
        try:
            tarefas = [str(t).strip(" ,.") for t in json.loads(resposta).get("tarefas", [])]
        except (ValueError, AttributeError, TypeError):
            return [comando]
        tarefas = [t for t in tarefas if t]
        return tarefas if self._valida(tarefas, comando) else [comando]

    @staticmethod
    def _valida(tarefas, comando) -> bool:
        """Não aceita palavras que a pessoa não disse: o modelo não pode inventar uma tarefa."""
        if not tarefas:
            return False
        ditas = _palavras(comando)
        for tarefa in tarefas:
            if not _palavras(tarefa) <= ditas:
                logger.warning("[DIVISÃO] Descartada por conter palavras não ditas: %s", tarefa)
                return False
        return True
