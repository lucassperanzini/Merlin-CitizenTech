"""Manchas de incêndio: focos vizinhos juntados, com a área em chamas e a extensão estimadas.

Cada foco da FIRMS é o centro de um pixel do satélite, com largura (scan) e altura (track) em km. Pixels que se
encostam são o mesmo incêndio. A área da mancha é o chão coberto pelos pixels (o que se sobrepõe conta uma vez);
a extensão, a maior distância entre as pontas.

É uma ESTIMATIVA do fogo ativo na passagem do satélite, não da área queimada: fogo já apagado, ou escondido por
nuvem ou fumaça densa, não aparece, e dois incêndios muito próximos viram uma mancha só.
"""
import math
from collections import defaultdict

PIXEL_PADRAO_KM = 0.375  # VIIRS no centro da passagem: vale quando o foco vem sem scan e track (robô antigo)
FOLGA = 1.15  # pixels quase encostados também contam como vizinhos (a grade do satélite não segue a do mapa)
KM_POR_GRAU_LAT = 110.57
KM_POR_GRAU_LON = 111.32  # no equador; multiplicado pelo cosseno da latitude


def tamanho_do_pixel(foco) -> tuple[float, float]:
    """(largura, altura) em km, com a reserva quando o robô não informa."""
    scan, track = getattr(foco, "scan", None), getattr(foco, "track", None)
    return (scan if scan and scan > 0 else PIXEL_PADRAO_KM, track if track and track > 0 else PIXEL_PADRAO_KM)


def _em_km(latitude, longitude):
    """Coordenadas planas em km, boas para distâncias curtas (dentro de uma mancha)."""
    return longitude * KM_POR_GRAU_LON * math.cos(math.radians(latitude)), latitude * KM_POR_GRAU_LAT


def agrupar(pontos) -> list[int]:
    """pontos: [(latitude, longitude, largura_km, altura_km)]. Devolve, para cada ponto, o número do grupo dele.

    Dois pixels são vizinhos quando os retângulos se encostam (com a FOLGA). Uma grade de 1 km evita comparar
    todos com todos: com milhares de focos, só os das células vizinhas são comparados."""
    pai = list(range(len(pontos)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    planos = [(*_em_km(lat, lon), largura, altura) for lat, lon, largura, altura in pontos]
    celula = max([max(p[2], p[3]) for p in planos] + [PIXEL_PADRAO_KM]) * FOLGA  # o maior vizinho possível
    grade = defaultdict(list)
    for i, (x, y, _, _) in enumerate(planos):
        grade[(math.floor(x / celula), math.floor(y / celula))].append(i)
    for (cx, cy), membros in grade.items():
        vizinhos = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grade.get((cx + dx, cy + dy), ())]
        for i in membros:
            xi, yi, li, ai = planos[i]
            for j in vizinhos:
                if j <= i:
                    continue
                xj, yj, lj, aj = planos[j]
                if abs(xi - xj) <= (li + lj) / 2 * FOLGA and abs(yi - yj) <= (ai + aj) / 2 * FOLGA:
                    pai[raiz(i)] = raiz(j)
    return [raiz(i) for i in range(len(pontos))]


def _casco(pontos):
    """Casco convexo (monotone chain): as pontas da mancha, para medir a extensão sem comparar todos os pontos."""
    pontos = sorted(set(pontos))
    if len(pontos) <= 2:
        return pontos

    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    baixo, cima = [], []
    for p in pontos:
        while len(baixo) >= 2 and giro(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    for p in reversed(pontos):
        while len(cima) >= 2 and giro(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    return baixo[:-1] + cima[:-1]


RESOLUCAO_AREA_KM = 0.05  # a área é contada numa grade de 50 m: bem menor que um pixel (375 m ou mais)


def _area_da_uniao(retangulos) -> float:
    """Área coberta pelos pixels, contando uma vez só o chão em que eles se sobrepõem.
    A consulta cobre horas: o mesmo incêndio aparece em várias passagens do satélite, com pixels quase no mesmo
    lugar. Somar os pixels contaria esse chão duas ou três vezes."""
    cobertas = set()
    passo = RESOLUCAO_AREA_KM
    for x, y, largura, altura in retangulos:
        x0, x1 = round((x - largura / 2) / passo), round((x + largura / 2) / passo)
        y0, y1 = round((y - altura / 2) / passo), round((y + altura / 2) / passo)
        cobertas.update((i, j) for i in range(x0, x1) for j in range(y0, y1))
    return len(cobertas) * passo * passo


def medir(pontos) -> tuple[float, float]:
    """(área em km², extensão em km) de uma mancha. pontos: [(latitude, longitude, largura_km, altura_km)].
    A extensão vai de canto a canto dos pixels das pontas; uma mancha de um pixel só mede a diagonal dele."""
    planos = [(*_em_km(lat, lon), largura, altura) for lat, lon, largura, altura in pontos]
    area = _area_da_uniao(planos)
    # Os cantos de cada pixel: assim a extensão já inclui as bordas
    cantos = []
    for x, y, largura, altura in planos:
        cantos += [(x + sx * largura / 2, y + sy * altura / 2) for sx in (-1, 1) for sy in (-1, 1)]
    casco = _casco(cantos)
    extensao = max((math.dist(a, b) for i, a in enumerate(casco) for b in casco[i + 1:]), default=0.0)
    return area, extensao
