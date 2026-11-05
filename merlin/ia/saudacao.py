"""Saudação diferente a cada ativação."""
from merlin.ia.frase_mago import GeradorFraseMago, frase_valida
from merlin.ia.prompts import PROMPT_SAUDACAO, SAUDACOES_RESERVA, TEMAS_SAUDACAO


def saudacao_valida(texto: str) -> bool:
    return frase_valida(texto) and "merlin" in texto.lower()


class GeradorSaudacao(GeradorFraseMago):
    PROMPT = PROMPT_SAUDACAO
    RESERVAS = SAUDACOES_RESERVA
    TEMAS = TEMAS_SAUDACAO

    def valida(self, texto: str) -> bool:
        return saudacao_valida(texto)
