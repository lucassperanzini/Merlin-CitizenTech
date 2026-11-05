"""Abre programas instalados. Se não encontrar, avisa e procura na internet."""
import difflib

from AppOpener import give_appnames, open as abrir_app

from merlin.config import APELIDOS_PROGRAMAS
from merlin.nucleo.resposta import Resultado
from merlin.texto import com_artigo

SEMELHANCA_MINIMA = 0.6


def encontrar_programa(nome: str, instalados: list[str]) -> str | None:
    """Nome do programa instalado que corresponde ao pedido, ou None. O AppOpener não avisa quando não acha."""
    pedido = nome.strip().lower()
    pedido = APELIDOS_PROGRAMAS.get(pedido, pedido)
    if pedido in instalados:
        return pedido
    parecidos = difflib.get_close_matches(pedido, instalados, n=1, cutoff=SEMELHANCA_MINIMA)
    return parecidos[0] if parecidos else None


class AbrirPrograma:
    def __init__(self, pesquisa):
        self._pesquisa = pesquisa

    def __call__(self, intencao) -> Resultado:
        nome = intencao.alvo
        programa = encontrar_programa(nome, [str(p).lower() for p in give_appnames()])
        if not programa:
            self._pesquisa.abrir_no_navegador(nome)
            return Resultado(f"não encontrei o programa {nome} instalado, então pesquisei na internet",
                             registro=f"Não instalado: {nome}")
        try:
            abrir_app(programa, output=False)
        except Exception as erro:
            return Resultado(f"não consegui abrir {com_artigo(programa)}", registro=f"Erro ao abrir {programa}: {erro}")
        return Resultado(f"abri {com_artigo(programa)}", registro=f"Aberto: {programa}")
