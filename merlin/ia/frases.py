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
TAMANHO_MINIMO = 20  # para as frases que a IA inventa na hora: abaixo disso costuma ser lixo ("Olá", pedaços)
TAMANHO_MINIMO_ESCRITA = 4  # para as frases prontas escritas pela pessoa: "Bom dia!" é uma boa saudação
# O modelo já gerou "vou mijar perto do caldeirão": nada disso pode ser lido em voz alta
PALAVRAS_PROIBIDAS = re.compile(
    r"\b(?:mij\w*|urin\w*|cag\w*|merd\w*|bost\w*|porra\w*|caralh\w*|fod\w*|fud\w*|put[ao]s?|viad\w*|cu|bund\w*|pau|peid\w*)\b",
    re.IGNORECASE,
)
TRATAMENTOS = re.compile(r"\b(?:senhor|senhora|mestre|mestra|dama|servo|cavaleira|cortesão|rainha)\b", re.IGNORECASE)


OPCOES_POR_VEZ = 2  # quantas expressões típicas são oferecidas de cada vez (a IA usa no máximo uma)


def oferecer_expressoes(expressoes, frequencia, sorteio=random) -> list[str]:
    """Um modelo pequeno não controla a frequência: com as expressões sempre à vista, usava uma em quase toda frase.
    Então o código sorteia, pela frequência configurada no assistente, se esta frase recebe expressões e quais."""
    if not expressoes or sorteio.random() >= frequencia:
        return []
    return sorteio.sample(list(expressoes), min(OPCOES_POR_VEZ, len(expressoes)))


def motivo_frase_invalida(texto: str, tamanho_maximo: int = 170, tamanho_minimo: int = TAMANHO_MINIMO) -> str:
    """Por que a frase não pode ser lida em voz alta ("" se pode). O modelo às vezes devolve lixo, e a frase
    é lida sem passar por mais nada."""
    if len(texto) < tamanho_minimo:
        return f"é curta demais ({len(texto)} caracteres; o mínimo é {tamanho_minimo})"
    if len(texto) > tamanho_maximo:
        return f"é longa demais ({len(texto)} caracteres; o máximo é {tamanho_maximo})"
    proibidos = sorted({c for c in texto if c in CARACTERES_PROIBIDOS})
    if proibidos:
        return f"tem símbolos que não podem ser lidos em voz alta: {' '.join(proibidos)}"
    if PALAVRAS_PROIBIDAS.search(texto):
        return "tem uma palavra proibida"
    if texto[-1] not in ".?!":
        return "precisa terminar com ponto final, de exclamação ou de interrogação"
    return ""


def motivo_recusa(texto: str, conjunto: ConjuntoFrases, tamanho_minimo: int = TAMANHO_MINIMO) -> str:
    """Por que a frase não serve para este conjunto ("" se serve)."""
    motivo = motivo_frase_invalida(texto, conjunto.tamanho_maximo, tamanho_minimo)
    if motivo:
        return motivo
    if conjunto.exige_nome and conjunto.exige_nome not in texto.lower():
        return f"precisa conter o nome \"{conjunto.exige_nome}\""
    if conjunto.sem_perguntas and "?" in texto:
        return "não pode ter pergunta (quem se despede não fica esperando resposta)"
    if conjunto.proibir_tratamentos and TRATAMENTOS.search(texto):
        return "usa um tratamento proibido para este assistente (como senhor ou mestre)"
    return ""


def frase_valida(texto: str, tamanho_maximo: int = 170) -> bool:
    return not motivo_frase_invalida(texto, tamanho_maximo)


def valida_para(texto: str, conjunto: ConjuntoFrases) -> bool:
    return not motivo_recusa(texto, conjunto)


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
        opcoes = oferecer_expressoes(conjunto.expressoes, conjunto.frequencia_expressoes)
        if opcoes:  # nem sempre, e nunca uma imposta: dá variedade sem forçar uma que não cabe
            pedido += ("\nSe combinar com a frase, use uma destas expressões típicas, no sentido certo: "
                       + "; ".join(opcoes) + ". Se nenhuma combinar, não use.")
        try:
            resposta = self._cliente.perguntar(
                [{"role": "user", "content": pedido}],
                opcoes={"temperature": 0.8, "num_predict": 70},
            )
            return resposta.strip()
        except Exception as erro:
            logger.warning("[FRASE] %s", erro)
            return ""
