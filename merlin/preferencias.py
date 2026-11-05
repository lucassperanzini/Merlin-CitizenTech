"""Escolhas da pessoa que precisam sobreviver ao fechamento do programa."""
import json
import logging
from pathlib import Path

from merlin.config import VOZ_PADRAO, VOZES

logger = logging.getLogger(__name__)


class Preferencias:
    def __init__(self, arquivo: Path):
        self._arquivo = arquivo
        self._dados = self._carregar()

    @property
    def voz(self) -> str:
        voz = self._dados.get("voz", VOZ_PADRAO)
        return voz if voz in VOZES.values() else VOZ_PADRAO

    @voz.setter
    def voz(self, voz: str) -> None:
        self._dados["voz"] = voz
        self._salvar()

    def _carregar(self) -> dict:
        try:
            return json.loads(self._arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _salvar(self) -> None:
        try:
            self._arquivo.write_text(json.dumps(self._dados, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as erro:
            logger.error("[CONFIG] Não consegui salvar: %s", erro)
