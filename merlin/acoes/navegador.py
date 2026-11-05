"""Descobre qual é o navegador padrão do Windows, para "abre o navegador" e "fecha o navegador"."""
import winreg
from dataclasses import dataclass

from merlin.texto import normalizar

CHAVE_PADRAO = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
PALAVRAS_NAVEGADOR = {"navegador", "onavegador", "meunavegador", "navegadordeinternet", "browser", "internet", "web"}


@dataclass(frozen=True)
class Navegador:
    programa: str  # nome na lista de programas instalados (para abrir)
    processo: str  # nome do executável sem .exe (para fechar)


# O Windows identifica o navegador padrão por um código (ProgId)
NAVEGADORES = {
    "chromehtml": Navegador("google chrome", "chrome"),
    "msedgehtm": Navegador("microsoft edge", "msedge"),
    "firefoxurl": Navegador("firefox", "firefox"),
    "bravehtml": Navegador("brave", "brave"),
    "operastable": Navegador("opera", "opera"),
}


def e_navegador_generico(nome: str) -> bool:
    return normalizar(nome) in PALAVRAS_NAVEGADOR


def navegador_padrao() -> Navegador | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_PADRAO) as chave:
            codigo = str(winreg.QueryValueEx(chave, "ProgId")[0]).lower()
    except OSError:
        return None
    # O Firefox usa códigos como "FirefoxURL-308046B0AF4A39CB"
    return next((n for prefixo, n in NAVEGADORES.items() if codigo.startswith(prefixo)), None)
