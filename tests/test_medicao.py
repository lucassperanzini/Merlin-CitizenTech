import unittest

import numpy as np

from merlin.audio.medicao import DetectorInterrupcao, calcular_nivel, volume

BLOCO = 1024
SEGUNDOS_POR_BLOCO = BLOCO / 16000
LIMIAR = 300


def onda(rms):
    return (np.sign(np.sin(np.arange(BLOCO))) * rms).astype(np.int16).tobytes()


def blocos(segundos):
    return int(segundos / SEGUNDOS_POR_BLOCO)


def detectar(volumes):
    detector = DetectorInterrupcao()
    return any(detector.analisar(v, LIMIAR, i * SEGUNDOS_POR_BLOCO) for i, v in enumerate(volumes))


class TestNivel(unittest.TestCase):
    def test_volume_vazio_e_zero(self):
        self.assertEqual(volume(b""), 0.0)

    def test_abaixo_do_limiar_e_zero(self):
        self.assertEqual(calcular_nivel(onda(200), LIMIAR), 0.0)

    def test_silencio_e_zero(self):
        self.assertEqual(calcular_nivel(onda(0), LIMIAR), 0.0)

    def test_nivel_cresce_com_o_volume(self):
        niveis = [calcular_nivel(onda(rms), LIMIAR) for rms in (600, 1200, 2500, 5000, 9000)]
        self.assertEqual(niveis, sorted(niveis))
        self.assertGreater(niveis[0], 0)
        self.assertLessEqual(niveis[-1], 1.0)

    def test_limiar_invalido_e_zero(self):
        self.assertEqual(calcular_nivel(onda(5000), 0), 0.0)


class TestDetectorInterrupcao(unittest.TestCase):
    def setUp(self):
        gerador = np.random.default_rng(1)
        self.eco = list(gerador.uniform(500, 1500, blocos(20)))

    def test_so_o_eco_nao_interrompe(self):
        self.assertFalse(detectar(self.eco))

    def test_estalo_curto_nao_interrompe(self):
        self.assertFalse(detectar(self.eco[:blocos(3)] + [9000] * blocos(0.1) + self.eco[:blocos(3)]))

    def test_voz_forte_interrompe(self):
        self.assertTrue(detectar(self.eco[:blocos(3)] + [6000] * blocos(1)))

    def test_pausas_entre_silabas_nao_impedem(self):
        self.assertTrue(detectar(self.eco[:blocos(3)] + ([6000] * 2 + [800]) * 8))

    def test_voz_mais_fraca_que_o_eco_nao_interrompe(self):
        self.assertFalse(detectar(self.eco[:blocos(3)] + [1200] * blocos(2)))

    def test_sem_eco_voz_normal_interrompe(self):
        self.assertTrue(detectar([30] * blocos(2) + [1500] * blocos(1)))

    def test_durante_o_aprendizado_nao_interrompe(self):
        self.assertFalse(detectar([9000] * blocos(0.4)))


if __name__ == "__main__":
    unittest.main()
