import unittest

from merlin.audio.segmentador import DURACAO_TRECHO, Segmentador, trechos

TRECHO = bytes(1024)  # 512 amostras de 16 bits


def alimentar(segmentador, sequencia):
    """sequencia: lista de (chance de voz, segundos). Devolve as frases fechadas, em trechos."""
    frases = []
    for chance, segundos in sequencia:
        for _ in range(trechos(segundos)):
            frase = segmentador.adicionar(TRECHO, chance)
            if frase is not None:
                frases.append(len(frase) // len(TRECHO))
    return frases


class TestSegmentador(unittest.TestCase):
    def setUp(self):
        self.s = Segmentador(pausa_fim=1.0, duracao_maxima=25)

    def test_fala_e_para_fecha_uma_frase(self):
        frases = alimentar(self.s, [(0.0, 1), (0.9, 2), (0.0, 1.2)])
        self.assertEqual(len(frases), 1)
        # 2 s de voz, mais o que veio antes do início e a folga final, sem a pausa inteira
        self.assertAlmostEqual(frases[0] * DURACAO_TRECHO, 2 + 0.3 + 0.15, delta=0.15)

    def test_pausa_curta_no_meio_nao_corta(self):
        frases = alimentar(self.s, [(0.9, 1), (0.05, 0.7), (0.9, 1), (0.0, 1.2)])
        self.assertEqual(len(frases), 1)

    def test_pausa_longa_separa_em_duas(self):
        frases = alimentar(self.s, [(0.9, 1), (0.05, 1.2), (0.9, 1), (0.0, 1.2)])
        self.assertEqual(len(frases), 2)

    def test_so_fecha_depois_da_pausa_inteira(self):
        alimentar(self.s, [(0.9, 1), (0.0, 0.9)])
        self.assertTrue(self.s.ouvindo_frase)
        self.assertEqual(len(alimentar(self.s, [(0.0, 0.15)])), 1)

    def test_ruido_sem_voz_nao_abre_frase(self):
        self.assertEqual(alimentar(self.s, [(0.3, 5)]), [])
        self.assertFalse(self.s.ouvindo_frase)

    def test_estalo_curto_nao_abre_frase(self):
        self.assertEqual(alimentar(self.s, [(0.9, 0.05), (0.0, 2)]), [])

    def test_voz_muito_curta_e_descartada(self):
        self.assertEqual(alimentar(self.s, [(0.9, 0.15), (0.0, 2)]), [])

    def test_zona_incerta_mantem_a_frase_aberta(self):
        # Entre os limiares (voz baixa, fim de palavra) não conta como pausa
        frases = alimentar(self.s, [(0.9, 1), (0.4, 2), (0.0, 1.2)])
        self.assertEqual(len(frases), 1)
        self.assertGreater(frases[0] * DURACAO_TRECHO, 3)

    def test_frase_longa_demais_fecha_no_limite(self):
        s = Segmentador(pausa_fim=1.0, duracao_maxima=3)
        frases = alimentar(s, [(0.9, 7)])
        self.assertEqual(len(frases), 2)

    def test_descartar_esquece_a_frase(self):
        alimentar(self.s, [(0.9, 1)])
        self.s.descartar()
        self.assertFalse(self.s.ouvindo_frase)
        self.assertEqual(alimentar(self.s, [(0.0, 2)]), [])


if __name__ == "__main__":
    unittest.main()
