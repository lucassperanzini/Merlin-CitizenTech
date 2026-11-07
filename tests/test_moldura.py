import math
import unittest

from merlin.interface.moldura import (Moldura, Retangulo, arredondamento_do_cartao, desenho_compacto, formas_compactas,
                                     interpolar, retangulo_do_canto, retangulo_do_cartao, suavizar,
                                     tamanho_compacto)


class TestMoldura(unittest.TestCase):
    def test_canto_inferior_direito_da_area_livre(self):
        area = Retangulo(0, 0, 1920, 1032)  # tela 1080 com barra de tarefas de 48
        # 150 de largura (bolinha de 120 + folga para o nome) por 148 de altura (120 + 4 + faixa de 24)
        self.assertEqual(retangulo_do_canto(area, 1.0), Retangulo(1449, 866, 453, 148))

    def test_canto_acompanha_a_escala_da_tela(self):
        r = retangulo_do_canto(Retangulo(0, 0, 2560, 1392), 1.5)
        self.assertEqual((r.largura, r.altura), (680, 222))
        self.assertEqual((r.x + r.largura, r.y + r.altura), (2560 - 27, 1392 - 27))

    def test_lista_de_assistentes_cresce_a_janela_para_baixo_do_nome(self):
        area = Retangulo(0, 0, 1920, 1032)
        sem, com = retangulo_do_canto(area, 1.0), retangulo_do_canto(area, 1.0, 120)
        self.assertEqual(com.altura, sem.altura + 120)
        self.assertEqual(com.y + com.altura, sem.y + sem.altura)  # a base continua dentro da área livre
        self.assertEqual(com.y, sem.y - 120)  # a bolinha e o nome sobem para a lista caber embaixo

    def test_canto_em_monitor_secundario(self):
        r = retangulo_do_canto(Retangulo(-1920, 0, 1920, 1080), 1.0)
        self.assertEqual(r.x, -471)

    def test_formas_da_janela_compacta(self):
        circulo, faixa, botoes = formas_compactas(1.0)
        self.assertEqual(circulo, (318, 0, 438, 120))  # a bolinha à direita, depois do balão e dos botões
        self.assertEqual(faixa, (303, 124, 453, 148))  # o nome embaixo, centralizado na bolinha
        self.assertEqual(len(botoes), 3)  # configurações, microfone e modo debug
        self.assertEqual(botoes[1], (280, 46, 308, 74))  # o do meio, bem à esquerda e na altura do centro
        self.assertEqual(120 - botoes[2][3], botoes[0][1])  # os outros dois, simétricos
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
        self.assertEqual(tamanho_compacto(1.0), (453, 148))

    def test_cartao_fica_no_canto_direito_acima_da_bolinha(self):
        area = Retangulo(0, 0, 1920, 1032)
        cartao = retangulo_do_cartao(area, 1.0, 400, 620)
        canto = retangulo_do_canto(area, 1.0)
        self.assertEqual(cartao, Retangulo(1920 - 18 - 400, 1032 - 18 - 620, 400, 620))
        # Mesma borda direita e mesma base da bolinha: o cartão cresce a partir dela, sem cobrir o centro da tela
        self.assertEqual(cartao.x + cartao.largura, canto.x + canto.largura)
        self.assertEqual(cartao.y + cartao.altura, canto.y + canto.altura)
        self.assertGreater(cartao.x, area.largura // 2)

    def test_cartao_encolhe_em_tela_baixa_e_acompanha_a_escala(self):
        self.assertEqual(retangulo_do_cartao(Retangulo(0, 0, 1366, 500), 1.0, 400, 620).altura, 500 - 36)
        self.assertEqual(retangulo_do_cartao(Retangulo(0, 0, 3840, 2100), 1.5, 400, 620).largura, 600)

    def test_cantos_do_cartao_tem_raio_fixo(self):
        self.assertAlmostEqual(arredondamento_do_cartao(Retangulo(0, 0, 400, 620), 1.0), 32 / 400)
        self.assertAlmostEqual(arredondamento_do_cartao(Retangulo(0, 0, 600, 930), 1.5), 48 / 600)

    def test_transicao_vai_de_0_a_1_sempre_crescendo_e_termina_na_forma_final(self):
        quadros = []
        Moldura.transicao(object.__new__(Moldura), quadros.append, duracao=0.05)
        self.assertGreater(len(quadros), 1)
        self.assertEqual(quadros[-1], 1.0)
        self.assertEqual(quadros, sorted(quadros))

    def test_balao_fica_a_esquerda_dos_botoes(self):
        desenho = desenho_compacto()
        self.assertLess(desenho["balao"]["direita"], min(b["x"] for b in desenho["botoes"]))
        self.assertEqual(desenho["balao"]["centro_y"], desenho["bolinha"]["lado"] / 2)

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
