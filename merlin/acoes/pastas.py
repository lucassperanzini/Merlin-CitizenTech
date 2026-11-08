"""Abre pastas do computador no Explorador de Arquivos. Na ordem: os apelidos da pessoa (aba Pastas da Central), as
pastas do Acesso Rápido do Windows, as pastas do Windows (Downloads, Documentos...), unidades de disco ("disco D") e,
por último, qualquer pasta pelo nome, procurada na pasta do usuário e nos outros discos."""
import logging
import os
import re
import string
import time
import unicodedata
from collections import deque
from pathlib import Path

from merlin.nucleo.resposta import Resultado
from merlin.texto import normalizar

logger = logging.getLogger(__name__)

# Pastas do Windows pelo jeito como a pessoa fala. O caminho vem do próprio Windows (pode estar no OneDrive).
PASTAS_DO_WINDOWS = {
    "downloads": ("FOLDERID_Downloads", "Downloads"), "download": ("FOLDERID_Downloads", "Downloads"),
    "baixados": ("FOLDERID_Downloads", "Downloads"),
    "documentos": ("FOLDERID_Documents", "Documentos"), "documento": ("FOLDERID_Documents", "Documentos"),
    "areadetrabalho": ("FOLDERID_Desktop", "Área de trabalho"), "desktop": ("FOLDERID_Desktop", "Área de trabalho"),
    "areatrabalho": ("FOLDERID_Desktop", "Área de trabalho"),  # "área de trabalho" sem o "de", que é tirado antes
    "imagens": ("FOLDERID_Pictures", "Imagens"), "fotos": ("FOLDERID_Pictures", "Imagens"),
    "musicas": ("FOLDERID_Music", "Músicas"), "musica": ("FOLDERID_Music", "Músicas"),
    "videos": ("FOLDERID_Videos", "Vídeos"), "video": ("FOLDERID_Videos", "Vídeos"),
    "usuario": ("FOLDERID_Profile", "pasta do usuário"), "pessoal": ("FOLDERID_Profile", "pasta do usuário"),
}
# Palavras que acompanham o nome da pasta no pedido e não fazem parte dele
ACOMPANHAM = {"a", "o", "as", "os", "pasta", "pastas", "minha", "minhas", "meu", "meus", "de", "da", "do", "das",
              "dos", "na", "no", "em"}
UNIDADE = re.compile(r"^(?:disco|unidade|drive|hd|particao)?\s*([a-z])\s*:?$")  # depois de tirar os acentos

# Busca por nome: até onde ir e o que pular (pastas do sistema e técnicas, que nunca são o que a pessoa quer)
ACESSO_RAPIDO = "shell:::{679f85cb-0220-4080-b29b-5540cc05aab6}"
VALIDADE_ACESSO_RAPIDO = 120  # segundos: ler o Acesso Rápido leva uns 0,3 s; a lista é guardada por um tempo

_fonte_de_apelidos = lambda: []  # noqa: E731  definida pela habilidade, com as preferências da pessoa
_acesso_rapido = {"lido_em": 0.0, "pastas": []}

PROFUNDIDADE = 3
TEMPO_MAXIMO = 2.0  # segundos
PULAR = {"windows", "program files", "program files (x86)", "programdata", "appdata", "$recycle.bin",
         "system volume information", "node_modules", "__pycache__", ".git", ".venv", "venv", "site-packages"}


def _sem_acompanhantes(nome: str) -> str:
    palavras = [p for p in re.findall(r"[\wÀ-ÿ]+", nome.lower()) if p not in ACOMPANHAM]
    return " ".join(palavras)


def pasta_do_windows(nome: str):
    """(caminho, nome falado) de uma pasta do Windows citada, ou None."""
    chave = normalizar(_sem_acompanhantes(nome))
    if chave not in PASTAS_DO_WINDOWS:
        return None
    pasta_id, falado = PASTAS_DO_WINDOWS[chave]
    try:
        from win32comext.shell import shell, shellcon
        return Path(shell.SHGetKnownFolderPath(getattr(shellcon, pasta_id))), falado
    except Exception as erro:  # sem o Windows saber dizer, usa o padrão dentro da pasta do usuário
        logger.warning("[PASTAS] Não consegui perguntar ao Windows por %s: %s", pasta_id, erro)
        return Path.home() / falado, falado


def definir_apelidos(fonte) -> None:
    """fonte(): a lista atual de apelidos [{"apelido", "caminho"}] (lida a cada pedido: mudanças valem na hora)."""
    global _fonte_de_apelidos
    _fonte_de_apelidos = fonte


def pastas_do_acesso_rapido() -> list[tuple[str, Path, bool]]:
    """(nome, caminho, fixada) das pastas do Acesso Rápido do Windows: as fixadas e as usadas com frequência.
    Os arquivos recentes que ele também mostra ficam de fora."""
    if time.monotonic() - _acesso_rapido["lido_em"] < VALIDADE_ACESSO_RAPIDO:
        return _acesso_rapido["pastas"]
    pastas = []
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()  # cada thread precisa iniciar o COM antes de usar
        for item in win32com.client.Dispatch("Shell.Application").Namespace(ACESSO_RAPIDO).Items():
            if item.IsFolder and item.Path and Path(item.Path).is_dir():
                try:
                    fixada = bool(item.ExtendedProperty("System.Home.IsPinned"))
                except Exception:
                    fixada = False
                pastas.append((str(item.Name), Path(item.Path), fixada))
    except Exception as erro:  # sem o Acesso Rápido, os outros jeitos de achar a pasta continuam valendo
        logger.warning("[PASTAS] Não consegui ler o Acesso Rápido: %s", erro)
    _acesso_rapido.update(lido_em=time.monotonic(), pastas=pastas)
    return pastas


