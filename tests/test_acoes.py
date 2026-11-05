import unittest
from unittest import mock

from merlin.acoes.abrir_programa import AbrirPrograma, encontrar_programa
from merlin.acoes.fechar_programa import FecharPrograma, descrever_alvo
from merlin.acoes.janelas import JanelaAberta, escolher_janelas
from merlin.acoes.web import PesquisarWeb, montar_url
from merlin.estado import EstadoAssistente
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.sessao import Sessao
from tests.falsos import CanalFalso, LocutorFalso


def janela(programa, titulo, hwnd=1):
    return JanelaAberta(hwnd, hwnd, programa, titulo)


JANELAS = [
    janela("chrome", "Spotify - Minha playlist - Google Chrome", 1),
    janela("chrome", "Gmail - Google Chrome", 2),
    janela("Code", "chrome.py - Projeto - Visual Studio Code", 3),
    janela("WINWORD", "Relatório - Word", 4),
    janela("ApplicationFrameHost", "Calculadora", 5),
    janela("notepad", "Sem título - Bloco de Notas", 6),
    janela("Discord", "Geral - Discord", 7),
    janela("Discord_helper", "Discord ajuda", 8),
]


def programas(nome):
    achadas, pelo_titulo = escolher_janelas(nome, JANELAS)
    return sorted({j.programa for j in achadas}), pelo_titulo


class TestEscolherJanelas(unittest.TestCase):
    def test_casos(self):
        casos = [
            ("chrome", ["chrome"], False),  # pelo programa, não pelo arquivo chrome.py aberto no VS Code
            ("Chrome", ["chrome"], False),
            ("google chrome", ["chrome"], False),
            ("word", ["WINWORD"], False),
            ("calculadora", ["ApplicationFrameHost"], True),
            ("bloco de notas", ["notepad"], True),  # não pode cair no "code" dentro de "blocOdenotas"
            ("spotify", ["chrome"], True),
            ("discord", ["Discord", "Discord_helper"], False),
            ("crome", ["chrome"], False),
            ("excel", [], True),
            ("a", [], False),
        ]
        for nome, esperado, pelo_titulo in casos:
            self.assertEqual(programas(nome), (esperado, pelo_titulo), nome)

    def test_pelo_titulo_pega_so_a_janela_certa(self):
        achadas, _ = escolher_janelas("spotify", JANELAS)
        self.assertEqual([j.hwnd for j in achadas], [1])


class TestDescricao(unittest.TestCase):
    def test_descricoes(self):
        self.assertEqual(descrever_alvo([JANELAS[4]], True), "a janela Calculadora")
        self.assertEqual(descrever_alvo(JANELAS[:2], False), "as 2 janelas de chrome")
        self.assertEqual(descrever_alvo([JANELAS[3]], False), "WINWORD")


class TestFecharPrograma(unittest.TestCase):
    def setUp(self):
        self.locutor = LocutorFalso()
        self.sessao = Sessao(EstadoAssistente(), CanalFalso())
        self.acao = FecharPrograma(self.locutor, self.sessao)
        listar = mock.patch("merlin.acoes.janelas.listar_janelas", return_value=JANELAS)
        listar.start()
        self.addCleanup(listar.stop)

    def _intencao(self, alvo):
        return Intencao(TipoIntencao.FECHAR_PROGRAMA, alvo, "x")

    def test_pergunta_e_nao_fecha(self):
        with mock.patch("merlin.acoes.janelas.pedir_fechamento") as pedir:
            self.acao(self._intencao("word"))
        pedir.assert_not_called()
        self.assertEqual(self.locutor.falas, ["Posso fechar WINWORD?"])
        self.assertTrue(self.sessao.tem_pendencia())

    def test_nao_encontrado_nao_cria_pergunta(self):
        self.acao(self._intencao("excel"))
        self.assertFalse(self.sessao.tem_pendencia())
        self.assertIn("Não encontrei", self.locutor.falas[0])

    def test_ambiguo_pergunta_qual_e_nao_cria_pendencia(self):
        self.acao(self._intencao("discord"))
        self.assertFalse(self.sessao.tem_pendencia())
        self.assertIn("Discord, Discord_helper", self.locutor.falas[0])

    def test_confirmar_fecha_e_avisa_resultado(self):
        with mock.patch("merlin.acoes.fechar_programa.time.sleep"), \
                mock.patch("merlin.acoes.janelas.pedir_fechamento", return_value=True) as pedir, \
                mock.patch("merlin.acoes.janelas.ainda_aberta", return_value=False):
            self.acao(self._intencao("word"))
            self.sessao.pegar_pendencia().ao_confirmar()
        pedir.assert_called_once_with(JANELAS[3])
        self.assertEqual(self.locutor.falas[-1], "Pronto, fechei WINWORD.")

    def test_programa_que_recusa_e_avisado(self):
        with mock.patch("merlin.acoes.fechar_programa.time.sleep"), \
                mock.patch("merlin.acoes.janelas.pedir_fechamento", return_value=True), \
                mock.patch("merlin.acoes.janelas.ainda_aberta", return_value=True):
            self.acao(self._intencao("word"))
            self.sessao.pegar_pendencia().ao_confirmar()
        self.assertIn("continua aberto", self.locutor.falas[-1])


class TestAbrirPrograma(unittest.TestCase):
    INSTALADOS = ["google chrome", "pycharm", "calculadora", "bloco de notas", "visual studio code", "spotify"]

    def test_encontrar(self):
        casos = [("chrome", "google chrome"), ("Chrome", "google chrome"), ("calc", "calculadora"),
                 ("vs code", "visual studio code"), ("notepad", "bloco de notas"), ("spotify", "spotify"),
                 ("youtube", None), ("xyzabc", None)]
        for nome, esperado in casos:
            self.assertEqual(encontrar_programa(nome, self.INSTALADOS), esperado, nome)

    def test_abre_e_anuncia_o_nome_real(self):
        locutor = LocutorFalso()
        with mock.patch("merlin.acoes.abrir_programa.give_appnames", return_value=self.INSTALADOS), \
                mock.patch("merlin.acoes.abrir_programa.abrir_app") as abrir:
            AbrirPrograma(locutor, None)(Intencao(TipoIntencao.ABRIR_PROGRAMA, "chrome", "x"))
        abrir.assert_called_once_with("google chrome", output=False)
        self.assertEqual(locutor.falas, ["Abrindo google chrome."])

    def test_nao_instalado_avisa_e_pesquisa(self):
        locutor = LocutorFalso()
        with mock.patch("merlin.acoes.abrir_programa.give_appnames", return_value=self.INSTALADOS), \
                mock.patch("merlin.acoes.abrir_programa.abrir_app") as abrir, \
                mock.patch("merlin.acoes.web.os.startfile") as navegador:
            AbrirPrograma(locutor, PesquisarWeb(locutor))(Intencao(TipoIntencao.ABRIR_PROGRAMA, "youtube", "x"))
        abrir.assert_not_called()
        navegador.assert_called_once_with("https://www.google.com/search?q=youtube")
        self.assertIn("Não encontrei", locutor.falas[0])


class TestWeb(unittest.TestCase):
    def test_urls(self):
        casos = [("gatos", "https://www.google.com/search?q=gatos"),
                 ("youtube.com", "https://youtube.com"),
                 ("https://uol.com.br", "https://uol.com.br"),
                 ("melhores sites .com de gatos", "https://www.google.com/search?q=melhores+sites+.com+de+gatos")]
        for termo, esperado in casos:
            self.assertEqual(montar_url(termo), esperado, termo)


if __name__ == "__main__":
    unittest.main()
