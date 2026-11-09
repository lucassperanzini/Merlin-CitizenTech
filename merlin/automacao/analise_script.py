"""Lê o código de um script escrito pela IA, sem executar nada, e aponta o que ele tentaria fazer.

Ajuda a barrar erros comuns, mas não prova que um script é seguro: a conferência real é o ensaio em cópia.
"""
import ast
import sys
from dataclasses import dataclass

ALTERA = "altera ou apaga arquivos que já existem"
EXECUTA = "abre outros programas ou comandos"
INTERNET = "acessa a internet"
DINAMICO = "monta código para rodar na hora"

_MODULOS_BLOQUEADOS = {
    "subprocess": EXECUTA, "multiprocessing": EXECUTA, "ctypes": EXECUTA, "winreg": EXECUTA, "pty": EXECUTA,
    "socket": INTERNET, "requests": INTERNET, "urllib": INTERNET, "urllib3": INTERNET, "http": INTERNET,
    "httpx": INTERNET, "aiohttp": INTERNET, "ftplib": INTERNET, "smtplib": INTERNET, "webbrowser": INTERNET,
    "importlib": DINAMICO, "runpy": DINAMICO,
}
_CHAMADAS_BLOQUEADAS = {
    **dict.fromkeys(("shutil.move", "shutil.rmtree", "os.rename", "os.renames", "os.replace", "os.remove", "os.unlink",
                     "os.rmdir", "os.removedirs", "os.truncate"), ALTERA),
    **dict.fromkeys(("os.system", "os.popen", "os.startfile", "os.fork", "os.kill"), EXECUTA),
    **dict.fromkeys(("eval", "exec", "compile", "__import__", "getattr", "globals", "locals"), DINAMICO),
}
_PREFIXOS_BLOQUEADOS = {"os.exec": EXECUTA, "os.spawn": EXECUTA}
_METODOS_BLOQUEADOS = ("unlink", "rmdir", "truncate")
_COPIAS = ("shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree")
_METODOS_QUE_GRAVAM = ("to_excel", "to_csv", "to_json", "to_parquet", "save", "write_text", "write_bytes")
_METODOS_DE_EXCEL = ("to_excel", "read_excel")
_MODULOS_ESTRELA = ("os", "shutil", "pathlib")
AVISO_SUBSTITUI = "Pode substituir um arquivo com o mesmo nome, se ele já existir."


@dataclass(frozen=True)
class Analise:
    valido: bool
    bloqueios: tuple[str, ...] = ()  # por que o script não pode ser oferecido
    avisos: tuple[str, ...] = ()  # o que a pessoa precisa saber antes de usar
    externos: tuple[str, ...] = ()  # bibliotecas de que o script precisa, fora as que vêm com o Python


def _nome(no, apelidos: dict[str, str]) -> str:
    """os.path.join, com apelidos desfeitos ("from shutil import move" vira shutil.move). "" se for dinâmico."""
    partes = []
    while isinstance(no, ast.Attribute):
        partes.append(no.attr)
        no = no.value
    if not isinstance(no, ast.Name):
        return ""
    partes.append(apelidos.get(no.id, no.id))
    return ".".join(reversed(partes))


def _modo_grava(no) -> bool:
    """Um valor que não dá para ler sem executar conta como gravação. O modo x só cria arquivo novo."""
    if not isinstance(no, ast.Constant) or not isinstance(no.value, str):
        return True
    return any(letra in no.value for letra in "wa+")


def _argumento(chamada: ast.Call, posicao: int, nome: str):
    if len(chamada.args) > posicao:
        return chamada.args[posicao]
    return next((k.value for k in chamada.keywords if k.arg == nome), None)


def _ler_imports(arvore) -> tuple[dict[str, str], set[str], list[str]]:
    apelidos, modulos, bloqueios = {}, set(), []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for item in no.names:
                modulos.add(item.name.split(".")[0])
                apelidos[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
        elif isinstance(no, ast.ImportFrom):
            modulo = no.module or ""
            modulos.add(modulo.split(".")[0])
            for item in no.names:
                if item.name == "*" and modulo.split(".")[0] in _MODULOS_ESTRELA:
                    bloqueios.append(ALTERA)
                apelidos[item.asname or item.name] = f"{modulo}.{item.name}"
    bloqueios += [_MODULOS_BLOQUEADOS[m] for m in modulos if m in _MODULOS_BLOQUEADOS]
    return apelidos, modulos, bloqueios


def _bloqueio_da_chamada(chamada: ast.Call, nome: str) -> str | None:
    if nome in _CHAMADAS_BLOQUEADAS:
        return _CHAMADAS_BLOQUEADAS[nome]
    for prefixo, motivo in _PREFIXOS_BLOQUEADOS.items():
        if nome.startswith(prefixo):
            return motivo
    if isinstance(chamada.func, ast.Attribute):
        metodo = chamada.func.attr
        if metodo in _METODOS_BLOQUEADOS:
            return ALTERA
        # Path.rename(novo) e Path.replace(novo) têm um argumento; "texto".replace(a, b) tem dois; df.rename usa nomes
        if metodo == "rename" and chamada.args:
            return ALTERA
        if metodo == "replace" and len(chamada.args) == 1:
            return ALTERA
    return None


def _grava(chamada: ast.Call, nome: str) -> bool:
    metodo = chamada.func.attr if isinstance(chamada.func, ast.Attribute) else ""
    if nome == "open":
        modo = _argumento(chamada, 1, "mode")
        return modo is not None and _modo_grava(modo)
    if metodo == "open":  # Path.open("w"); em Image.open(caminho), o primeiro argumento é o arquivo
        modo = _argumento(chamada, 0, "mode")
        return isinstance(modo, ast.Constant) and isinstance(modo.value, str) \
            and set(modo.value) <= set("rwaxbt+") and _modo_grava(modo)
    if nome == "zipfile.ZipFile":
        modo = _argumento(chamada, 1, "mode")
        return modo is not None and _modo_grava(modo)
    return nome in _COPIAS or metodo in _METODOS_QUE_GRAVAM


def analisar(codigo: str) -> Analise:
    try:
        arvore = ast.parse(codigo)
    except (SyntaxError, ValueError):
        return Analise(False)
    apelidos, modulos, bloqueios = _ler_imports(arvore)
    grava = usa_excel = False
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            nome = _nome(no.func, apelidos)
            motivo = _bloqueio_da_chamada(no, nome)
            if motivo:
                bloqueios.append(motivo)
            grava = grava or _grava(no, nome)
            usa_excel = usa_excel or (isinstance(no.func, ast.Attribute) and no.func.attr in _METODOS_DE_EXCEL)
    if usa_excel:  # o pandas precisa dela por dentro, sem o script importar
        modulos.add("openpyxl")
    externos = tuple(sorted(m for m in modulos if m and m not in sys.stdlib_module_names))
    return Analise(True, tuple(dict.fromkeys(bloqueios)), (AVISO_SUBSTITUI,) if grava else (), externos)
