import unittest

import numpy as np

from merlin.config import EFEITOS_VOZ, VOZES, EfeitoVoz
from merlin.voz.efeitos import aplicar_efeito, cortar_silencio

TAXA = 22050


class TestEfeitos(unittest.TestCase):
    def setUp(self):
        self.efeito = EfeitoVoz(modelo="x", tom=0.85, lentidao=1.0, tremor=0.06, eco=0.22)
        self.audio = 0.5 * np.sin(2 * np.pi * 150 * np.arange(TAXA) / TAXA).astype(np.float32)

    def test_tom_menor_alonga_o_audio(self):
        saida = aplicar_efeito(self.audio, TAXA, self.efeito)
        self.assertGreater(len(saida), len(self.audio) / 0.85)

    def test_nunca_passa_do_limite(self):
        forte = self.audio * 2
        saida = aplicar_efeito(forte, TAXA, self.efeito)
        self.assertLessEqual(np.max(np.abs(saida)), 0.951)

    def test_corta_silencio_das_pontas(self):
        silencio = np.zeros(TAXA)  # 1 s
        cortado = cortar_silencio(np.concatenate([silencio, self.audio, silencio]), TAXA)
        self.assertLess(len(cortado), len(self.audio) + 0.2 * TAXA)
        self.assertGreater(len(cortado), len(self.audio))

    def test_silencio_total_fica_como_esta(self):
        self.assertEqual(len(cortar_silencio(np.zeros(100), TAXA)), 100)

    def test_toda_voz_com_efeito_esta_no_seletor(self):
        for voz in EFEITOS_VOZ:
            self.assertIn(voz, VOZES.values())


if __name__ == "__main__":
    unittest.main()
