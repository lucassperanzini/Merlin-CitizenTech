"""Abre programas instalados. Se não encontrar, avisa e procura na internet."""
import difflib

from AppOpener import give_appnames, open as abrir_app

from merlin.config import APELIDOS_PROGRAMAS

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
    def __init__(self, locutor, pesquisa):
        self._locutor = locutor
        self._pesquisa = pesquisa

    def __call__(self, intencao) -> str:
        nome = intencao.alvo
        programa = encontrar_programa(nome, [str(p).lower() for p in give_appnames()])
        if not programa:
            self._locutor.falar(f"Não encontrei o programa {nome} instalado. Vou procurar na internet.")
            return self._pesquisa.pesquisar(nome)
        try:
            self._locutor.falar(f"Abrindo {programa}.")
            abrir_app(programa, output=False)
            return f"Sucesso: {programa} foi aberto."
        except Exception as erro:
            self._locutor.falar(f"Não consegui abrir {programa}.")
            return f"Erro ao abrir {programa}: {erro}"
