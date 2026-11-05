"""Interpreta a resposta da pessoa a uma pergunta de confirmação. Só SIM autoriza a ação; o resto nunca age."""
import json
from enum import Enum

from merlin.ia.prompts import PROMPT_CONFIRMACAO


class RespostaConfirmacao(str, Enum):
    SIM = "sim"
    NAO = "nao"
    OUTRO = "outro"


ESQUEMA_CONFIRMACAO = {
    "type": "object",
    "properties": {"resposta": {"type": "string", "enum": [r.value for r in RespostaConfirmacao]}},
    "required": ["resposta"],
}


class ClassificadorConfirmacao:
    def __init__(self, cliente):
        self._cliente = cliente

    def classificar(self, pergunta: str, comando: str) -> RespostaConfirmacao:
        """Se a resposta do modelo vier inválida, nada é autorizado."""
        resposta = self._cliente.perguntar(
            [{"role": "system", "content": PROMPT_CONFIRMACAO.format(pergunta=pergunta)},
             {"role": "user", "content": comando}],
            formato=ESQUEMA_CONFIRMACAO,
            opcoes={"temperature": 0},
        )
        try:
            return RespostaConfirmacao(json.loads(resposta).get("resposta", RespostaConfirmacao.OUTRO))
        except (ValueError, AttributeError):
            return RespostaConfirmacao.OUTRO
