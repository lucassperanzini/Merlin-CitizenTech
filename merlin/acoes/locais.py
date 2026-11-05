"""Decide onde o Merlin pode criar coisas e valida nomes ditos em voz alta. Nada aqui altera o disco."""
import re
from dataclasses import dataclass
from pathlib import Path

from win32com.shell import shell, shellcon

from merlin.texto import normalizar

CARACTERES_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
NOMES_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
EXTENSAO_FALADA = re.compile(r"\s+ponto\s+(\w{1,5})$", re.IGNORECASE)
PREFIXOS_DE_PASTA = re.compile(r"^(?:n?[ao]\s+)?(?:pasta\s+)", re.IGNORECASE)


class LocalNaoPermitido(Exception):
    """O caminho pedido fica fora das pastas pessoais."""


class NomeInvalido(Exception):
    """O Windows não aceita esse nome, ou ele tentaria sair da pasta de destino."""


@dataclass(frozen=True)
class PastaPessoal:
    rotulo: str  # como o Merlin fala o nome da pasta
    caminho: Path
    apelidos: tuple[str, ...]  # como a pessoa pode chamá-la


def pastas_do_usuario() -> list[PastaPessoal]:
    """Pastas pessoais reais, mesmo se o Windows ou o OneDrive as tiver movido. A primeira é a pasta padrão."""
    pastas = [
        ("Área de Trabalho", shellcon.FOLDERID_Desktop, ("area de trabalho", "desktop", "tela inicial")),
        ("Documentos", shellcon.FOLDERID_Documents, ("documentos", "meus documentos", "documents")),
        ("Downloads", shellcon.FOLDERID_Downloads, ("downloads", "download", "baixados")),
        ("Imagens", shellcon.FOLDERID_Pictures, ("imagens", "fotos", "pictures")),
        ("Músicas", shellcon.FOLDERID_Music, ("musicas", "musica", "music")),
        ("Vídeos", shellcon.FOLDERID_Videos, ("videos", "video")),
    ]
    return [PastaPessoal(rotulo, Path(shell.SHGetKnownFolderPath(pasta)), apelidos) for rotulo, pasta, apelidos in pastas]


def validar_nome(nome: str) -> str:
    """Devolve o nome pronto para uso; "notas ponto txt" vira "notas.txt"."""
    limpo = EXTENSAO_FALADA.sub(r".\1", nome.strip()).rstrip(" .")
    if not limpo or limpo in {".", ".."} or CARACTERES_INVALIDOS.search(limpo):
        raise NomeInvalido(nome)
    if limpo.split(".")[0].strip().lower() in NOMES_RESERVADOS:
        raise NomeInvalido(nome)
    return limpo


class LocaisPermitidos:
    def __init__(self, pastas: list[PastaPessoal]):
        self._pastas = pastas
        self._apelidos = {normalizar(a): p.caminho for p in pastas for a in p.apelidos}

    @property
    def padrao(self) -> Path:
        return self._pastas[0].caminho

    def resolver(self, local: str) -> Path:
        """Transforma o que a pessoa disse em um caminho, sempre dentro das pastas pessoais."""
        local = PREFIXOS_DE_PASTA.sub("", local.strip()).strip()
        if not local:
            return self.padrao
        if normalizar(local) in self._apelidos:
            return self._apelidos[normalizar(local)]

        caminho = Path(local)
        if caminho.is_absolute():
            return self.garantir_permitido(caminho)
        if len(caminho.parts) > 1:
            return self.garantir_permitido(self.padrao / caminho)
        nome = validar_nome(local)
        return self.garantir_permitido(self._procurar_existente(nome) or self.padrao / nome)

    def garantir_permitido(self, caminho: Path) -> Path:
        resolvido = caminho.resolve()
        if any(resolvido.is_relative_to(p.caminho.resolve()) for p in self._pastas):
            return resolvido
        raise LocalNaoPermitido(str(caminho))

    def descrever(self, caminho: Path) -> str:
        """Como falar um local em voz alta, por exemplo "Projetos, em Documentos"."""
        for pasta in self._pastas:
            if caminho == pasta.caminho.resolve():
                return pasta.rotulo
        for pasta in self._pastas:
            if caminho.is_relative_to(pasta.caminho.resolve()):
                return f"{caminho.name}, em {pasta.rotulo}"
        return caminho.name

    def _procurar_existente(self, nome: str) -> Path | None:
        for pasta in self._pastas:
            if (pasta.caminho / nome).is_dir():
                return pasta.caminho / nome
        return None
