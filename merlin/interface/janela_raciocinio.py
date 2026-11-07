"""Aba Raciocínio da Central: mostra, pedido a pedido, o que o assistente ouviu, entendeu, viu na tela e fez.
A página busca os passos novos sozinha enquanto está aberta."""
import os
from pathlib import Path


class ApiRaciocinio:
    """Funções que a página pode chamar (atributos privados: o pywebview expõe os públicos)."""

    def __init__(self, raciocinio, pasta_registros: Path | None = None):
        self._raciocinio = raciocinio
        self._pasta = pasta_registros

    def novos(self, ultimo: int):
        return [p.como_dict() for p in self._raciocinio.desde(int(ultimo or 0))]

    def limpar(self):
        """Limpa só a tela: os arquivos do dia continuam guardados."""
        self._raciocinio.limpar()

    def tem_pasta(self):
        return self._pasta is not None

    def abrir_pasta(self):
        if self._pasta is None:
            return
        self._pasta.mkdir(parents=True, exist_ok=True)
        os.startfile(self._pasta)  # abre no Explorador de Arquivos

