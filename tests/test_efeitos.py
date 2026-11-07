import unittest

import numpy as np

from merlin.config import PASTA_VOZES
from merlin.personalidades import PERSONALIDADES
from merlin.voz.catalogo import efeito_da_voz, todas_as_vozes
from merlin.voz.efeitos import EfeitoVoz, aplicar_efeito, cortar_silencio

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

    def test_vozes_proprias_das_personalidades_estao_no_seletor(self):
        vozes = todas_as_vozes()
        for p in PERSONALIDADES.values():
            for propria in p.vozes_proprias:
                self.assertEqual(vozes[propria.rotulo], propria.id)
                self.assertIs(efeito_da_voz(propria.id), propria.efeito)
                self.assertTrue((PASTA_VOZES / f"{propria.efeito.modelo}.onnx").is_file(), propria.efeito.modelo)

    def test_voz_do_piper_nao_tem_efeito(self):
        self.assertIsNone(efeito_da_voz("pt_BR-faber-medium"))


if __name__ == "__main__":
    unittest.main()


class TestEncurtarPausas(unittest.TestCase):
    def _voz(self, segundos):
        t = np.arange(int(segundos * TAXA)) / TAXA
        return (0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)

    def test_pausa_longa_no_meio_vira_curta(self):
        from merlin.voz.efeitos import PAUSA_MAXIMA, encurtar_pausas
        audio = np.concatenate([self._voz(1), np.zeros(int(1.2 * TAXA), np.float32), self._voz(1)])
        saida = encurtar_pausas(audio, TAXA)
        self.assertAlmostEqual(len(saida) / TAXA, 2 + PAUSA_MAXIMA, delta=0.05)

    def test_pausa_curta_fica_como_esta(self):
        from merlin.voz.efeitos import encurtar_pausas
        audio = np.concatenate([self._voz(1), np.zeros(int(0.2 * TAXA), np.float32), self._voz(1)])
        self.assertEqual(len(encurtar_pausas(audio, TAXA)), len(audio))

    def test_silencio_das_pontas_nao_e_mexido(self):
        from merlin.voz.efeitos import encurtar_pausas
        audio = np.concatenate([np.zeros(TAXA, np.float32), self._voz(1), np.zeros(TAXA, np.float32)])
        self.assertEqual(len(encurtar_pausas(audio, TAXA)), len(audio))  # as pontas são do cortar_silencio

    def test_audio_vazio_ou_mudo(self):
        from merlin.voz.efeitos import encurtar_pausas
        self.assertEqual(len(encurtar_pausas(np.zeros(0, np.float32), TAXA)), 0)
        self.assertEqual(len(encurtar_pausas(np.zeros(TAXA, np.float32), TAXA)), TAXA)
