"""As personalidades (assistentes) disponíveis.

Duas origens:
- código: um arquivo por personalidade nesta pasta (merlin.py, jarvis.py), com os textos afinados à mão;
- configurador: arquivos .json em assistentes/, criados pela janela "Assistentes". Um .json com o id de uma
  personalidade do código é um ajuste dela (apagar o arquivo restaura o padrão).

PERSONALIDADES e NOMES_DO_ASSISTENTE são atualizados no lugar por recarregar(): quem importou os dois vê as mudanças.
"""
import importlib
import pkgutil

from merlin.config import PASTA_ASSISTENTES, PERSONALIDADE_PADRAO_ID
from merlin.personalidades import armazenamento
from merlin.personalidades.base import ConjuntoFrases, Personalidade, VozPropria

__all__ = ["ConjuntoFrases", "Personalidade", "VozPropria", "PERSONALIDADES", "EMBUTIDAS", "NOMES_DO_ASSISTENTE",
           "personalidade_padrao", "recarregar"]

NAO_SAO_PERSONALIDADES = {"base", "armazenamento", "modelo"}


def _do_codigo() -> dict[str, Personalidade]:
    modulos = []
    for info in pkgutil.iter_modules(__path__):
        if info.name in NAO_SAO_PERSONALIDADES:
            continue
        modulo = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(modulo, "PERSONALIDADE"):
            modulos.append(modulo)
    modulos.sort(key=lambda m: (getattr(m, "ORDEM", 100), m.PERSONALIDADE.nome))
    encontradas = {}
    for modulo in modulos:
        p = modulo.PERSONALIDADE
        if p.id in encontradas:
            raise ValueError(f"Duas personalidades com o id '{p.id}'")
        encontradas[p.id] = p
    return encontradas


EMBUTIDAS = _do_codigo()  # as do código, sem ajustes: o "padrão" para restaurar
PERSONALIDADES: dict[str, Personalidade] = {}
NOMES_DO_ASSISTENTE: set[str] = set()  # o classificador escreve um destes no "alvo" quando a frase é para o assistente


def recarregar(pasta=PASTA_ASSISTENTES) -> None:
    """Junta as do código com as do configurador (ajustes no lugar do original; novas depois, por nome)."""
    do_configurador = {p.id: p for p in armazenamento.carregar(pasta, EMBUTIDAS)}
    juntas = {i: do_configurador.get(i, p) for i, p in EMBUTIDAS.items()}
    juntas.update(sorted(((i, p) for i, p in do_configurador.items() if i not in EMBUTIDAS),
                         key=lambda item: item[1].nome.lower()))
    PERSONALIDADES.clear()
    PERSONALIDADES.update(juntas)
    NOMES_DO_ASSISTENTE.clear()
    NOMES_DO_ASSISTENTE.update(PERSONALIDADES)


def personalidade_padrao() -> Personalidade:
    return PERSONALIDADES.get(PERSONALIDADE_PADRAO_ID) or next(iter(PERSONALIDADES.values()))


recarregar()
