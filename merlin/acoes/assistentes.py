"""Trocar de assistente (personalidade) pela lista no nome da bolinha."""
from merlin.personalidades import PERSONALIDADES


def trocar_personalidade(preferencias, memoria, canal, identificador: str) -> bool:
    """Passa a usar outra personalidade. Retorna False se ela não existe ou já é a atual."""
    if identificador not in PERSONALIDADES or identificador == preferencias.personalidade.id:
        return False
    preferencias.personalidade = identificador
    memoria.limpar()  # a conversa anterior era com a outra personalidade
    canal.personalidade()  # a janela troca o visual, a cor e o nome
    return True
