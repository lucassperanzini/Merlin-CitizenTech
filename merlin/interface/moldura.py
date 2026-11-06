"""Formato da janela no Windows: a bolinha sem moldura no canto da tela e a transição até a janela cheia.
Usa a API do Windows direto no handle da janela, porque o pywebview não troca a moldura nem anima o tamanho."""
import ctypes
import ctypes.wintypes as wt
import time
from typing import NamedTuple

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_STYLE = -16
WS_CAPTION = 0x00C00000  # barra de título e borda
WS_THICKFRAME = 0x00040000
MOLDURA = WS_CAPTION | WS_THICKFRAME
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20
MONITOR_DEFAULTTONEAREST = 2
dwmapi = ctypes.windll.dwmapi
DWMWA_NCRENDERING_POLICY, DWMNCRP_USEWINDOWSTYLE, DWMNCRP_DISABLED = 2, 0, 1
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DEFAULT, DWMWCP_DONOTROUND = 33, 0, 1
DWMWA_BORDER_COLOR, DWMWA_COLOR_DEFAULT, DWMWA_COLOR_NONE = 34, 0xFFFFFFFF, 0xFFFFFFFE

LADO_COMPACTO = 120  # pontos; vira pixels conforme a escala da tela
MARGEM_COMPACTA = 18
DURACAO_ANIMACAO = 0.38  # segundos
QUADROS_POR_SEGUNDO = 60

user32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
gdi32.CreateRoundRectRgn.restype = wt.HANDLE
user32.MonitorFromWindow.restype = wt.HANDLE
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]


class Retangulo(NamedTuple):
    x: int
    y: int
    largura: int
    altura: int


class _InfoMonitor(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def interpolar(de: Retangulo, para: Retangulo, t: float) -> Retangulo:
    return Retangulo(*(round(a + (b - a) * t) for a, b in zip(de, para)))


def suavizar(t: float) -> float:
    """Começa rápido e chega devagar, como algo que se acomoda no lugar."""
    return 1 - (1 - t) ** 3


def retangulo_do_canto(area: Retangulo, escala: float) -> Retangulo:
    """Canto inferior direito da área livre da tela (sem a barra de tarefas)."""
    lado, margem = round(LADO_COMPACTO * escala), round(MARGEM_COMPACTA * escala)
    return Retangulo(area.x + area.largura - lado - margem, area.y + area.altura - lado - margem, lado, lado)


class Moldura:
    def __init__(self, hwnd: int):
        self._hwnd = hwnd
        self._estilo_original = user32.GetWindowLongW(hwnd, GWL_STYLE)
        # Guardados com a janela ainda no tamanho normal: é para eles que ela volta
        self.cheia = self._retangulo_janela()
        self.conteudo = self._retangulo_conteudo()

    def canto(self) -> Retangulo:
        monitor = user32.MonitorFromWindow(self._hwnd, MONITOR_DEFAULTTONEAREST)
        info = _InfoMonitor(cbSize=ctypes.sizeof(_InfoMonitor))
        user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        r = info.rcWork
        escala = user32.GetDpiForWindow(self._hwnd) / 96 or 1
        return retangulo_do_canto(Retangulo(r.left, r.top, r.right - r.left, r.bottom - r.top), escala)

    # Só os bits da moldura mudam: o resto do estilo (inclusive se a janela está visível) fica como estiver agora
    def sem_moldura(self) -> None:
        self._trocar_estilo(self._estilo_atual() & ~MOLDURA)
        self._efeitos_do_windows(False)

    def com_moldura(self) -> None:
        self._efeitos_do_windows(True)
        self._trocar_estilo(self._estilo_atual() | (self._estilo_original & MOLDURA))

    def _efeitos_do_windows(self, ligados: bool) -> None:
        """O Windows 11 arredonda os cantos, contorna e sombreia a janela pelo retângulo dela, ignorando o recorte
        redondo: em volta da bolinha sobravam cantos brancos e uma sombra quadrada. Na bolinha, tudo isso sai."""
        for atributo, ligado, desligado in ((DWMWA_NCRENDERING_POLICY, DWMNCRP_USEWINDOWSTYLE, DWMNCRP_DISABLED),
                                            (DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DEFAULT, DWMWCP_DONOTROUND),
                                            (DWMWA_BORDER_COLOR, DWMWA_COLOR_DEFAULT, DWMWA_COLOR_NONE)):
            valor = ctypes.c_uint(ligado if ligados else desligado)
            dwmapi.DwmSetWindowAttribute(self._hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor))

    def _estilo_atual(self) -> int:
        return user32.GetWindowLongW(self._hwnd, GWL_STYLE)

    def posicionar(self, r: Retangulo, arredondamento: float = 0.0) -> None:
        """arredondamento 0 é retângulo comum; 1 é círculo (num quadrado)."""
        user32.SetWindowPos(self._hwnd, None, r.x, r.y, r.largura, r.altura, SWP_NOZORDER | SWP_NOACTIVATE)
        if arredondamento <= 0:
            user32.SetWindowRgn(self._hwnd, None, True)
            return
        diametro = round(min(r.largura, r.altura) * arredondamento)
        regiao = gdi32.CreateRoundRectRgn(0, 0, r.largura + 1, r.altura + 1, diametro, diametro)
        user32.SetWindowRgn(self._hwnd, regiao, True)  # o Windows passa a ser o dono da região

    def animar(self, de: Retangulo, para: Retangulo, arredondar_de: float, arredondar_para: float) -> None:
        inicio = time.perf_counter()
        while True:
            t = min((time.perf_counter() - inicio) / DURACAO_ANIMACAO, 1.0)
            e = suavizar(t)
            self.posicionar(interpolar(de, para, e), arredondar_de + (arredondar_para - arredondar_de) * e)
            if t >= 1.0:
                return
            time.sleep(1 / QUADROS_POR_SEGUNDO)

    def _trocar_estilo(self, estilo: int) -> None:
        user32.SetWindowLongW(self._hwnd, GWL_STYLE, estilo)
        user32.SetWindowPos(self._hwnd, None, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)

    def _retangulo_janela(self) -> Retangulo:
        r = wt.RECT()
        user32.GetWindowRect(self._hwnd, ctypes.byref(r))
        return Retangulo(r.left, r.top, r.right - r.left, r.bottom - r.top)

    def _retangulo_conteudo(self) -> Retangulo:
        """A área da página, sem a barra de título: a animação termina exatamente sobre ela."""
        r, origem = wt.RECT(), wt.POINT(0, 0)
        user32.GetClientRect(self._hwnd, ctypes.byref(r))
        user32.ClientToScreen(self._hwnd, ctypes.byref(origem))
        return Retangulo(origem.x, origem.y, r.right, r.bottom)
