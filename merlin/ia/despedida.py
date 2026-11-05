"""Despedidas diferentes a cada saída: ao ficar em espera e ao encerrar o programa."""
import re

from merlin.ia.frase_mago import GeradorFraseMago, frase_valida
from merlin.ia.prompts import (
    DESPEDIDAS_RESERVA,
    ENCERRAMENTOS_RESERVA,
    EXEMPLOS_DESPEDIDA,
    EXEMPLOS_ENCERRAMENTO,
    PROMPT_DESPEDIDA,
    PROMPT_ENCERRAMENTO,
    TEMAS_DESPEDIDA,
)


TAMANHO_MAXIMO = 120  # a despedida deve ser curta: a pessoa já quer ir embora
TRATAMENTOS_PROIBIDOS = re.compile(r"\b(?:senhor|senhora|mestre|mestra|dama|servo|cavaleira|cortesão|rainha)\b", re.IGNORECASE)


class _GeradorSemPerguntas(GeradorFraseMago):
    TEMAS = TEMAS_DESPEDIDA

    def valida(self, texto: str) -> bool:
        if not frase_valida(texto) or len(texto) > TAMANHO_MAXIMO:
            return False
        # Quem se despede não pode ficar esperando resposta, e o modelo tende a tratamentos estranhos
        return "?" not in texto and not TRATAMENTOS_PROIBIDOS.search(texto)


class GeradorDespedida(_GeradorSemPerguntas):
    PROMPT = PROMPT_DESPEDIDA
    RESERVAS = DESPEDIDAS_RESERVA
    EXEMPLOS = EXEMPLOS_DESPEDIDA


class GeradorEncerramento(_GeradorSemPerguntas):
    PROMPT = PROMPT_ENCERRAMENTO
    RESERVAS = ENCERRAMENTOS_RESERVA
    EXEMPLOS = EXEMPLOS_ENCERRAMENTO
