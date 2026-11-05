"""Abre programas instalados. Se não encontrar, avisa e procura na internet."""
import difflib

from AppOpener import give_appnames, open as abrir_app

from merlin.acoes import navegador
from merlin.config import APELIDOS_PROGRAMAS
from merlin.nucleo.resposta import Resultado
from merlin.texto import com_artigo

# Alta de propósito: com 0,6, "navegador" abria o Narrador e "navegador de internet" o Agendador de Tarefas
SEMELHANCA_MINIMA = 0.85


def encontrar_programa(nome: str, instalados: list[str]) -> str | None:
    """Nome do programa instalado que corresponde ao pedido, ou None. Na dúvida, None: abrir o programa errado
    é pior do que avisar que não encontrou."""
    pedido = nome.strip().lower()
    pedido = APELIDOS_PROGRAMAS.get(pedido, pedido)
    if pedido in instalados:
        return pedido

    # "chrome" é uma das palavras de "google chrome"
    por_palavra = [p for p in instalados if pedido in p.split()]
    if por_palavra:
        return por_palavra[0] if len(por_palavra) == 1 else None

    # Erros de transcrição, como "crome": comparados com cada palavra e com o nome inteiro, com rigor
    parecidos = {p for p in instalados
                 if difflib.get_close_matches(pedido, [p, *p.split()], n=1, cutoff=SEMELHANCA_MINIMA)}
    return parecidos.pop() if len(parecidos) == 1 else None


def resolver_nome(nome: str, instalados: list[str]) -> str | None:
    if navegador.e_navegador_generico(nome):
        padrao = navegador.navegador_padrao()
        return padrao.programa if padrao and padrao.programa in instalados else None
    return encontrar_programa(nome, instalados)


class AbrirPrograma:
    def __init__(self, pesquisa):
        self._pesquisa = pesquisa

    def __call__(self, intencao) -> Resultado:
        nome = intencao.alvo
        programa = resolver_nome(nome, [str(p).lower() for p in give_appnames()])
        if not programa:
            self._pesquisa.abrir_no_navegador(nome)
            return Resultado(f"não encontrei o programa {nome} instalado, então pesquisei na internet",
                             registro=f"Não instalado: {nome}")
        try:
            abrir_app(programa, output=False)
        except Exception as erro:
            return Resultado(f"não consegui abrir {com_artigo(programa)}", registro=f"Erro ao abrir {programa}: {erro}")
        return Resultado(f"abri {com_artigo(programa)}", registro=f"Aberto: {programa}")
