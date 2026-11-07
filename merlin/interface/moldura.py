"""Formato da janela no Windows: a bolinha no canto da tela, o cartão da janela ativa logo acima dela e a
transição entre os dois.
Usa a API do Windows direto no handle da janela, porque o pywebview não troca a moldura nem anima o tamanho."""
import ctypes
import ctypes.wintypes as wt
import math
import time
from typing import Callable, NamedTuple

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_STYLE = -16
WS_CAPTION = 0x00C00000  # barra de título e borda
WS_THICKFRAME = 0x00040000
MOLDURA = WS_CAPTION | WS_THICKFRAME
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20
MONITOR_DEFAULTTONEAREST = 2
dwmapi = ctypes.windll.dwmapi
DWMWA_NCRENDERING_POLICY, DWMNCRP_DISABLED = 2, 1
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND = 33, 1
DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE = 34, 0xFFFFFFFE
DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NENHUM = 38, 1

# A janela compacta: a bolinha em cima, uma faixa com o nome do assistente embaixo e, do lado de fora da bolinha,
# botões redondos num arco à esquerda (o lado de dentro da tela, já que a bolinha fica no canto direito).
# Medidas em pontos: viram pixels conforme a escala da tela, e são as mesmas que a página usa em CSS.
LADO_COMPACTO = 120  # diâmetro da bolinha
LARGURA_NOME = 150  # um pouco mais larga que a bolinha, para caber o nome
ESPACO_NOME = 4  # entre a bolinha e a faixa do nome
ALTURA_NOME = 24
BOTOES_COMPACTOS = ("engrenagem", "microfone", "debug")  # ids dos botões na página, de cima para baixo
ANGULOS_BOTOES = (148, 180, 212)  # graus a partir da direita, no sentido anti-horário: 180 é bem à esquerda
DIAMETRO_BOTAO = 28
ORBITA_BOTOES = 84  # do centro da bolinha ao centro de cada botão: sobra um vão entre eles e a bolinha
# Modo discreto: o balão com a resposta curta aparece à esquerda da bolinha. O espaço dele fica reservado na janela
# (fora do recorte, invisível e sem receber cliques) para ela não precisar mudar de tamanho quando ele aparece.
LARGURA_BALAO = 280
RAIO_BALAO = 14
MARGEM_COMPACTA = 18
RAIO_CARTAO = 16  # cantos arredondados do cartão da janela ativa
LARGURA_PAINEL = 360  # o painel do raciocínio, aberto à esquerda do cartão pela aba da borda (--painel na página)
LARGURA_ABA, ALTURA_ABA = 18, 64  # a aba que abre o painel, do lado de fora do cartão, à esquerda (--aba na página)
ESPACO_LISTA = 6  # entre a faixa do nome e a lista de assistentes (o mesmo vão na página)
DURACAO_ANIMACAO = 0.38  # segundos: a bolinha virando cartão e vice-versa
DURACAO_RAPIDA = 0.26  # segundos: painéis e listas que abrem e fecham dentro da mesma forma
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
    # Centro da bolinha: depois do espaço do balão, com o botão mais à esquerda encostado nele
    cx, cy = LARGURA_BALAO + ORBITA_BOTOES + raio_botao, raio
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
        # O balão termina um pouco antes dos botões e fica centrado na altura da bolinha
        "balao": {"direita": LARGURA_BALAO - 6, "centro_y": cy},
    }


def largura_visivel_compacta(escala: float) -> int:
    """A largura do que aparece da bolinha (com o nome e os botões), sem o espaço reservado ao balão."""
    return round((desenho_compacto()["largura"] - LARGURA_BALAO) * escala)


def tamanho_compacto(escala: float) -> tuple[int, int]:
    desenho = desenho_compacto()
    return round(desenho["largura"] * escala), round(desenho["altura"] * escala)


