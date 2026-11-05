"""Pesquisa na internet ou abre um site no navegador."""
import os
from urllib.parse import quote_plus

from merlin.nucleo.resposta import Resultado


def e_endereco(termo: str) -> bool:
    return termo.startswith("http") or (".com" in termo and " " not in termo)  # uma frase com espaços nunca é um endereço


def montar_url(termo: str) -> str:
    if termo.startswith("http"):
        return termo
    if e_endereco(termo):
        return f"https://{termo}"
    return f"https://www.google.com/search?q={quote_plus(termo)}"


class PesquisarWeb:
    def __call__(self, intencao) -> Resultado:
        termo = intencao.alvo
        self.abrir_no_navegador(termo)
        fala = f"abri o site {termo}" if e_endereco(termo) else f"pesquisei por {termo}"
        return Resultado(fala, registro=f"Navegador: {termo}")

    @staticmethod
    def abrir_no_navegador(termo: str) -> None:
        os.startfile(montar_url(termo))