def _chave(nome: str) -> str:
    return normalizar(_sem_acompanhantes(nome)) or normalizar(nome)


def atalho(nome: str, so_fixadas: bool = False):
    """(caminho, nome falado, de onde veio) de um apelido da pessoa ou de uma pasta do Acesso Rápido, ou None.
    so_fixadas: do Acesso Rápido, só as pastas que a pessoa fixou (as frequentes podem ter nome de programa)."""
    chave = _chave(nome)
    if not chave:
        return None
    for item in _fonte_de_apelidos():
        if _chave(item["apelido"]) == chave:
            return Path(item["caminho"]), item["apelido"], "pelo seu apelido"
    for nome_rapido, caminho, fixada in pastas_do_acesso_rapido():
        if _chave(nome_rapido) == chave and (fixada or not so_fixadas):
            return caminho, nome_rapido, "pelo Acesso Rápido do Windows"
    return None


def unidade_de_disco(nome: str) -> Path | None:
    """"disco D", "unidade c", "D:" -> D:\\, se a unidade existir."""
    achado = UNIDADE.match(normalizar_espacos(nome))
    if not achado:
        return None
    raiz = Path(f"{achado.group(1).upper()}:\\")
    return raiz if raiz.exists() else None


def normalizar_espacos(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return " ".join(sem_acento.split())


def raizes_de_busca() -> list[Path]:
    """Onde procurar: a pasta do usuário primeiro, depois a raiz dos outros discos."""
    raizes = [Path.home()]
    for letra in string.ascii_uppercase:
        raiz = Path(f"{letra}:\\")
        if raiz.exists() and raiz.drive.upper() != Path.home().drive.upper():
            raizes.append(raiz)
    return raizes


def procurar_pasta(nome: str, raizes: list[Path], profundidade: int = PROFUNDIDADE,
                   tempo_maximo: float = TEMPO_MAXIMO) -> list[Path]:
    """Pastas com esse nome (sem diferenciar acentos e maiúsculas), da mais rasa para a mais funda e, no mesmo
    nível, da mais recente para a mais antiga. A busca para no tempo máximo, com o que já achou."""
    alvo = normalizar(nome)
    if not alvo:
        return []
    limite = time.monotonic() + tempo_maximo
    achadas: list[tuple[int, Path]] = []
    fila = deque((raiz, 0) for raiz in raizes)
    while fila and time.monotonic() < limite:
        pasta, nivel = fila.popleft()
        try:
            with os.scandir(pasta) as itens:
                for item in itens:
                    if not item.is_dir(follow_symlinks=False) or item.name.startswith((".", "$")):
                        continue
                    if item.name.lower() in PULAR:
                        continue
                    caminho = Path(item.path)
                    if normalizar(item.name) == alvo:
                        achadas.append((nivel + 1, caminho))
                    if nivel + 1 < profundidade:
                        fila.append((caminho, nivel + 1))
        except OSError:
            continue  # sem permissão ou sumiu: segue
    return [c for _, c in sorted(achadas, key=lambda a: (a[0], -_modificada(a[1])))]


def _modificada(caminho: Path) -> float:
    try:
        return caminho.stat().st_mtime
    except OSError:
        return 0.0


class AbrirPasta:
    def __init__(self, abrir=os.startfile, raizes=raizes_de_busca):
        self._abrir = abrir
        self._raizes = raizes

    def __call__(self, intencao) -> Resultado:
        pedido = (intencao.alvo or "").strip()
        nome = _sem_acompanhantes(pedido) or pedido
        achado = atalho(pedido)
        if achado:
            caminho, falado, origem = achado
            return self._abrir_pasta(caminho, f"a pasta {falado}", f" ({origem})")
        conhecida = pasta_do_windows(pedido)
        if conhecida:
            caminho, falado = conhecida
            return self._abrir_pasta(caminho, f"a pasta {falado}" if falado != "pasta do usuário" else "a sua pasta de usuário")
        disco = unidade_de_disco(nome)
        if disco:
            return self._abrir_pasta(disco, f"o disco {disco.drive[0]}")
        achadas = procurar_pasta(nome, self._raizes())
        if not achadas:
            return Resultado(f"não encontrei a pasta {nome}", registro=f"Pasta não encontrada: {nome}")
        outras = f" (havia {len(achadas)} com esse nome; abri a mais rasa)" if len(achadas) > 1 else ""
        return self._abrir_pasta(achadas[0], f"a pasta {achadas[0].name}", outras)

    def _abrir_pasta(self, caminho: Path, falado: str, observacao: str = "") -> Resultado:
        if not caminho.is_dir():
            return Resultado(f"não encontrei {falado}", registro=f"Pasta não existe: {caminho}")
        try:
            self._abrir(str(caminho))
        except OSError as erro:
            return Resultado(f"não consegui abrir {falado}", registro=f"Erro ao abrir {caminho}: {erro}")
        return Resultado(f"abri {falado}", registro=f"Aberta: {caminho}{observacao}")
