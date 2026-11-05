"""Base das falas criadas pela IA no estilo do mago. Sem o Ollama ou com texto inválido, usa uma frase de reserva."""
import logging
import random
import re

logger = logging.getLogger(__name__)

RECENTES_GUARDADAS = 3  # menos que as frases de reserva, para sempre sobrar uma
CARACTERES_PROIBIDOS = '{}[]<>*#_`"'
TAMANHO_MINIMO, TAMANHO_MAXIMO = 20, 170
# O modelo já gerou "vou mijar perto do caldeirão": nada disso pode ser lido em voz alta
PALAVRAS_PROIBIDAS = re.compile(
    r"\b(?:mij\w*|urin\w*|cag\w*|merd\w*|bost\w*|porra\w*|caralh\w*|fod\w*|fud\w*|put[ao]s?|viad\w*|cu|bund\w*|pau|peid\w*)\b",
    re.IGNORECASE,
)


def frase_valida(texto: str) -> bool:
    """O modelo às vezes devolve lixo, e a frase é lida em voz alta sem passar por mais nada."""
    if not TAMANHO_MINIMO <= len(texto) <= TAMANHO_MAXIMO or PALAVRAS_PROIBIDAS.search(texto):
        return False
    return not any(c in texto for c in CARACTERES_PROIBIDOS) and texto[-1] in ".?!"


class GeradorFraseMago:
    PROMPT = ""  # recebe {tema}, {evitar} e, se usar, {exemplo}
    RESERVAS = ()
    TEMAS = ()
    EXEMPLOS = ("",)  # sortear o exemplo evita que todas as frases sigam o mesmo molde

    def __init__(self, cliente):
        self._cliente = cliente
        self._recentes = []

    def gerar(self) -> str:
        texto = self._pedir_ao_modelo()
        if not self.valida(texto) or texto in self._recentes or texto in self.EXEMPLOS:
            texto = random.choice([f for f in self.RESERVAS if f not in self._recentes])
        self._recentes.append(texto)
        del self._recentes[:-RECENTES_GUARDADAS]
        return texto

    def valida(self, texto: str) -> bool:
        return frase_valida(texto)

    def _pedir_ao_modelo(self) -> str:
        evitar = "\n".join(f"- {f}" for f in self._recentes) or "- nenhuma"
        pedido = self.PROMPT.format(tema=random.choice(self.TEMAS), evitar=evitar, exemplo=random.choice(self.EXEMPLOS))
        try:
            resposta = self._cliente.perguntar(
                [{"role": "user", "content": pedido}],
                opcoes={"temperature": 0.8, "num_predict": 70},
            )
            return resposta.strip()
        except Exception as erro:
            logger.warning("[FRASE DO MAGO] %s", erro)
            return ""
