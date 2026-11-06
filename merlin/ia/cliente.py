"""Único ponto de contato com o Ollama. Para trocar de provedor de IA, só este arquivo muda."""
import logging
from dataclasses import dataclass
from typing import Callable

import ollama

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModeloInstalado:
    nome: str
    tamanho_gb: float
    parametros: str  # como o Ollama informa, por exemplo "7.6B"


def listar_modelos() -> list[ModeloInstalado]:
    """Modelos instalados no Ollama. Lança erro se o Ollama não estiver rodando."""
    modelos = []
    for m in ollama.list().models:
        detalhes = getattr(m, "details", None)
        modelos.append(ModeloInstalado(m.model, round((m.size or 0) / 1e9, 1), getattr(detalhes, "parameter_size", "") or ""))
    return sorted(modelos, key=lambda m: m.nome)


class ClienteIA:
    def __init__(self, modelo: Callable[[], str]):
        """Recebe uma função que diz o modelo atual, para a troca nas configurações valer na próxima pergunta."""
        self._modelo = modelo

    def perguntar(self, mensagens: list, formato: dict | None = None, opcoes: dict | None = None) -> str:
        """Envia as mensagens e devolve o texto da resposta. Erros de conexão chegam a quem chamou."""
        parametros = {}
        if formato:
            parametros["format"] = formato
        if opcoes:
            parametros["options"] = opcoes
        # think=False: modelos que "pensam em voz alta" (qwen3, deepseek-r1) levariam de 7 a 15 s por resposta.
        # Os outros modelos ignoram a opção.
        resposta = ollama.chat(model=self._modelo(), messages=mensagens, think=False, **parametros)
        return resposta["message"]["content"] or ""

    def preaquecer(self) -> None:
        """Carrega o modelo na memória antes da primeira pergunta; a primeira resposta de um modelo novo é lenta."""
        try:
            ollama.chat(model=self._modelo(), messages=[{"role": "user", "content": "oi"}], think=False,
                        options={"num_predict": 1})
        except Exception as erro:
            logger.warning("[IA] Não consegui carregar o modelo %s: %s", self._modelo(), erro)
