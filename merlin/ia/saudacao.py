"""Cria uma saudação diferente a cada ativação; sem o Ollama ou com texto inválido, usa uma frase de reserva."""
import logging
import random

from merlin.ia.prompts import PROMPT_SAUDACAO, SAUDACOES_RESERVA, TEMAS_SAUDACAO

logger = logging.getLogger(__name__)

RECENTES_GUARDADAS = 3  # menos que as frases de reserva, para sempre sobrar uma
CARACTERES_PROIBIDOS = '{}[]<>*#_`"'
TAMANHO_MINIMO, TAMANHO_MAXIMO = 20, 170


def saudacao_valida(texto: str) -> bool:
    """O modelo às vezes devolve lixo, e a saudação é lida em voz alta sem passar por mais nada."""
    if not TAMANHO_MINIMO <= len(texto) <= TAMANHO_MAXIMO:
        return False
    return not any(c in texto for c in CARACTERES_PROIBIDOS) and "merlin" in texto.lower() and texto[-1] in ".?!"


class GeradorSaudacao:
    def __init__(self, cliente):
        self._cliente = cliente
        self._recentes = []

    def gerar(self) -> str:
        texto = self._pedir_ao_modelo()
        if not saudacao_valida(texto) or texto in self._recentes:
            texto = random.choice([s for s in SAUDACOES_RESERVA if s not in self._recentes])
        self._recentes.append(texto)
        del self._recentes[:-RECENTES_GUARDADAS]
        return texto

    def _pedir_ao_modelo(self) -> str:
        evitar = "\n".join(f"- {s}" for s in self._recentes) or "- nenhuma"
        pedido = PROMPT_SAUDACAO.format(tema=random.choice(TEMAS_SAUDACAO), evitar=evitar)
        try:
            resposta = self._cliente.perguntar(
                [{"role": "user", "content": pedido}],
                opcoes={"temperature": 0.8, "num_predict": 70},
            )
            return resposta.strip()
        except Exception as erro:
            logger.warning("[SAUDAÇÃO] %s", erro)
            return ""
