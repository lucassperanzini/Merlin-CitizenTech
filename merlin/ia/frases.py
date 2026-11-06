"""Falas curtas criadas pela IA (saudação, despedida), no estilo da personalidade escolhida.
Sem o Ollama ou com texto inválido, usa uma frase de reserva."""
import logging
import random
import re
from typing import Callable

from merlin.personalidades import ConjuntoFrases

logger = logging.getLogger(__name__)

RECENTES_GUARDADAS = 3  # menos que as frases de reserva, para sempre sobrar uma
CARACTERES_PROIBIDOS = '{}[]<>*#_`"'
TAMANHO_MINIMO = 20
# O modelo já gerou "vou mijar perto do caldeirão": nada disso pode ser lido em voz alta
PALAVRAS_PROIBIDAS = re.compile(
    r"\b(?:mij\w*|urin\w*|cag\w*|merd\w*|bost\w*|porra\w*|caralh\w*|fod\w*|fud\w*|put[ao]s?|viad\w*|cu|bund\w*|pau|peid\w*)\b",
    re.IGNORECASE,
)
TRATAMENTOS = re.compile(r"\b(?:senhor|senhora|mestre|mestra|dama|servo|cavaleira|cortesão|rainha)\b", re.IGNORECASE)


def frase_valida(texto: str, tamanho_maximo: int = 170) -> bool:
    """O modelo às vezes devolve lixo, e a frase é lida em voz alta sem passar por mais nada."""
    if not TAMANHO_MINIMO <= len(texto) <= tamanho_maximo or PALAVRAS_PROIBIDAS.search(texto):
        return False
    return not any(c in texto for c in CARACTERES_PROIBIDOS) and texto[-1] in ".?!"


def valida_para(texto: str, conjunto: ConjuntoFrases) -> bool:
    if not frase_valida(texto, conjunto.tamanho_maximo):
        return False
    if conjunto.exige_nome and conjunto.exige_nome not in texto.lower():
        return False
    if conjunto.sem_perguntas and "?" in texto:
        return False  # quem se despede não pode ficar esperando resposta
    return not (conjunto.proibir_tratamentos and TRATAMENTOS.search(texto))


class GeradorFrases:
    """Lê o conjunto a cada fala, para seguir a personalidade escolhida no momento."""

    def __init__(self, cliente, conjunto: Callable[[], ConjuntoFrases]):
        self._cliente = cliente
        self._conjunto = conjunto
        self._recentes = []

    def gerar(self) -> str:
        conjunto = self._conjunto()
        texto = self._pedir_ao_modelo(conjunto)
        if not valida_para(texto, conjunto) or texto in self._recentes or texto in conjunto.exemplos:
            texto = random.choice([f for f in conjunto.reservas if f not in self._recentes])
        self._recentes.append(texto)
        del self._recentes[:-RECENTES_GUARDADAS]
        return texto

    def _pedir_ao_modelo(self, conjunto) -> str:
        evitar = "\n".join(f"- {f}" for f in self._recentes) or "- nenhuma"
        pedido = conjunto.prompt.format(tema=random.choice(conjunto.temas), evitar=evitar,
                                        exemplo=random.choice(conjunto.exemplos))
        try:
            resposta = self._cliente.perguntar(
                [{"role": "user", "content": pedido}],
                opcoes={"temperature": 0.8, "num_predict": 70},
            )
            return resposta.strip()
        except Exception as erro:
            logger.warning("[FRASE] %s", erro)
            return ""
