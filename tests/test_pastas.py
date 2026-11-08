import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from merlin.acoes import pastas
from merlin.acoes.pastas import AbrirPasta, pasta_do_windows, procurar_pasta, unidade_de_disco
from merlin.habilidades import HABILIDADES
from merlin.habilidades.base import Leitura
from merlin.ia.intencoes import Intencao, TipoIntencao


def sem_acesso_rapido(teste, fixadas=()):
    """Os testes não leem o Acesso Rápido de verdade: usam o que for passado aqui."""
    lista = list(fixadas)
    p = mock.patch.object(pastas, "pastas_do_acesso_rapido", lambda: lista)
    p.start()
    teste.addCleanup(p.stop)
    pastas.definir_apelidos(lambda: [])
    teste.addCleanup(pastas.definir_apelidos, lambda: [])


def pedido(alvo):
    return Intencao(TipoIntencao("abrir_pasta"), alvo, f"abre a pasta {alvo}")


class TestPastasDoWindows(unittest.TestCase):
    def test_reconhece_o_jeito_de_falar(self):
        for falado, esperado in (("downloads", "Downloads"), ("meus documentos", "Documentos"),
                                 ("área de trabalho", "Área de trabalho"), ("minhas fotos", "Imagens"),
                                 ("pasta de músicas", "Músicas"), ("vídeos", "Vídeos")):
            achado = pasta_do_windows(falado)
            self.assertIsNotNone(achado, falado)
            self.assertEqual(achado[1], esperado)
        self.assertIsNone(pasta_do_windows("fotos da viagem"))  # nome qualquer: vai para a busca

    def test_unidade_de_disco(self):
        self.assertEqual(unidade_de_disco("disco c"), Path("C:\\"))
        self.assertEqual(unidade_de_disco("C:"), Path("C:\\"))
        self.assertIsNone(unidade_de_disco("disco do trabalho"))


