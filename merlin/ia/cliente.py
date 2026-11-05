"""Único ponto de contato com o Ollama. Para trocar de provedor de IA, só este arquivo muda."""
import ollama


class ClienteIA:
    def __init__(self, modelo: str):
        self._modelo = modelo

    def perguntar(self, mensagens: list, formato: dict | None = None, opcoes: dict | None = None) -> str:
        """Envia as mensagens e devolve o texto da resposta. Erros de conexão chegam a quem chamou."""
        parametros = {}
        if formato:
            parametros["format"] = formato
        if opcoes:
            parametros["options"] = opcoes
        resposta = ollama.chat(model=self._modelo, messages=mensagens, **parametros)
        return resposta["message"]["content"] or ""