def retangulo_do_canto(area: Retangulo, escala: float, altura_extra: int = 0) -> Retangulo:
    """Canto inferior direito da área livre da tela (sem a barra de tarefas).
    altura_extra (em pontos) aumenta a janela embaixo da faixa do nome, para a lista de assistentes. A janela sobe
    esse tanto: a lista cabe embaixo do nome sem passar da área livre da tela."""
    largura, altura = tamanho_compacto(escala)
    altura += round(altura_extra * escala)
    margem = round(MARGEM_COMPACTA * escala)
    return Retangulo(area.x + area.largura - largura - margem, area.y + area.altura - altura - margem, largura, altura)


def retangulo_do_cartao(area: Retangulo, escala: float, largura: int, altura: int) -> Retangulo:
    """A janela ativa: encostada no canto inferior direito da área livre, onde fica a bolinha, crescendo para cima.
    Em telas baixas, encolhe para caber."""
    margem = round(MARGEM_COMPACTA * escala)
    largura = min(round(largura * escala), area.largura - 2 * margem)
    altura = min(round(altura * escala), area.altura - 2 * margem)
    return Retangulo(area.x + area.largura - largura - margem, area.y + area.altura - altura - margem, largura, altura)


def arredondamento_do_cartao(r: Retangulo, escala: float) -> float:
    """O arredondamento de posicionar() é uma fração do lado menor: converte o raio dos cantos para ela."""
    return min(1.0, 2 * RAIO_CARTAO * escala / max(1, min(r.largura, r.altura)))


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

    def canto(self, altura_extra: int = 0) -> Retangulo:
        return retangulo_do_canto(self._area_livre(), self._escala(), altura_extra)

    def cartao(self, largura: int, altura: int) -> tuple[Retangulo, float]:
        """Onde fica a janela ativa e o quanto arredondar os cantos dela."""
        escala = self._escala()
        r = retangulo_do_cartao(self._area_livre(), escala, largura, altura)
        return r, arredondamento_do_cartao(r, escala)

    def _area_livre(self) -> Retangulo:
        """A tela onde a janela está, sem a barra de tarefas."""
        monitor = user32.MonitorFromWindow(self._hwnd, MONITOR_DEFAULTTONEAREST)
        info = _InfoMonitor(cbSize=ctypes.sizeof(_InfoMonitor))
        user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        r = info.rcWork
        return Retangulo(r.left, r.top, r.right - r.left, r.bottom - r.top)

    def _escala(self) -> float:
        return user32.GetDpiForWindow(self._hwnd) / 96 or 1

    def sem_moldura(self) -> None:
        """A bolinha e o cartão são desenhados pela página: a janela fica sem barra de título e sem borda.
        Só os bits da moldura mudam; o resto do estilo (inclusive se a janela está visível) fica como estiver."""
        self._trocar_estilo(self._estilo_atual() & ~MOLDURA)
        self._desligar_efeitos_do_windows()

    def _desligar_efeitos_do_windows(self) -> None:
        """O Windows 11 arredonda os cantos, contorna e sombreia a janela pelo retângulo dela, ignorando o recorte:
        em volta da bolinha sobravam cantos brancos e uma sombra quadrada.

        No modo escuro, o pywebview ainda liga o fundo translúcido do Windows 11 (Mica), também desenhado no
        retângulo inteiro: aparecia um quadrado cinza em volta da bolinha."""
        efeitos = ((DWMWA_NCRENDERING_POLICY, DWMNCRP_DISABLED),
                   (DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND),
                   (DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE),
                   (DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NENHUM))
        for atributo, valor in efeitos:
            valor = ctypes.c_uint(valor)
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

    def posicionar_cartao(self, r: Retangulo, com_painel: float, com_aba: bool = True) -> None:
        """O cartão no lugar dele e, no modo debug, a aba do raciocínio do lado de fora, à esquerda.
        com_painel vai de 0 (fechado) a 1 (aberto); os valores do meio são os quadros da transição.

        No modo debug, a janela já tem o espaço do painel reservado à esquerda e NÃO muda de tamanho ao abrir ou
        fechar: só o recorte (o que aparece) cresce para a esquerda. Mudar o tamanho pela borda esquerda fazia o
        cartão tremer, porque o Windows mostra o desenho antigo deslocado até a página se redesenhar."""
        escala = self._escala()
        janela = self.janela_do_cartao(r, com_aba)
        self._mover(janela)
        painel = round(LARGURA_PAINEL * escala * float(com_painel)) if com_aba else 0
        self._recortar_lado_direito(janela, r.largura + painel, round(2 * RAIO_CARTAO * escala), com_aba)

    def _mover(self, r: Retangulo) -> None:
        """Muda a posição e o tamanho só se mudaram: um SetWindowPos igual ainda faria a página se redesenhar."""
        if self._retangulo_atual() != r:
            user32.SetWindowPos(self._hwnd, None, r.x, r.y, r.largura, r.altura, SWP_NOZORDER | SWP_NOACTIVATE)

    def _retangulo_atual(self) -> Retangulo:
        atual = wt.RECT()
        user32.GetWindowRect(self._hwnd, ctypes.byref(atual))
        return Retangulo(atual.left, atual.top, atual.right - atual.left, atual.bottom - atual.top)

    def _recortar_lado_direito(self, janela: Retangulo, visivel: int, diametro: int, com_aba: bool) -> None:
        """Mostra só a faixa da direita da janela, com a largura visivel; com a aba, ela fica na borda esquerda
        dessa faixa, entrando um pouco nela para emendar sem fresta."""
        borda = janela.largura - visivel
        regiao = gdi32.CreateRoundRectRgn(borda, 0, janela.largura + 1, janela.altura + 1, diametro, diametro)
        if com_aba:
            escala = self._escala()
            aba, altura_aba = round(LARGURA_ABA * escala), round(ALTURA_ABA * escala)
            topo = (janela.altura - altura_aba) // 2
            peca = gdi32.CreateRoundRectRgn(borda - aba, topo, borda + diametro, topo + altura_aba + 1,
                                            diametro, diametro)
            gdi32.CombineRgn(regiao, regiao, peca, RGN_OR)
            gdi32.DeleteObject(peca)
        user32.SetWindowRgn(self._hwnd, regiao, True)  # o Windows passa a ser o dono da região

    def janela_do_cartao(self, r: Retangulo, com_aba: bool = True) -> Retangulo:
        """O retângulo da janela para o cartão r. No modo debug (com a aba), já inclui à esquerda o espaço do
        painel do raciocínio e da aba, para a janela não precisar mudar de tamanho ao abrir o painel."""
        if not com_aba:
            return r
        escala = self._escala()
        extra = round(LARGURA_ABA * escala) + round(LARGURA_PAINEL * escala)
        return Retangulo(r.x - extra, r.y, r.largura + extra, r.altura)

    def animar_cartao(self, canto: Retangulo, cartao: Retangulo, com_aba: bool, abrindo: bool) -> None:
        """A bolinha virando cartão (abrindo) ou o cartão voltando para a bolinha. A janela vai do canto até o
        retângulo final do cartão (com o espaço do painel, no modo debug), mas só a faixa da direita aparece,
        do tamanho da bolinha ao do cartão, com os cantos indo de redondos a arredondados."""
        cheia = self.janela_do_cartao(cartao, com_aba)
        bolinha = largura_visivel_compacta(self._escala())  # o espaço do balão, à esquerda, não aparece
        lado_bolinha = min(bolinha, canto.altura)
        diametro_cartao = round(2 * RAIO_CARTAO * self._escala())

        def quadro(e):
            p = e if abrindo else 1 - e
            r = interpolar(canto, cheia, p)
            self._mover(r)
            visivel = round(bolinha + (cartao.largura - bolinha) * p)
            diametro = round(lado_bolinha + (diametro_cartao - lado_bolinha) * p)
            self._recortar_lado_direito(r, min(visivel, r.largura), diametro, False)

        self.transicao(quadro)

    def posicionar_compacta(self, r: Retangulo, com_botoes: bool = False, com_menu: bool = False,
                            balao: tuple[float, float, float, float] | None = None) -> None:
        """A forma final da espera: a bolinha e a faixa arredondada com o nome. Os botões em volta só entram no
        recorte com o mouse por perto: fora do recorte, eles nem aparecem nem recebem cliques.
        Com a lista de assistentes aberta (clique no nome), entra também a área dela, embaixo do nome.
        balao: (x, y, largura, altura) em pontos, do balão do modo discreto, quando ele está na tela."""
        self._mover(r)
        (ce, ct, cd, cb), (fe, ft, fd, fb), botoes = formas_compactas(self._escala())
        regiao = gdi32.CreateEllipticRgn(ce, ct, cd + 1, cb + 1)
        pecas = [gdi32.CreateRoundRectRgn(fe, ft, fd + 1, fb + 1, fb - ft, fb - ft)]
        if com_botoes:
            pecas += [gdi32.CreateEllipticRgn(e, t, d + 1, b + 1) for e, t, d, b in botoes]
        topo = fb + round(ESPACO_LISTA * self._escala())
        if com_menu and r.altura > topo:  # a lista: na largura da faixa do nome, embaixo dela até o fim da janela
            diametro = round(2 * RAIO_CARTAO * self._escala())
            pecas.append(gdi32.CreateRoundRectRgn(fe, topo, fd + 1, r.altura + 1, diametro, diametro))
        if balao:
            escala = self._escala()
            x, y, largura, altura = (round(v * escala) for v in balao)
            diametro = round(2 * RAIO_BALAO * escala)
            pecas.append(gdi32.CreateRoundRectRgn(x, y, x + largura + 1, y + altura + 1, diametro, diametro))
        for peca in pecas:
            gdi32.CombineRgn(regiao, regiao, peca, RGN_OR)
            gdi32.DeleteObject(peca)
        user32.SetWindowRgn(self._hwnd, regiao, True)  # o Windows passa a ser o dono da região

    def transicao(self, quadro: Callable[[float], None], duracao: float = DURACAO_ANIMACAO) -> None:
        """A base de todo abrir e fechar da janela: chama quadro(e) a cada quadro, com e indo de 0 a 1 de forma
        suave (rápido no começo, devagar no fim); o último quadro é sempre 1, a forma final.
        Cada transição só descreve como a janela fica em e; o ritmo e a suavidade são os mesmos para todas."""
        inicio = time.perf_counter()
        while True:
            t = min((time.perf_counter() - inicio) / duracao, 1.0)
            quadro(suavizar(t))
            if t >= 1.0:
                return
            time.sleep(1 / QUADROS_POR_SEGUNDO)

    def animar_painel(self, cartao: Retangulo, de: float, para: float, com_aba: bool = True) -> None:
        """O painel do raciocínio abrindo (de 0 para 1) ou fechando (de 1 para 0) ao lado do cartão."""
        self.transicao(lambda e: self.posicionar_cartao(cartao, de + (para - de) * e, com_aba), DURACAO_RAPIDA)

    def animar_lista(self, de: int, para: int, com_botoes: bool) -> None:
        """A lista de assistentes abrindo (ou fechando) embaixo do nome da bolinha: de e para em pontos."""
        self.transicao(lambda e: self.posicionar_compacta(self.canto(de + (para - de) * e), com_botoes, True),
                       DURACAO_RAPIDA)

    def _trocar_estilo(self, estilo: int) -> None:
        user32.SetWindowLongW(self._hwnd, GWL_STYLE, estilo)
        user32.SetWindowPos(self._hwnd, None, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