class TestBusca(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        for caminho in ("Projetos/Merlin", "Antigos/Coisas/Merlin", ".escondida/Merlin", "node_modules/Merlin",
                        "Fotos da Viagem", "a/b/c/d/Funda"):
            (self.raiz / caminho).mkdir(parents=True)

    def test_acha_pelo_nome_sem_acento_nem_maiuscula_e_a_mais_rasa_primeiro(self):
        achadas = procurar_pasta("merlin", [self.raiz])
        self.assertEqual(achadas[0], self.raiz / "Projetos" / "Merlin")
        self.assertEqual(len(achadas), 2)  # a escondida e a de node_modules ficam de fora
        self.assertEqual(procurar_pasta("fotos da viagem", [self.raiz]), [self.raiz / "Fotos da Viagem"])

    def test_nao_passa_da_profundidade(self):
        self.assertEqual(procurar_pasta("funda", [self.raiz]), [])

    def test_para_no_tempo_maximo(self):
        inicio = time.monotonic()
        procurar_pasta("nada", [self.raiz], tempo_maximo=0)
        self.assertLess(time.monotonic() - inicio, 0.5)


class TestAcao(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        (self.raiz / "Notas Fiscais").mkdir()
        sem_acesso_rapido(self)
        self.abertas = []
        self.acao = AbrirPasta(abrir=self.abertas.append, raizes=lambda: [self.raiz])

    def test_abre_a_pasta_achada_pelo_nome(self):
        r = self.acao(pedido("notas fiscais"))
        self.assertEqual(self.abertas, [str(self.raiz / "Notas Fiscais")])
        self.assertEqual(r.fala, "abri a pasta Notas Fiscais")

    def test_pasta_do_windows_nao_precisa_de_busca(self):
        r = self.acao(pedido("downloads"))
        self.assertEqual(r.fala, "abri a pasta Downloads")
        self.assertTrue(os.path.isdir(self.abertas[0]))

    def test_nao_encontrada_avisa_e_nao_abre_nada(self):
        r = self.acao(pedido("pasta que não existe"))
        self.assertEqual(self.abertas, [])
        self.assertIn("não encontrei", r.fala)


class TestRegras(unittest.TestCase):
    def setUp(self):
        sem_acesso_rapido(self)

    def _regra(self, nome):
        return next(h for h in HABILIDADES if h.nome == nome).regra

    def test_pergunta_vira_conversa(self):
        correcao = self._regra("abrir_pasta")(Leitura("abrir_pasta", "downloads", {}, "onde fica a pasta downloads?"))
        self.assertEqual(correcao.intencao, "conversar")

    def test_criar_apagar_ou_mover_pasta_vira_conversa(self):
        for frase in ("cria uma pasta chamada fotos", "apaga a pasta temporarios", "renomeia a pasta x",
                      "move a pasta downloads"):
            correcao = self._regra("abrir_pasta")(Leitura("abrir_pasta", "x", {}, frase))
            self.assertEqual(correcao.intencao, "conversar", frase)
        self.assertIsNone(self._regra("abrir_pasta")(Leitura("abrir_pasta", "downloads", {}, "abre a pasta downloads")))
        self.assertIsNone(self._regra("abrir_pasta")(Leitura("abrir_pasta", "movies", {}, "abre a pasta movies")))

    def test_abrir_programa_com_a_palavra_pasta_vira_abrir_pasta(self):
        correcao = self._regra("abrir_programa")(Leitura("abrir_programa", "pasta downloads", {}, "abre a pasta downloads"))
        self.assertEqual((correcao.intencao, correcao.alvo), ("abrir_pasta", "downloads"))
        self.assertIsNone(self._regra("abrir_programa")(Leitura("abrir_programa", "chrome", {}, "abre o chrome")))


class TestAtalhos(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        (self.raiz / "Clientes").mkdir()
        (self.raiz / "Projeto X").mkdir()
        (self.raiz / "Spotify").mkdir()
        sem_acesso_rapido(self, [("Projeto X", self.raiz / "Projeto X", True),
                                 ("Spotify", self.raiz / "Spotify", False)])
        pastas.definir_apelidos(lambda: [{"apelido": "trabalho", "caminho": str(self.raiz / "Clientes")}])
        self.abertas = []
        self.acao = AbrirPasta(abrir=self.abertas.append, raizes=lambda: [])

    def test_apelido_vale_com_ou_sem_a_palavra_pasta(self):
        for falado in ("trabalho", "pasta do trabalho", "Trabalho"):
            self.assertEqual(pastas.atalho(falado)[0], self.raiz / "Clientes", falado)
        r = self.acao(pedido("pasta do trabalho"))
        self.assertEqual(self.abertas, [str(self.raiz / "Clientes")])
        self.assertEqual(r.fala, "abri a pasta trabalho")
        self.assertIn("apelido", r.registro)

    def test_pasta_do_acesso_rapido_abre_pelo_nome(self):
        r = self.acao(pedido("projeto x"))
        self.assertEqual(self.abertas, [str(self.raiz / "Projeto X")])
        self.assertIn("Acesso Rápido", r.registro)

    def test_abrir_programa_vira_pasta_so_com_apelido_ou_fixada(self):
        regra = next(h for h in HABILIDADES if h.nome == "abrir_programa").regra
        self.assertEqual(regra(Leitura("abrir_programa", "trabalho", {}, "abre o trabalho")).intencao, "abrir_pasta")
        self.assertEqual(regra(Leitura("abrir_programa", "projeto x", {}, "abre o projeto x")).intencao, "abrir_pasta")
        # Uma pasta só frequente com nome de programa não rouba o programa
        self.assertIsNone(regra(Leitura("abrir_programa", "spotify", {}, "abre o spotify")))


class TestAbaPastas(unittest.TestCase):
    def setUp(self):
        from merlin.interface.configuracoes import ServicoConfiguracoes
        from merlin.preferencias import Preferencias
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        sem_acesso_rapido(self)
        self.preferencias = Preferencias(self.raiz / "config.json")
        self.servico = ServicoConfiguracoes(self.preferencias, None, None, None, None)

    def test_salva_e_le_de_volta(self):
        r = self.servico.pastas_salvar([{"apelido": " trabalho ", "caminho": str(self.raiz)}, {"apelido": "", "caminho": ""}])
        self.assertEqual(r["apelidos"], [{"apelido": "trabalho", "caminho": str(self.raiz), "existe": True}])
        self.assertEqual(self.preferencias.apelidos_pastas, [{"apelido": "trabalho", "caminho": str(self.raiz)}])

    def test_recusa_sem_apelido_pasta_inexistente_ou_repetido(self):
        self.assertIn("erro", self.servico.pastas_salvar([{"apelido": "", "caminho": str(self.raiz)}]))
        self.assertIn("erro", self.servico.pastas_salvar([{"apelido": "x", "caminho": str(self.raiz / "nao_existe")}]))
        self.assertIn("erro", self.servico.pastas_salvar([{"apelido": "x", "caminho": str(self.raiz)},
                                                          {"apelido": "X", "caminho": str(self.raiz)}]))
        self.assertEqual(self.preferencias.apelidos_pastas, [])  # nada foi salvo


if __name__ == "__main__":
    unittest.main()
