import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from merlin.acoes.rodar_script import RodarScript
from merlin.automacao.scripts import ArmazemDeScripts, ScriptInvalido
from merlin.habilidades.base import Leitura
from merlin.habilidades.rodar_script import regra
from merlin.nucleo.sessao import Sessao
from tests.falsos import CanalFalso

CODIGO = 'PASTA = r"C:\\Exemplo"\nprint("oi", PASTA)\n'


class Base(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        python = patch("merlin.automacao.scripts.PYTHON_DOS_SCRIPTS", Path(sys.executable))
        python.start()
        self.addCleanup(python.stop)
        self.raiz = Path(temporaria.name).resolve()
        self.teste = self.raiz / "teste"
        self.real = self.raiz / "real"
        self.teste.mkdir(), self.real.mkdir()
        self.armazem = ArmazemDeScripts(self.raiz / "s")
        self.id = self.armazem.guardar("maior", CODIGO, "", [])

    def testar_e_aprovar(self, nome="maior arquivo"):
        self.armazem.definir_pasta(self.id, str(self.teste))
        self.assertTrue(self.armazem.executar(self.id)["ok"])
        self.armazem.aprovar(self.id, nome)

    def aprovado(self):
        return self.armazem.listar()[0]["aprovado"]


class Aprovacao(Base):
    def test_precisa_ter_rodado_sem_erro(self):
        with self.assertRaisesRegex(ScriptInvalido, "Execute"):
            self.armazem.aprovar(self.id, "maior arquivo")

    def test_codigo_novo_precisa_de_novo_teste(self):
        self.testar_e_aprovar()
        self.armazem.salvar_codigo(self.id, 'PASTA = "x"\nprint("mudou")\n')
        self.assertEqual(self.aprovado(), "")
        with self.assertRaisesRegex(ScriptInvalido, "Execute"):
            self.armazem.aprovar(self.id, "maior arquivo")

    def test_mudar_o_arquivo_a_mao_derruba(self):
        self.testar_e_aprovar()
        arquivo = self.raiz / "s" / f"{self.id}.py"
        arquivo.write_text(arquivo.read_text(encoding="utf-8") + "print(2)\n", encoding="utf-8")
        self.assertEqual(self.aprovado(), "")
        with self.assertRaisesRegex(ScriptInvalido, "aprovado de novo"):
            self.armazem.executar_aprovado(self.id, str(self.teste))

    def test_trocar_a_pasta_mantem_a_aprovacao(self):
        self.testar_e_aprovar()
        self.armazem.definir_pasta(self.id, str(self.real))
        self.assertEqual(self.aprovado(), "maior arquivo")

    def test_pasta_trocada_depois_da_confirmacao(self):
        self.testar_e_aprovar()
        self.armazem.definir_pasta(self.id, str(self.real))
        with self.assertRaisesRegex(ScriptInvalido, "pasta mudou"):
            self.armazem.executar_aprovado(self.id, str(self.teste))

    def test_nomes(self):
        self.armazem.definir_pasta(self.id, str(self.teste))
        self.armazem.executar(self.id)
        for ruim in ("", "a", "o script", "x" * 41):
            with self.subTest(ruim), self.assertRaises(ScriptInvalido):
                self.armazem.aprovar(self.id, ruim)

    def test_nome_repetido(self):
        self.testar_e_aprovar("Maior Arquivo")
        outro = self.armazem.guardar("outro", "print(1)\n", "", [])
        self.armazem.executar(outro)
        with self.assertRaisesRegex(ScriptInvalido, "Já existe"):
            self.armazem.aprovar(outro, "maior arquivo")

    def test_remover(self):
        self.testar_e_aprovar()
        self.armazem.desaprovar(self.id)
        self.assertEqual(self.aprovado(), "")

    def test_encontra_pelo_nome_falado(self):
        self.testar_e_aprovar("maior arquivo")
        for alvo, comando in (("Maior Arquivo", "x"), ("o script maior arquivo", "x"), ("", "roda o maior arquivo aí")):
            with self.subTest(alvo):
                self.assertEqual(self.armazem.encontrar_aprovado(alvo, comando)["id"], self.id)
        self.assertIsNone(self.armazem.encontrar_aprovado("outro", "roda outro"))


class Voz(Base):
    def setUp(self):
        super().setUp()
        self.canal = CanalFalso()
        self.sessao = Sessao(MagicMock(), self.canal)
        self.acao = RodarScript(self.armazem, self.sessao, self.canal, em_segundo_plano=lambda f: f())

    def pedir(self):
        return self.acao(SimpleNamespace(alvo="maior arquivo", comando="roda o maior arquivo"))

    def test_sem_aprovacao_nao_oferece(self):
        self.assertIn("não tenho", self.pedir().fala)
        self.assertFalse(self.sessao.tem_pendencia())

    def test_nada_roda_antes_de_confirmar(self):
        self.testar_e_aprovar()
        self.armazem.salvar_codigo(self.id, CODIGO.replace('print("oi", PASTA)', 'open("rodou.txt", "x").close()'))
        self.armazem.executar(self.id), self.armazem.aprovar(self.id, "maior arquivo")
        (self.teste / "rodou.txt").unlink()
        self.pedir().depois()
        self.assertFalse((self.teste / "rodou.txt").exists())
        self.assertIn(str(self.teste), self.canal.eventos[-1])
        self.sessao.pegar_pendencia().ao_confirmar()
        self.assertTrue((self.teste / "rodou.txt").exists())

    def test_mostra_o_resultado(self):
        self.testar_e_aprovar()
        self.pedir()
        self.sessao.pegar_pendencia().ao_confirmar()
        self.assertIn("Terminou sem erro", self.canal.eventos[-1])
        self.assertIn("oi", self.canal.eventos[-1])

    def test_codigo_mudou_durante_a_espera(self):
        self.testar_e_aprovar()
        self.pedir()
        arquivo = self.raiz / "s" / f"{self.id}.py"
        arquivo.write_text(arquivo.read_text(encoding="utf-8") + "print(2)\n", encoding="utf-8")
        self.sessao.pegar_pendencia().ao_confirmar()
        self.assertIn("aprovado de novo", self.canal.eventos[-1])

    def test_um_por_vez(self):
        self.testar_e_aprovar()
        pendentes = []
        acao = RodarScript(self.armazem, self.sessao, self.canal, em_segundo_plano=pendentes.append)
        self.assertIn("rodando", acao._iniciar(self.id, str(self.teste)).fala)
        self.assertIn("já tem", acao._iniciar(self.id, str(self.teste)).fala)
        pendentes[0]()
        self.assertIn("rodando.", acao._iniciar(self.id, str(self.teste)).fala)
        pendentes[1]()


class Regra(unittest.TestCase):
    def test_precisa_mandar_rodar(self):
        ler = lambda c: regra(Leitura("rodar_script", "", {}, c))  # noqa: E731
        self.assertIsNone(ler("roda o maior arquivo"))
        self.assertIsNone(ler("executa o maior arquivo"))
        self.assertEqual(ler("mostra o maior arquivo").intencao, "conversar")


if __name__ == "__main__":
    unittest.main()
