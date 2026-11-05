import unittest
from unittest import mock

from merlin.acoes.controles import LeituraBotoes, e_botao_da_barra_de_titulo
from merlin.acoes.janelas import JanelaAberta
from merlin.acoes.ver_botoes import VerBotoes, descrever_leitura, nome_para_falar
from merlin.ia.intencoes import Intencao, TipoIntencao

CHROME = JanelaAberta(1, 1, "chrome", "Banco - Minha conta")
CALC = JanelaAberta(2, 2, "ApplicationFrameHost", "Calculadora")


def leitura(nomes=(), sem_nome=0, incompleta=False):
    return LeituraBotoes(list(nomes), sem_nome, incompleta)


class TestDescricao(unittest.TestCase):
    def test_um_botao(self):
        self.assertEqual(descrever_leitura("o word", leitura(["Salvar"])), "No word, vejo um botão: Salvar.")

    def test_varios(self):
        texto = descrever_leitura("a Calculadora", leitura(["Salvar", "Abrir"]))
        self.assertEqual(texto, "Na Calculadora, vejo 2 botões: Salvar, Abrir.")

    def test_contracao_no_meio_da_frase(self):
        self.assertIn("botões no jogo.", descrever_leitura("o jogo", leitura()))

    def test_muitos_cita_so_alguns(self):
        nomes = [f"B{i}" for i in range(20)]
        texto = descrever_leitura("o word", leitura(nomes))
        self.assertIn("20 botões", texto)
        self.assertIn("B7", texto)
        self.assertNotIn("B8", texto)
        self.assertIn("e mais 12", texto)

    def test_incompleta_avisa(self):
        self.assertIn("não consegui ler a janela inteira", descrever_leitura("x", leitura(["A", "B"], incompleta=True)))

    def test_nenhum_explica(self):
        self.assertIn("pode não informar", descrever_leitura("o jogo", leitura()))

    def test_so_icones_explica(self):
        self.assertIn("não têm nome", descrever_leitura("o app", leitura(sem_nome=5)))


class TestBarraDeTitulo(unittest.TestCase):
    def test_comandos_da_janela_sao_ignorados(self):
        for nome in ("Minimizar Calculadora", "Maximizar Calculadora", "Fechar Calculadora", "Close Calculadora"):
            self.assertTrue(e_botao_da_barra_de_titulo(nome, "Calculadora"), nome)

    def test_botoes_de_verdade_sao_mantidos(self):
        for nome in ("Fechar", "Fechar aba", "Fechar Calculadora científica", "Limpar", "Minimizar tudo"):
            self.assertFalse(e_botao_da_barra_de_titulo(nome, "Calculadora"), nome)


class TestNomeFalado(unittest.TestCase):
    def test_usa_o_programa_e_nao_o_titulo(self):
        self.assertEqual(nome_para_falar(CHROME), "o chrome")  # o título pode ter dados pessoais

    def test_app_da_loja_usa_o_titulo(self):
        self.assertEqual(nome_para_falar(CALC), "a Calculadora")


class TestAcao(unittest.TestCase):
    def setUp(self):
        for alvo, valor in (("merlin.acoes.janelas.listar_janelas", [CHROME, CALC]),
                            ("merlin.acoes.janelas.janela_em_uso", CHROME)):
            p = mock.patch(alvo, return_value=valor)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("merlin.acoes.controles.ler_botoes", return_value=leitura(["Salvar"]))
        self.ler = p.start()
        self.addCleanup(p.stop)

    def _ver(self, alvo):
        return VerBotoes()(Intencao(TipoIntencao.VER_BOTOES, alvo, "x"))

    def test_sem_programa_le_a_janela_em_uso(self):
        for alvo in ("", "merlin", "aqui", "botões", "tela", "essa janela"):
            self.ler.reset_mock()
            self._ver(alvo)
            self.ler.assert_called_once_with(CHROME.hwnd, CHROME.titulo)

    def test_programa_citado_le_a_janela_dele(self):
        self._ver("calculadora")
        self.ler.assert_called_once_with(CALC.hwnd, CALC.titulo)

    def test_programa_fechado_avisa_sem_ler(self):
        r = self._ver("excel")
        self.ler.assert_not_called()
        self.assertIn("Não encontrei excel", r.fala)

    def test_nenhuma_janela_aberta(self):
        with mock.patch("merlin.acoes.janelas.janela_em_uso", return_value=None):
            self.assertIn("nenhuma janela", self._ver("").fala)


if __name__ == "__main__":
    unittest.main()
