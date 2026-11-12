import unittest
from types import SimpleNamespace

from merlin.alertas import manchas

GRAU_LAT_KM = 110.57


def ao_lado(lat, lon, km_norte=0.0, km_leste=0.0):
    """Um ponto a tantos km de outro (para montar pixels vizinhos)."""
    import math
    return lat + km_norte / GRAU_LAT_KM, lon + km_leste / (111.32 * math.cos(math.radians(lat)))


class TestAgrupar(unittest.TestCase):
    def test_pixels_que_se_encostam_sao_o_mesmo_incendio(self):
        a = (-10.0, -50.0)
        b = ao_lado(*a, km_leste=0.4)  # pixel de 0,4 km: encostado em a
        c = ao_lado(*b, km_norte=0.4)  # encostado em b (e na diagonal de a)
        longe = ao_lado(*a, km_leste=3)
        grupos = manchas.agrupar([(*p, 0.4, 0.4) for p in (a, b, c, longe)])
        self.assertEqual(len({grupos[0], grupos[1], grupos[2]}), 1)
        self.assertNotEqual(grupos[0], grupos[3])

    def test_pixel_maior_alcanca_mais_longe(self):
        a = (-10.0, -50.0)
        b = ao_lado(*a, km_leste=0.7)
        self.assertNotEqual(*manchas.agrupar([(*a, 0.375, 0.375), (*b, 0.375, 0.375)]))  # vão de 0,3 km
        self.assertEqual(*manchas.agrupar([(*a, 0.7, 0.7), (*b, 0.7, 0.7)]))  # nas bordas da passagem: encostam

    def test_muitos_focos_rapido(self):
        import time
        pontos = [(-10 + i * 0.001, -50 + j * 0.001, 0.4, 0.4) for i in range(60) for j in range(60)]
        inicio = time.perf_counter()
        self.assertEqual(len(set(manchas.agrupar(pontos))), 1)  # 3.600 pixels encostados: um incêndio só
        self.assertLess(time.perf_counter() - inicio, 2)


class TestMedir(unittest.TestCase):
    def test_um_pixel(self):
        area, extensao = manchas.medir([(-10.0, -50.0, 0.4, 0.3)])
        self.assertAlmostEqual(area, 0.12, places=2)
        self.assertAlmostEqual(extensao, 0.5, places=2)  # a diagonal

    def test_fileira_de_pixels(self):
        a = (-10.0, -50.0)
        pontos = [(*ao_lado(*a, km_leste=0.4 * i), 0.4, 0.4) for i in range(5)]
        area, extensao = manchas.medir(pontos)
        self.assertAlmostEqual(area, 0.8, delta=0.03)  # 5 × 0,16 km²
        self.assertAlmostEqual(extensao, (2.0 ** 2 + 0.4 ** 2) ** 0.5, delta=0.03)  # de canto a canto

    def test_mesmo_chao_em_duas_passagens_conta_uma_vez(self):
        mesmo = [(-10.0, -50.0, 0.4, 0.4), (-10.0, -50.0001, 0.4, 0.4)]  # o mesmo fogo, visto duas vezes
        area, _ = manchas.medir(mesmo)
        self.assertAlmostEqual(area, 0.16, delta=0.02)

    def test_sem_tamanho_usa_o_pixel_padrao(self):
        self.assertEqual(manchas.tamanho_do_pixel(SimpleNamespace(scan=None, track=0)), (0.375, 0.375))
        self.assertEqual(manchas.tamanho_do_pixel(SimpleNamespace()), (0.375, 0.375))  # robô antigo
        self.assertEqual(manchas.tamanho_do_pixel(SimpleNamespace(scan=0.5, track=0.45)), (0.5, 0.45))


if __name__ == "__main__":
    unittest.main()
