"""Escolhas da pessoa que precisam sobreviver ao fechamento do programa."""
import json
import logging
from pathlib import Path

from merlin.config import MODELO_IA
from merlin.personalidades import PERSONALIDADES, Personalidade, personalidade_padrao
from merlin.voz.catalogo import todas_as_vozes

logger = logging.getLogger(__name__)


class Preferencias:
    """Guarda a personalidade escolhida e a voz de cada personalidade separadamente."""

    def __init__(self, arquivo: Path):
        self._arquivo = arquivo
        self._dados = self._carregar()
        self._migrar_formato_antigo()

    @property
    def personalidade(self) -> Personalidade:
        return PERSONALIDADES.get(self._dados.get("personalidade")) or personalidade_padrao()

    @personalidade.setter
    def personalidade(self, identificador: str) -> None:
        if identificador in PERSONALIDADES:
            self._dados["personalidade"] = identificador
            self._salvar()

    @property
    def voz(self) -> str:
        """A voz da personalidade atual."""
        personalidade = self.personalidade
        voz = self._dados.get("vozes", {}).get(personalidade.id, personalidade.voz_padrao)
        return voz if voz in todas_as_vozes().values() else personalidade.voz_padrao

    @voz.setter
    def voz(self, voz: str) -> None:
        self._dados.setdefault("vozes", {})[self.personalidade.id] = voz
        self._salvar()

    @property
    def modelo_ia(self) -> str:
        return self._dados.get("modelo_ia") or MODELO_IA

    @modelo_ia.setter
    def modelo_ia(self, modelo: str) -> None:
        self._dados["modelo_ia"] = modelo
        self._salvar()

    def _migrar_formato_antigo(self) -> None:
        # Antes havia uma única voz, que era a do Merlin
        if "voz" in self._dados and not isinstance(self._dados.get("vozes"), dict):
            self._dados["vozes"] = {"merlin": self._dados.pop("voz")}
            self._salvar()

    def _carregar(self) -> dict:
        try:
            dados = json.loads(self._arquivo.read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def _salvar(self) -> None:
        try:
            self._arquivo.write_text(json.dumps(self._dados, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as erro:
            logger.error("[CONFIG] Não consegui salvar: %s", erro)
