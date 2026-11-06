"""Todas as vozes disponíveis: as do Piper (config.VOZES_PIPER) mais as vozes próprias das personalidades."""
from merlin.config import VOZES_PIPER
from merlin.personalidades import PERSONALIDADES
from merlin.voz.efeitos import EfeitoVoz


def todas_as_vozes() -> dict[str, str]:
    """Rótulo mostrado nas configurações -> id da voz."""
    vozes = dict(VOZES_PIPER)
    for personalidade in PERSONALIDADES.values():
        for voz in personalidade.vozes_proprias:
            vozes[voz.rotulo] = voz.id
    return vozes


def efeito_da_voz(voz: str) -> EfeitoVoz | None:
    for personalidade in PERSONALIDADES.values():
        for propria in personalidade.vozes_proprias:
            if propria.id == voz:
                return propria.efeito
    return None
