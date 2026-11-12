"""As personalidades (assistentes) disponíveis. Todas são arquivos .json, no mesmo formato:

- original: recursos/assistentes_padrao/ (Merlin). Não podem ser excluídos pela interface, e
  "Restaurar original" volta para eles;
- configurador: assistentes_citizentech/, criados ou ajustados na aba Editor. Um .json com o id de um original é um ajuste
  dele (vale no lugar do original; apagar o arquivo restaura o padrão). Um id novo é um assistente novo.

PERSONALIDADES e NOMES_DO_ASSISTENTE são atualizados no lugar por recarregar(): quem importou os dois vê as mudanças.
"""
import json
import logging

from merlin.config import PASTA_ASSISTENTES, PASTA_ASSISTENTES_PADRAO, PERSONALIDADE_PADRAO_ID
from merlin.personalidades import armazenamento
from merlin.personalidades.base import ConjuntoFrases, Personalidade, VozPropria

__all__ = ["ConjuntoFrases", "Personalidade", "VozPropria", "PERSONALIDADES", "EMBUTIDAS", "NOMES_DO_ASSISTENTE",
           "personalidade_padrao", "recarregar"]

logger = logging.getLogger(__name__)


def _originais(pasta=PASTA_ASSISTENTES_PADRAO) -> dict[str, Personalidade]:
    """Os assistentes originais, na ordem do campo "ordem" de cada arquivo (é a ordem dos seletores)."""
    lidos = []
    for arquivo in sorted(pasta.glob("*.json")):
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        dados["id"] = arquivo.stem
        lidos.append((dados.get("ordem", 100), dados.get("nome", ""), armazenamento.de_dados(dados)))
    if not lidos:
        raise FileNotFoundError(f"Nenhum assistente original em {pasta}")
    return {p.id: p for _, _, p in sorted(lidos, key=lambda item: item[:2])}


EMBUTIDAS = _originais()  # os originais, sem ajustes: o "padrão" para restaurar (e que não podem ser excluídos)
PERSONALIDADES: dict[str, Personalidade] = {}
NOMES_DO_ASSISTENTE: set[str] = set()  # o classificador escreve um destes no "alvo" quando a frase é para o assistente


def recarregar(pasta=PASTA_ASSISTENTES) -> None:
    """Junta os originais com os do configurador (ajustes no lugar do original; novos depois, por nome)."""
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
