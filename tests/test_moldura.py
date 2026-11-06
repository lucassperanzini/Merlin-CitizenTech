import unittest

from merlin.interface.moldura import Retangulo, interpolar, retangulo_do_canto, suavizar


class TestMoldura(unittest.TestCase):
    def test_canto_inferior_direito_da_area_livre(self):
        area = Retangulo(0, 0, 1920, 1032)  # tela 1080 com barra de tarefas de 48
        self.assertEqual(retangulo_do_canto(area, 1.0), Retangulo(1782, 894, 120, 120))

    def test_canto_acompanha_a_escala_da_tela(self):
        r = retangulo_do_canto(Retangulo(0, 0, 2560, 1392), 1.5)
        self.assertEqual((r.largura, r.altura), (180, 180))
        self.assertEqual((r.x + r.largura, r.y + r.altura), (2560 - 27, 1392 - 27))

    def test_canto_em_monitor_secundario(self):
        r = retangulo_do_canto(Retangulo(-1920, 0, 1920, 1080), 1.0)
        self.assertEqual(r.x, -138)

    def test_interpolar_vai_do_inicio_ao_fim(self):
        de, para = Retangulo(0, 0, 100, 100), Retangulo(200, 100, 300, 500)
        self.assertEqual(interpolar(de, para, 0), de)
        self.assertEqual(interpolar(de, para, 1), para)
        self.assertEqual(interpolar(de, para, 0.5), Retangulo(100, 50, 200, 300))

    def test_suavizar_comeca_rapido_e_termina_no_lugar(self):
        self.assertEqual(suavizar(0), 0)
        self.assertEqual(suavizar(1), 1)
        self.assertGreater(suavizar(0.5), 0.5)


if __name__ == "__main__":
    unittest.main()
