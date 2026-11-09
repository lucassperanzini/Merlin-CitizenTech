"""O Python usado pelos scripts, separado do Merlin: instalar algo aqui não tem como quebrar o assistente.

Separa só as bibliotecas. Um script continua podendo mexer nos arquivos do computador.
"""
import re
import subprocess
import sys
from importlib.machinery import PathFinder
from pathlib import Path

from merlin.config import PASTA_PYTHON_SCRIPTS

BASICAS = ("pandas", "numpy", "pillow", "matplotlib")  # as que a IA é orientada a usar
# Nome no "import" -> nome para instalar. Nem sempre são iguais, e às vezes o nome igual é de outro pacote (docx)
CONHECIDAS = {"pandas": "pandas", "numpy": "numpy", "PIL": "pillow", "matplotlib": "matplotlib", "openpyxl": "openpyxl",
              "pypdf": "pypdf", "PyPDF2": "PyPDF2", "docx": "python-docx", "pptx": "python-pptx", "reportlab": "reportlab",
              "customtkinter": "customtkinter"}
_NOME_VALIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")  # também impede que um nome vire uma opção do pip
TEMPO_PARA_INSTALAR = 600
TEMPO_PARA_PREPARAR = 1800
MAX_CARACTERES_DA_RESPOSTA = 1500


def nome_valido(nome: str) -> bool:
    return isinstance(nome, str) and bool(_NOME_VALIDO.match(nome))


class Ambiente:
    def __init__(self, pasta=PASTA_PYTHON_SCRIPTS):
        self._pasta = Path(pasta)

    @property
    def python(self) -> Path:
        return self._pasta / "Scripts" / "python.exe"

    def pronto(self) -> bool:
        return self.python.is_file()

    def faltando(self, modulos) -> list[str]:
        """Só procura nos arquivos do ambiente: não importa nem executa nada."""
        bibliotecas = [str(self._pasta / "Lib" / "site-packages")]
        return [m for m in modulos if PathFinder.find_spec(m, bibliotecas) is None]

    def _rodar(self, comando: list[str], tempo: int) -> tuple[bool, str]:
        try:
            feito = subprocess.run(comando, capture_output=True, stdin=subprocess.DEVNULL, timeout=tempo, encoding="utf-8",
                                   errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            return False, "Demorou demais e foi interrompido."
        except OSError as erro:
            return False, str(erro)
        return feito.returncode == 0, (feito.stderr or feito.stdout or "").strip()[-MAX_CARACTERES_DA_RESPOSTA:]

    def instalar(self, *pacotes: str) -> tuple[bool, str]:
        if not pacotes or not all(nome_valido(p) for p in pacotes):
            return False, "Nome de pacote inválido."
        return self._rodar([str(self.python), "-m", "pip", "install", "--no-input", *pacotes], TEMPO_PARA_INSTALAR)

    def preparar(self, basicas=BASICAS) -> tuple[bool, str]:
        ok, resposta = self._rodar([sys.executable, "-m", "venv", str(self._pasta)], TEMPO_PARA_PREPARAR)
        if not ok or not basicas:
            return ok, resposta
        return self.instalar(*basicas)
