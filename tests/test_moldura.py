import math
import unittest

from merlin.interface.moldura import (Retangulo, desenho_compacto, formas_compactas, interpolar,
                                     retangulo_do_canto, suavizar, tamanho_compacto)


class TestMoldura(unittest.TestCase):
    def test_canto_inferior_direito_da_area_livre(self):
        area = Retangulo(0, 0, 1920, 1032)  # tela 1080 com barra de tarefas de 48
        # 150 de largura (bolinha de 120 + folga para o nome) por 148 de altura (120 + 4 + faixa de 24)
        self.assertEqual(retangulo_do_canto(area, 1.0), Retangulo(1729, 866, 173, 148))

    def test_canto_acompanha_a_escala_da_tela(self):
        r = retangulo_do_canto(Retangulo(0, 0, 2560, 1392), 1.5)
        self.assertEqual((r.largura, r.altura), (260, 222))
        self.assertEqual((r.x + r.largura, r.y + r.altura), (2560 - 27, 1392 - 27))

    def test_canto_em_monitor_secundario(self):
        r = retangulo_do_canto(Retangulo(-1920, 0, 1920, 1080), 1.0)
        self.assertEqual(r.x, -191)

    def test_formas_da_janela_compacta(self):
        circulo, faixa, botoes = formas_compactas(1.0)
        self.assertEqual(circulo, (38, 0, 158, 120))  # a bolinha à direita, deixando lugar para os botões
        self.assertEqual(faixa, (23, 124, 173, 148))  # o nome embaixo, centralizado na bolinha
        self.assertEqual(len(botoes), 3)
        self.assertEqual(botoes[1], (0, 46, 28, 74))  # o do meio, bem à esquerda e na altura do centro
        circulo, faixa, _ = formas_compactas(1.5)
        self.assertEqual(circulo[2] - circulo[0], 180)  # acompanha a escala da tela
        self.assertEqual(faixa[3], 222)

    def test_botoes_ficam_fora_da_bolinha_e_dentro_da_janela(self):
        desenho = desenho_compacto()
        b = desenho["bolinha"]
        centro, raio = (b["x"] + b["lado"] / 2, b["y"] + b["lado"] / 2), b["lado"] / 2
        for botao in desenho["botoes"]:
            r = botao["lado"] / 2
            x, y = botao["x"] + r, botao["y"] + r
            self.assertGreater(math.dist((x, y), centro), raio + r)  # não encosta na bolinha
            self.assertGreaterEqual(botao["x"], 0)
            self.assertGreaterEqual(botao["y"], 0)
            self.assertLessEqual(botao["y"] + botao["lado"], desenho["nome"]["y"])  # nem na faixa do nome
        self.assertEqual(tamanho_compacto(1.0), (173, 148))

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
