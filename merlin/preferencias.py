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

    @property
    def apelidos_pastas(self) -> list[dict]:
        """Atalhos de pasta da pessoa: [{"apelido": "trabalho", "caminho": "D:\\Clientes"}], da aba Pastas."""
        itens = self._dados.get("apelidos_pastas", [])
        return [i for i in itens if isinstance(i, dict) and i.get("apelido") and i.get("caminho")] \
            if isinstance(itens, list) else []

    @apelidos_pastas.setter
    def apelidos_pastas(self, itens: list[dict]) -> None:
        self._dados["apelidos_pastas"] = [{"apelido": str(i["apelido"]).strip(), "caminho": str(i["caminho"]).strip()}
                                          for i in itens]
        self._salvar()

    @property
    def administrador(self) -> bool:
        """Perfil da máquina (merlin/interface/perfil.py). Só "administrador", escrito à mão no arquivo, libera os
        ajustes da IA; sem o campo, a máquina é de operador. Não há tela para mudar: é de propósito."""
        return self._dados.get("perfil") == "administrador"

    @property
    def modo_debug(self) -> bool:
        """Botão da órbita: mostra a aba do raciocínio da IA no cartão. Só para o administrador."""
        return self.administrador and bool(self._dados.get("modo_debug", False))

    @modo_debug.setter
    def modo_debug(self, ligado: bool) -> None:
        if not self.administrador:
            return
        self._dados["modo_debug"] = bool(ligado)
        self._salvar()

    @property
    def alertas_intervalo(self) -> int:
        """De quantos em quantos minutos a aba Alertas busca os focos sozinha. 0: só quando alguém clica."""
        valor = self._dados.get("alertas_intervalo", 0)
        return valor if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0 else 0

    @alertas_intervalo.setter
    def alertas_intervalo(self, minutos: int) -> None:
        self._dados["alertas_intervalo"] = int(minutos)
        self._salvar()

    @property
    def alertas_modo_teste(self) -> bool:
        """Consultas que aparecem no mapa e não ficam guardadas, para repetir o teste. Só para o administrador."""
        return self.administrador and bool(self._dados.get("alertas_modo_teste", False))

    @alertas_modo_teste.setter
    def alertas_modo_teste(self, ligado: bool) -> None:
        if not self.administrador:
            return
        self._dados["alertas_modo_teste"] = bool(ligado)
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
