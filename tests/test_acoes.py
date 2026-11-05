import unittest
from unittest import mock

from merlin.acoes.abrir_programa import AbrirPrograma, encontrar_programa
from merlin.acoes.fechar_programa import FecharPrograma, descrever_alvo
from merlin.acoes.janelas import JanelaAberta, escolher_janelas
from merlin.acoes.web import PesquisarWeb, montar_url
from merlin.ia.intencoes import Intencao, TipoIntencao


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
        self.assertEqual(descrever_alvo([JANELAS[3]], False), "o WINWORD")


class TestFecharPrograma(unittest.TestCase):
    def setUp(self):
        self.acao = FecharPrograma()
        listar = mock.patch("merlin.acoes.janelas.listar_janelas", return_value=JANELAS)
        listar.start()
        self.addCleanup(listar.stop)

    def _intencao(self, alvo):
        return Intencao(TipoIntencao.FECHAR_PROGRAMA, alvo, "x")

    def test_nao_encontrado_nao_fecha_nada(self):
        with mock.patch("merlin.acoes.janelas.pedir_fechamento") as pedir:
            r = self.acao(self._intencao("excel"))
        pedir.assert_not_called()
        self.assertIn("não encontrei", r.fala)

    def test_ambiguo_pergunta_qual_e_nao_fecha_nada(self):
        with mock.patch("merlin.acoes.janelas.pedir_fechamento") as pedir:
            r = self.acao(self._intencao("discord"))
        pedir.assert_not_called()
        self.assertIn("Discord, Discord_helper", r.fala)
        self.assertTrue(r.frase_completa)

    def test_fecha_direto_sem_perguntar(self):
        with mock.patch("merlin.acoes.janelas.pedir_fechamento", return_value=True) as pedir, \
                mock.patch("merlin.acoes.janelas.ainda_aberta", return_value=False):
            r = self.acao(self._intencao("word"))
        pedir.assert_called_once_with(JANELAS[3])
        self.assertEqual(r.fala, "fechei o WINWORD")

    def test_programa_que_recusa_e_avisado(self):
        with mock.patch("merlin.acoes.fechar_programa.time.sleep"), \
                mock.patch("merlin.acoes.fechar_programa.TEMPO_MAXIMO_PARA_FECHAR", 0), \
                mock.patch("merlin.acoes.janelas.pedir_fechamento", return_value=True), \
                mock.patch("merlin.acoes.janelas.ainda_aberta", return_value=True):
            r = self.acao(self._intencao("word"))
        self.assertIn("continua aberto", r.fala)

    def test_nao_espera_o_tempo_todo_se_ja_fechou(self):
        with mock.patch("merlin.acoes.fechar_programa.time.sleep") as espera, \
                mock.patch("merlin.acoes.janelas.pedir_fechamento", return_value=True), \
                mock.patch("merlin.acoes.janelas.ainda_aberta", return_value=False):
            self.acao(self._intencao("word"))
        espera.assert_not_called()


class TestAbrirPrograma(unittest.TestCase):
    INSTALADOS = ["google chrome", "pycharm", "calculadora", "bloco de notas", "visual studio code", "spotify"]

    def test_encontrar(self):
        casos = [("chrome", "google chrome"), ("Chrome", "google chrome"), ("calc", "calculadora"),
                 ("vs code", "visual studio code"), ("notepad", "bloco de notas"), ("spotify", "spotify"),
                 ("youtube", None), ("xyzabc", None)]
        for nome, esperado in casos:
            self.assertEqual(encontrar_programa(nome, self.INSTALADOS), esperado, nome)

    def _abrir(self, alvo, pesquisa=None):
        with mock.patch("merlin.acoes.abrir_programa.give_appnames", return_value=self.INSTALADOS), \
                mock.patch("merlin.acoes.abrir_programa.abrir_app") as abrir:
            return AbrirPrograma(pesquisa)(Intencao(TipoIntencao.ABRIR_PROGRAMA, alvo, "x")), abrir

    def test_abre_e_informa_o_nome_real(self):
        r, abrir = self._abrir("chrome")
        abrir.assert_called_once_with("google chrome", output=False)
        self.assertEqual(r.fala, "abri o google chrome")

    def test_artigo_feminino(self):
        self.assertEqual(self._abrir("calculadora")[0].fala, "abri a calculadora")

    def test_nao_instalado_avisa_e_pesquisa(self):
        with mock.patch("merlin.acoes.web.os.startfile") as navegador:
            r, abrir = self._abrir("youtube", PesquisarWeb())
        abrir.assert_not_called()
        navegador.assert_called_once_with("https://www.google.com/search?q=youtube")
        self.assertIn("não encontrei", r.fala)


class TestWeb(unittest.TestCase):
    def test_fala_no_passado(self):
        with mock.patch("merlin.acoes.web.os.startfile"):
            self.assertEqual(PesquisarWeb()(Intencao(TipoIntencao.PESQUISAR_WEB, "gatos", "x")).fala, "pesquisei por gatos")
            self.assertEqual(PesquisarWeb()(Intencao(TipoIntencao.PESQUISAR_WEB, "github.com", "x")).fala, "abri o site github.com")

    def test_urls(self):
        casos = [("gatos", "https://www.google.com/search?q=gatos"),
                 ("youtube.com", "https://youtube.com"),
                 ("https://uol.com.br", "https://uol.com.br"),
                 ("melhores sites .com de gatos", "https://www.google.com/search?q=melhores+sites+.com+de+gatos")]
        for termo, esperado in casos:
            self.assertEqual(montar_url(termo), esperado, termo)


if __name__ == "__main__":
    unittest.main()
