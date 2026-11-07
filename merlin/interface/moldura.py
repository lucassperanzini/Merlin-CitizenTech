"""Formato da janela no Windows: a bolinha sem moldura no canto da tela e a transição até a janela cheia.
Usa a API do Windows direto no handle da janela, porque o pywebview não troca a moldura nem anima o tamanho."""
import ctypes
import ctypes.wintypes as wt
import math
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
DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_AUTOMATICO, DWMSBT_NENHUM = 38, 0, 1

# A janela compacta: a bolinha em cima, uma faixa com o nome do assistente embaixo e, do lado de fora da bolinha,
# botões redondos num arco à esquerda (o lado de dentro da tela, já que a bolinha fica no canto direito).
# Medidas em pontos: viram pixels conforme a escala da tela, e são as mesmas que a página usa em CSS.
LADO_COMPACTO = 120  # diâmetro da bolinha
LARGURA_NOME = 150  # um pouco mais larga que a bolinha, para caber o nome
ESPACO_NOME = 4  # entre a bolinha e a faixa do nome
ALTURA_NOME = 24
BOTOES_COMPACTOS = ("engrenagem", "microfone", "raciocinio")  # ids dos botões na página, de cima para baixo
ANGULOS_BOTOES = (148, 180, 212)  # graus a partir da direita, no sentido anti-horário: 180 é bem à esquerda
DIAMETRO_BOTAO = 28
ORBITA_BOTOES = 84  # do centro da bolinha ao centro de cada botão: sobra um vão entre eles e a bolinha
MARGEM_COMPACTA = 18
DURACAO_ANIMACAO = 0.38  # segundos
QUADROS_POR_SEGUNDO = 60

user32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
gdi32.CreateRoundRectRgn.restype = wt.HANDLE
gdi32.CreateEllipticRgn.restype = wt.HANDLE
gdi32.CombineRgn.argtypes = [wt.HANDLE, wt.HANDLE, wt.HANDLE, ctypes.c_int]
gdi32.DeleteObject.argtypes = [wt.HANDLE]
RGN_OR = 2
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


def desenho_compacto() -> dict:
    """Onde fica cada peça da janela compacta, em pontos, a partir do canto de cima à esquerda dela.
    É a fonte única: o recorte da janela sai daqui, e a página recebe o mesmo desenho para posicionar as peças."""
    raio, raio_botao = LADO_COMPACTO / 2, DIAMETRO_BOTAO / 2
    cx, cy = ORBITA_BOTOES + raio_botao, raio  # centro da bolinha: o botão mais à esquerda encosta na borda
    botoes = [{"id": id_botao,
               "x": round(cx + ORBITA_BOTOES * math.cos(math.radians(angulo)) - raio_botao, 1),
               "y": round(cy - ORBITA_BOTOES * math.sin(math.radians(angulo)) - raio_botao, 1),
               "lado": DIAMETRO_BOTAO}
              for id_botao, angulo in zip(BOTOES_COMPACTOS, ANGULOS_BOTOES)]
    return {
        "largura": cx + max(raio, LARGURA_NOME / 2),
        "altura": LADO_COMPACTO + ESPACO_NOME + ALTURA_NOME,
        "bolinha": {"x": cx - raio, "y": 0, "lado": LADO_COMPACTO},
        "nome": {"x": cx - LARGURA_NOME / 2, "y": LADO_COMPACTO + ESPACO_NOME,
                 "largura": LARGURA_NOME, "altura": ALTURA_NOME},
        "botoes": botoes,
    }


def tamanho_compacto(escala: float) -> tuple[int, int]:
    desenho = desenho_compacto()
    return round(desenho["largura"] * escala), round(desenho["altura"] * escala)


def retangulo_do_canto(area: Retangulo, escala: float) -> Retangulo:
    """Canto inferior direito da área livre da tela (sem a barra de tarefas)."""
    largura, altura = tamanho_compacto(escala)
    margem = round(MARGEM_COMPACTA * escala)
    return Retangulo(area.x + area.largura - largura - margem, area.y + area.altura - altura - margem, largura, altura)


