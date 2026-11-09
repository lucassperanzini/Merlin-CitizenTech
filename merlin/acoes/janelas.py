"""Acesso às janelas abertas no Windows.

Não usa o close() do AppOpener: ele mata o processo à força (perde trabalho não salvo) e aceita qualquer
processo de nome parecido. Aqui só janelas visíveis são candidatas, e o WM_CLOSE equivale a clicar no X.
"""
import ctypes
import difflib
import logging
import os
from dataclasses import dataclass

import psutil
import win32con
import win32gui
import win32process

from merlin.texto import normalizar

logger = logging.getLogger(__name__)

CLASSES_PROTEGIDAS = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
ATRIBUTO_OCULTA = 14  # DWMWA_CLOAKED
SEMELHANCA_MINIMA = 0.8
TAMANHO_MINIMO_NOME = 3
TAMANHO_MINIMO_TRECHO = 4


@dataclass(frozen=True)
class JanelaAberta:
    hwnd: int
    pid: int
    programa: str
    titulo: str


def listar_janelas() -> list[JanelaAberta]:
    """Janelas principais abertas pelo usuário, sem as do próprio Merlin e as da área de trabalho."""
    janelas = []

    def visitar(hwnd, _):
        try:
            janela = _ler_janela(hwnd)
        except win32gui.error:
            return True  # a janela fechou no meio da leitura: só não entra na lista
        if janela:
            janelas.append(janela)
        return True

    win32gui.EnumWindows(visitar, None)
    return janelas


# Palavras que não são nome de programa: "clica em salvar aqui" vai para a janela em uso
ALVOS_GENERICOS = {"", "merlin", "aqui", "botoes", "botao", "tela", "janela", "essajanela", "estatela", "programa",
                   "app", "aplicativo"}


def citou_programa(alvo: str) -> bool:
    return normalizar(alvo) not in ALVOS_GENERICOS


def janela_em_uso() -> JanelaAberta | None:
    """A janela em que a pessoa está: a que tem o foco. Se o foco estiver no próprio Merlin, a primeira janela atrás
    dele (o Windows lista da frente para trás), sem contar as "sempre na frente", como um widget ou uma agenda: elas
    ficam no topo da lista mesmo sem a pessoa estar usando."""
    frente = _janela_com_foco()
    if frente:
        return frente
    abertas = [j for j in listar_janelas() if not win32gui.IsIconic(j.hwnd)]
    return next((j for j in abertas if not _sempre_na_frente(j.hwnd)), abertas[0] if abertas else None)


def _janela_com_foco() -> JanelaAberta | None:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    try:
        return _ler_janela(hwnd)  # None para as janelas do Merlin e as da área de trabalho
    except win32gui.error:
        return None


def _sempre_na_frente(hwnd) -> bool:
    return bool(win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST)


def escolher_janelas(nome: str, janelas: list[JanelaAberta]) -> tuple[list[JanelaAberta], bool]:
    """Retorna (janelas encontradas, se foi pelo título). Prefere o nome do programa ao título da janela."""
    alvo = normalizar(nome)
    if len(alvo) < TAMANHO_MINIMO_NOME:
        return [], False
    palavras = {normalizar(p) for p in nome.split()}  # "google chrome" combina com chrome

    def combina(janela):
        programa = normalizar(janela.programa)
        return alvo == programa or (len(alvo) >= TAMANHO_MINIMO_TRECHO and alvo in programa) or programa in palavras

    achadas = [j for j in janelas if combina(j)]
    if not achadas:
        programas = {normalizar(j.programa) for j in janelas}
        parecidos = difflib.get_close_matches(alvo, programas, n=1, cutoff=SEMELHANCA_MINIMA)
        achadas = [j for j in janelas if normalizar(j.programa) in parecidos]
    if achadas:
        return achadas, False
    return [j for j in janelas if alvo in normalizar(j.titulo)], True


def ainda_aberta(janela: JanelaAberta) -> bool:
    if not win32gui.IsWindow(janela.hwnd):
        return False
    return win32process.GetWindowThreadProcessId(janela.hwnd)[1] == janela.pid


def pedir_fechamento(janela: JanelaAberta) -> bool:
    """Pede para a janela fechar, como o botão X. Retorna False se o pedido falhou."""
    try:
        if ainda_aberta(janela):
            win32gui.PostMessage(janela.hwnd, win32con.WM_CLOSE, 0, 0)
        return True
    except win32gui.error as erro:
        logger.error("[FECHAR] %s", erro)
        return False


def _ler_janela(hwnd) -> JanelaAberta | None:
    if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
        return None
    titulo = win32gui.GetWindowText(hwnd).strip()
    if not titulo or win32gui.GetClassName(hwnd) in CLASSES_PROTEGIDAS or _oculta_pelo_sistema(hwnd):
        return None
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid == os.getpid():
        return None
    try:
        programa = os.path.splitext(psutil.Process(pid).name())[0]
    except psutil.Error:
        return None
    return JanelaAberta(hwnd, pid, programa, titulo)


def _oculta_pelo_sistema(hwnd) -> bool:
    # Apps da Microsoft Store deixam janelas "visíveis" que na verdade não aparecem na tela
    oculta = ctypes.c_int(0)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, ATRIBUTO_OCULTA, ctypes.byref(oculta), ctypes.sizeof(oculta))
    return oculta.value != 0
