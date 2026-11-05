"""Pesquisa na internet ou abre um site no navegador."""
import os
from urllib.parse import quote_plus


def montar_url(termo: str) -> str:
    if termo.startswith("http"):
        return termo
    if ".com" in termo and " " not in termo:  # uma frase com espaços nunca é um endereço
        return f"https://{termo}"
    return f"https://www.google.com/search?q={quote_plus(termo)}"


class PesquisarWeb:
    def __init__(self, locutor):
        self._locutor = locutor

    def __call__(self, intencao) -> str:
        return self.pesquisar(intencao.alvo)

    def pesquisar(self, termo: str) -> str:
        self._locutor.falar(f"Pesquisando por {termo}.")
        os.startfile(montar_url(termo))
        return f"Sucesso: Pesquisa por '{termo}' realizada."
