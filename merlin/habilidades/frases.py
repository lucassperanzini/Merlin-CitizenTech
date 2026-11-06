"""Expressões usadas pelas regras de mais de uma habilidade."""
import re

# O que pode vir antes do verbo numa ordem: "por favor, abre…", "você pode clicar…", "quero que você feche…"
INICIO_DA_FRASE = (r"^(?:por favor,?\s+|agora\s+|e\s+|(?:voc[eê]\s+)?pode\s+|"
                   r"(?:eu\s+)?(?:quero|preciso)\s+que\s+(?:voc[eê]\s+)?)*")

PERGUNTA = re.compile(
    INICIO_DA_FRASE + r"(?:como|onde|qual|quais|o que|oque|por ?que|cad[eê]|ser[aá] que|d[aá] pra|tem como)\b",
    re.IGNORECASE,
)


def comeca_com(verbos: str) -> re.Pattern:
    """Uma ordem que começa por um destes verbos (alternativas de regex separadas por |)."""
    return re.compile(INICIO_DA_FRASE + rf"(?:{verbos})\b", re.IGNORECASE)
