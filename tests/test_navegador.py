import unittest
from unittest import mock

from merlin.acoes.abrir_programa import encontrar_programa, resolver_nome
from merlin.acoes.fechar_programa import FecharPrograma
from merlin.acoes.janelas import JanelaAberta
from merlin.acoes.navegador import Navegador, e_navegador_generico
from merlin.ia.intencoes import Intencao, TipoIntencao

# Parte da lista real de programas do PC onde o bug apareceu
INSTALADOS = ["google chrome", "microsoft edge", "narrador", "agendador de tarefas", "calculadora", "bloco de notas",
              "visual studio code", "visual studio", "spotify", "discord", "steam", "steamvr", "paint", "word",
              "gerenciador de tarefas", "obsidian"]
CHROME = Navegador("google chrome", "chrome")


class TestNaoAbreOProgramaErrado(unittest.TestCase):
    def test_navegador_nunca_vira_narrador_nem_agendador(self):
        for pedido in ("navegador", "o navegador", "navegador de internet"):
            self.assertNotIn(encontrar_programa(pedido, INSTALADOS), ("narrador", "agendador de tarefas"), pedido)

    def test_nomes_que_continuam_funcionando(self):
        casos = {"chrome": "google chrome", "Chrome": "google chrome", "edge": "microsoft edge",
                 "narrador": "narrador", "calculadora": "calculadora", "calc": "calculadora", "vs code": "visual studio code",
                 "spotify": "spotify", "steam": "steam", "crome": "google chrome", "spotfy": "spotify",
                 "gerenciador de tarefas": "gerenciador de tarefas"}
        for pedido, esperado in casos.items():
            self.assertEqual(encontrar_programa(pedido, INSTALADOS), esperado, pedido)

    def test_ambiguo_nao_chuta(self):
        self.assertIsNone(encontrar_programa("visual", INSTALADOS))  # visual studio ou visual studio code?

    def test_sem_nada_parecido(self):
        for pedido in ("youtube", "xyzabc", "agenda"):
            self.assertIsNone(encontrar_programa(pedido, INSTALADOS), pedido)


class TestNavegadorPadrao(unittest.TestCase):
    def test_palavras_genericas(self):
        for nome in ("navegador", "o navegador", "Navegador", "navegador de internet", "browser", "internet"):
            self.assertTrue(e_navegador_generico(nome), nome)
        self.assertFalse(e_navegador_generico("chrome"))

    def test_abre_o_navegador_padrao(self):
        with mock.patch("merlin.acoes.navegador.navegador_padrao", return_value=CHROME):
            self.assertEqual(resolver_nome("navegador", INSTALADOS), "google chrome")

    def test_sem_navegador_padrao_conhecido_nao_abre_nada(self):
        with mock.patch("merlin.acoes.navegador.navegador_padrao", return_value=None):
            self.assertIsNone(resolver_nome("navegador", INSTALADOS))

    def test_fecha_o_navegador_padrao(self):
        janelas = [JanelaAberta(1, 1, "chrome", "Google"), JanelaAberta(2, 2, "Narrator", "Narrador")]
        with mock.patch("merlin.acoes.navegador.navegador_padrao", return_value=CHROME), \
                mock.patch("merlin.acoes.janelas.listar_janelas", return_value=janelas), \
                mock.patch("merlin.acoes.janelas.pedir_fechamento", return_value=True) as pedir, \
                mock.patch("merlin.acoes.janelas.ainda_aberta", return_value=False):
            FecharPrograma()(Intencao(TipoIntencao.FECHAR_PROGRAMA, "navegador", "x"))
        pedir.assert_called_once_with(janelas[0])


if __name__ == "__main__":
    unittest.main()
