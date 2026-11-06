"""As personalidades do assistente, uma por arquivo nesta pasta.

Para criar uma nova: copie merlin.py ou jarvis.py com outro nome, troque os textos, a voz e o som, e pronto.
Ela é encontrada sozinha e aparece no seletor das configurações (na posição dada por ORDEM).
"""
import importlib
import pkgutil

from merlin.config import PERSONALIDADE_PADRAO_ID
from merlin.personalidades.base import ConjuntoFrases, Personalidade, VozPropria

__all__ = ["ConjuntoFrases", "Personalidade", "VozPropria", "PERSONALIDADES", "PERSONALIDADE_PADRAO",
           "NOMES_DO_ASSISTENTE"]


def _descobrir() -> dict[str, Personalidade]:
    modulos = []
    for info in pkgutil.iter_modules(__path__):
        if info.name == "base":
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


PERSONALIDADES = _descobrir()
PERSONALIDADE_PADRAO = PERSONALIDADES[PERSONALIDADE_PADRAO_ID]
# O classificador escreve um destes no "alvo" quando a frase é dirigida ao próprio assistente
NOMES_DO_ASSISTENTE = {p.id for p in PERSONALIDADES.values()}