def formas_compactas(escala: float):
    """O recorte da janela compacta, em pixels dentro dela: (círculo da bolinha, faixa do nome, [círculo de cada
    botão]), cada forma como (esquerda, topo, direita, base)."""
    desenho = desenho_compacto()

    def caixa(x, y, largura, altura):
        return round(x * escala), round(y * escala), round((x + largura) * escala), round((y + altura) * escala)

    b, n = desenho["bolinha"], desenho["nome"]
    return (caixa(b["x"], b["y"], b["lado"], b["lado"]),
            caixa(n["x"], n["y"], n["largura"], n["altura"]),
            [caixa(o["x"], o["y"], o["lado"], o["lado"]) for o in desenho["botoes"]])


class Moldura:
    def __init__(self, hwnd: int):
        self._hwnd = hwnd
        self._estilo_original = user32.GetWindowLongW(hwnd, GWL_STYLE)
        self._fundo_do_windows = DWMSBT_AUTOMATICO  # o efeito de fundo da janela cheia, guardado ao virar bolinha
        # Guardados com a janela ainda no tamanho normal: é para eles que ela volta
        self.cheia = self._retangulo_janela()
        self.conteudo = self._retangulo_conteudo()

    def canto(self) -> Retangulo:
        monitor = user32.MonitorFromWindow(self._hwnd, MONITOR_DEFAULTTONEAREST)
        info = _InfoMonitor(cbSize=ctypes.sizeof(_InfoMonitor))
        user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        r = info.rcWork
        return retangulo_do_canto(Retangulo(r.left, r.top, r.right - r.left, r.bottom - r.top), self._escala())

    def _escala(self) -> float:
        return user32.GetDpiForWindow(self._hwnd) / 96 or 1

    # Só os bits da moldura mudam: o resto do estilo (inclusive se a janela está visível) fica como estiver agora
    def sem_moldura(self) -> None:
        self._trocar_estilo(self._estilo_atual() & ~MOLDURA)
        self._efeitos_do_windows(False)

    def com_moldura(self) -> None:
        self._efeitos_do_windows(True)
        self._trocar_estilo(self._estilo_atual() | (self._estilo_original & MOLDURA))

    def _efeitos_do_windows(self, ligados: bool) -> None:
        """O Windows 11 arredonda os cantos, contorna e sombreia a janela pelo retângulo dela, ignorando o recorte
        redondo: em volta da bolinha sobravam cantos brancos e uma sombra quadrada. Na bolinha, tudo isso sai.

        No modo escuro, o pywebview ainda liga o fundo translúcido do Windows 11 (Mica), também desenhado no
        retângulo inteiro: aparecia um quadrado cinza em volta da bolinha. Ele é desligado na bolinha e volta
        como estava na janela cheia."""
        if not ligados:
            self._fundo_do_windows = self._ler_atributo(DWMWA_SYSTEMBACKDROP_TYPE, self._fundo_do_windows)
        efeitos = ((DWMWA_NCRENDERING_POLICY, DWMNCRP_USEWINDOWSTYLE, DWMNCRP_DISABLED),
                   (DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DEFAULT, DWMWCP_DONOTROUND),
                   (DWMWA_BORDER_COLOR, DWMWA_COLOR_DEFAULT, DWMWA_COLOR_NONE),
                   (DWMWA_SYSTEMBACKDROP_TYPE, self._fundo_do_windows, DWMSBT_NENHUM))
        for atributo, ligado, desligado in efeitos:
            valor = ctypes.c_uint(ligado if ligados else desligado)
            dwmapi.DwmSetWindowAttribute(self._hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor))

    def _ler_atributo(self, atributo: int, padrao: int) -> int:
        valor = ctypes.c_uint(padrao)
        if dwmapi.DwmGetWindowAttribute(self._hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor)) != 0:
            return padrao
        return valor.value

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

    def posicionar_compacta(self, r: Retangulo) -> None:
        """A forma final da espera: a bolinha, a faixa arredondada com o nome e os botões em volta."""
        user32.SetWindowPos(self._hwnd, None, r.x, r.y, r.largura, r.altura, SWP_NOZORDER | SWP_NOACTIVATE)
        (ce, ct, cd, cb), (fe, ft, fd, fb), botoes = formas_compactas(self._escala())
        regiao = gdi32.CreateEllipticRgn(ce, ct, cd + 1, cb + 1)
        pecas = [gdi32.CreateRoundRectRgn(fe, ft, fd + 1, fb + 1, fb - ft, fb - ft)]
        pecas += [gdi32.CreateEllipticRgn(e, t, d + 1, b + 1) for e, t, d, b in botoes]
        for peca in pecas:
            gdi32.CombineRgn(regiao, regiao, peca, RGN_OR)
            gdi32.DeleteObject(peca)
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
