"""Todas as vozes disponíveis: as do Piper (config.VOZES_PIPER), as vozes próprias das personalidades e,
se a clonagem estiver instalada, as vozes clonadas (vozes/clonadas/)."""
from merlin.config import VOZES_PIPER
from merlin.personalidades import PERSONALIDADES
from merlin.voz.clonagem import clonagem_instalada, listar_vozes_clonadas
from merlin.voz.efeitos import EfeitoVoz


def todas_as_vozes() -> dict[str, str]:
    """Rótulo mostrado nas configurações -> id da voz."""
    vozes = dict(VOZES_PIPER)
    for personalidade in PERSONALIDADES.values():
        for voz in personalidade.vozes_proprias:
            vozes[voz.rotulo] = voz.id
    if clonagem_instalada():
        for voz in listar_vozes_clonadas():
            vozes[voz.rotulo] = voz.id
    return vozes


def efeito_da_voz(voz: str) -> EfeitoVoz | None:
    for personalidade in PERSONALIDADES.values():
        for propria in personalidade.vozes_proprias:
            if propria.id == voz:
                return propria.efeito
    return None
