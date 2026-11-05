"""Quando o nome dito não bate com nenhum botão, a IA escolhe o mais provável entre os que existem de verdade."""
import json
import logging

from merlin.ia.prompts import PROMPT_ESCOLHA_BOTAO

logger = logging.getLogger(__name__)

NENHUM = "nenhum"
MAX_OPCOES = 80  # listas maiores deixam o modelo lento e confuso


class EscolhedorBotao:
    def __init__(self, cliente):
        self._cliente = cliente

    def escolher(self, pedido: str, nomes: list[str]) -> str | None:
        """Retorna um nome que está na lista, ou None. A resposta do modelo é restrita às opções existentes."""
        opcoes = list(dict.fromkeys(nomes))[:MAX_OPCOES]
        if not opcoes:
            return None
        esquema = {
            "type": "object",
            "properties": {"botao": {"type": "string", "enum": [*opcoes, NENHUM]}},
            "required": ["botao"],
        }
        lista = "\n".join(f"- {nome}" for nome in opcoes)
        try:
            resposta = self._cliente.perguntar(
                [{"role": "system", "content": PROMPT_ESCOLHA_BOTAO.format(botoes=lista)},
                 {"role": "user", "content": pedido}],
                formato=esquema,
                opcoes={"temperature": 0},
            )
            escolhido = json.loads(resposta).get("botao")
        except Exception as erro:
            logger.warning("[ESCOLHA DE BOTÃO] %s", erro)
            return None
        # O formato já restringe as opções, mas a regra final é do código: nome fora da lista não é aceito
        return escolhido if escolhido in opcoes else None
