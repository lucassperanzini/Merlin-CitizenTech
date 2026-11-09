import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from merlin.acoes.gerar_script import GerarScript
from merlin.automacao.ambiente import nome_valido
from merlin.automacao.analise_script import ALTERA, AVISO_SUBSTITUI, DINAMICO, EXECUTA, INTERNET, analisar
from merlin.automacao.scripts import ArmazemDeScripts, trocar_pasta
from merlin.habilidades.base import Leitura
from merlin.habilidades.gerar_script import regra
from merlin.interface.painel_automacoes import ApiAutomacoes, ServicoAutomacoes
from merlin.nucleo.sessao import Sessao
from tests.falsos import CanalFalso, ClienteFalso


class AmbienteFalso:
    def __init__(self):
        self.ausentes, self.instalados, self.resposta = set(), [], (True, "")

    def pronto(self):
        return True

    def faltando(self, modulos):
        return [m for m in modulos if m in self.ausentes]

    def instalar(self, *pacotes):
        if self.resposta[0]:
            self.instalados.extend(pacotes)
            self.ausentes.clear()
        return self.resposta


class AnaliseDoCodigo(unittest.TestCase):
    def test_bloqueia_o_que_altera_arquivos_mesmo_com_apelido(self):
        for codigo in ("import shutil\nshutil.move('a', 'b')", "from shutil import move\nmove('a', 'b')",
                       "from shutil import move as m\nm('a', 'b')", "import os as x\nx.remove('a')",
                       "from pathlib import Path\nPath('a').unlink()", "from pathlib import Path\nPath('a').rename('b')",
                       "from pathlib import Path\nPath('a').replace('b')", "from os import *\nremove('a')"):
            with self.subTest(codigo):
                self.assertIn(ALTERA, analisar(codigo).bloqueios)

    def test_bloqueia_programas_internet_e_codigo_montado(self):
        self.assertIn(EXECUTA, analisar("import subprocess").bloqueios)
        self.assertIn(EXECUTA, analisar("import os\nos.system('dir')").bloqueios)
        self.assertIn(INTERNET, analisar("from urllib.request import urlopen").bloqueios)
        self.assertIn(DINAMICO, analisar("eval('1')").bloqueios)
        self.assertIn(DINAMICO, analisar("import os\ngetattr(os, 'remove')('a')").bloqueios)

    def test_nao_confunde_com_usos_inofensivos(self):
        codigo = "import pandas as pd\nprint('a'.replace('a', 'b'))\ndf = pd.DataFrame()\ndf.rename(columns={'a': 'b'})"
        self.assertEqual(analisar(codigo).bloqueios, ())

    def test_avisa_quando_pode_substituir(self):
        for codigo in ("open('a', 'w')", "open('a', mode='a')", "import pandas as pd\npd.DataFrame().to_excel('a')",
                       "import shutil\nshutil.copy('a', 'b')", "from zipfile import ZipFile\nZipFile('a', 'w')"):
            with self.subTest(codigo):
                self.assertIn(AVISO_SUBSTITUI, analisar(codigo).avisos)

    def test_leitura_e_criacao_exclusiva_nao_avisam(self):
        self.assertEqual(analisar("open('a')\nopen('b', 'r')\nopen('c', 'x')").avisos, ())

    def test_lista_bibliotecas_externas(self):
        self.assertEqual(analisar("import nao_existe_xyz\nimport os").externos, ("nao_existe_xyz",))

    def test_excel_precisa_de_openpyxl_mesmo_sem_importar(self):
        self.assertEqual(analisar("import pandas as pd\npd.DataFrame().to_excel('a')").externos, ("openpyxl", "pandas"))

    def test_sintaxe_invalida(self):
        self.assertFalse(analisar("def (").valido)


class TrocarPasta(unittest.TestCase):
    def test_troca_e_o_resultado_continua_valido(self):
        novo = trocar_pasta('import os\nPASTA = r"C:\\Inventada"\nprint(PASTA)\n', r"D:\Minhas Fotos\água")
        escopo = {}
        linha = next(l for l in novo.split("\n") if l.startswith("PASTA"))
        exec(linha, escopo)  # só a linha da constante, escrita por este teste
        self.assertEqual(escopo["PASTA"], r"D:\Minhas Fotos\água")
        self.assertIn("print(PASTA)", novo)

    def test_pasta_terminando_em_barra(self):
        self.assertTrue(analisar(trocar_pasta('PASTA = "x"\n', "D:\\")).valido)

    def test_valor_em_varias_linhas(self):
        self.assertEqual(trocar_pasta('PASTA = (\n  "x"\n)\nprint(1)\n', "D:\\a"), "PASTA = 'D:\\\\a'\nprint(1)\n")

    def test_recusa_o_que_nao_da_para_trocar(self):
        for codigo in ('print(1)', 'PASTA = "a"\nPASTA = "b"', 'def f():\n    PASTA = "a"', 'PASTA = "a"; print(1)', "def ("):
            with self.subTest(codigo):
                self.assertIsNone(trocar_pasta(codigo, "D:\\a"))


class Acao(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name) / "scripts"
        self.cliente, self.canal, self.copiado = ClienteFalso(), CanalFalso(), []
        self.sessao = Sessao(MagicMock(), self.canal)
        self.armazem = ArmazemDeScripts(self.pasta)
        self.acao = GerarScript(self.cliente, self.sessao, self.canal, self.armazem)

    def pedir(self, codigo, explicacao="Mostra os arquivos."):
        self.cliente.resposta = f"```python\n{codigo}\n```\n{explicacao}"
        return self.acao(SimpleNamespace(comando="cria um script que lista arquivos"))

    def test_mostra_sem_executar(self):
        marca = self.pasta.parent / "executou.txt"
        resultado = self.pedir(f"open(r'{marca}', 'x')")
        resultado.depois()
        self.assertFalse(marca.exists())
        self.assertEqual(self.canal.scripts, ["Mostra os arquivos."])
        self.assertTrue(self.sessao.tem_pendencia())
        guardado = self.armazem.listar()[0]
        self.assertEqual(guardado["explicacao"], "Mostra os arquivos.")
        self.assertIn("ainda não foi testado", guardado["avisos"][0])

    def test_recusa_script_que_altera_e_nao_guarda(self):
        resultado = self.pedir("from shutil import move\nmove('a', 'b')")
        self.assertIn("Não vou criar", resultado.fala)
        self.assertFalse(self.sessao.tem_pendencia())
        self.assertEqual(self.armazem.listar(), [])

    def test_ver_abre_a_aba(self):
        self.pedir("print(1)")
        self.sessao.pegar_pendencia().ao_confirmar()
        self.assertEqual(self.canal.eventos[-1], "abrir_script: cria_um_script_que_lista_arquivos")

    def test_descartar_apaga(self):
        self.pedir("print(1)")
        self.sessao.pegar_pendencia().ao_recusar()
        self.assertEqual(self.armazem.listar(), [])
        self.assertEqual(list(self.pasta.iterdir()), [])

    def test_sem_codigo_valido(self):
        self.cliente.resposta = "não sei"
        self.assertIn("válido", self.acao(SimpleNamespace(comando="x")).fala)
        self.cliente.resposta = "```python\ndef (\n```"
        self.assertIn("válido", self.acao(SimpleNamespace(comando="x")).fala)

    def test_ia_fora_do_ar(self):
        self.cliente.resposta = ConnectionError("x")
        self.assertIn("IA", self.acao(SimpleNamespace(comando="x")).fala)

    def test_guardar_nunca_substitui(self):
        for _ in range(2):
            self.pedir("print(1)")
        arquivos = sorted(p.name for p in self.pasta.glob("*.py"))
        self.assertEqual(arquivos, ["cria_um_script_que_lista_arquivos.py", "cria_um_script_que_lista_arquivos_2.py"])


class Painel(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.raiz = Path(temporaria.name).resolve()
        self.armazem = ArmazemDeScripts(self.raiz / "s")
        self.copiado = []
        modulo_python = patch("merlin.automacao.scripts.PYTHON_DOS_SCRIPTS", Path(sys.executable))
        modulo_python.start()
        self.addCleanup(modulo_python.stop)
        self.ambiente = AmbienteFalso()
        self.paginas = []
        self.servico = ServicoAutomacoes(self.raiz / "s", self.copiado.append, self.ambiente, self.paginas.append)
        self.id = self.armazem.guardar("lista arquivos", 'PASTA = r"C:\\Exemplo"\nprint(PASTA)\n', "Lista.", ["Aviso"])

    def test_escolher_pasta_troca_no_arquivo_e_mostra(self):
        estado = self.servico.definir_pasta_script(self.id, str(self.raiz))
        self.assertEqual(estado["scripts"][0]["pasta"], str(self.raiz))
        self.assertIn(repr(str(self.raiz)), self.armazem.codigo(self.id))
        self.assertNotIn("Exemplo", self.armazem.codigo(self.id))

    def test_pasta_inexistente(self):
        self.assertIn("erro", self.servico.definir_pasta_script(self.id, str(self.raiz / "nao")))
        self.assertIn("Exemplo", self.armazem.codigo(self.id))

    def test_script_sem_constante(self):
        outro = self.armazem.guardar("x", "print(1)\n", "", [])
        descrito = next(s for s in self.servico.estado()["scripts"] if s["id"] == outro)
        self.assertFalse(descrito["aceita_pasta"])
        self.assertIn("Não consegui", self.servico.definir_pasta_script(outro, str(self.raiz))["erro"])

    def test_id_nao_sai_da_pasta(self):
        (self.raiz / "fora.py").write_text("x", encoding="utf-8")
        for ruim in ("../fora", "..\\fora", "", None):
            with self.subTest(ruim):
                self.assertIn("erro", self.servico.apagar_script(ruim))
        self.assertTrue((self.raiz / "fora.py").exists())

    def test_copia_e_apaga(self):
        self.assertEqual(self.servico.copiar_script(self.id), {})
        self.assertIn("print(PASTA)", self.copiado[0])
        self.assertEqual(self.servico.apagar_script(self.id)["scripts"], [])

    def test_script_antigo_sem_dados_aparece(self):
        (self.raiz / "s" / "antigo.py").write_text("print(1)\n", encoding="utf-8")
        self.assertIn("antigo", [s["id"] for s in self.servico.estado()["scripts"]])

    def falta(self, codigo):
        self.ambiente.ausentes = {"docx", "abc_tools"}
        return self.armazem.guardar("lib", codigo, "", [])

    def faltando(self, id_script):
        return next(s for s in self.servico.estado()["scripts"] if s["id"] == id_script)["faltando"]

    def test_mostra_o_nome_certo_para_instalar(self):
        outro = self.falta("import docx\nimport abc_tools\n")
        por_modulo = {f["modulo"]: f for f in self.faltando(outro)}
        self.assertEqual(por_modulo["docx"], {"modulo": "docx", "pacote": "python-docx", "conhecida": True})
        self.assertFalse(por_modulo["abc_tools"]["conhecida"])

    def test_instala_e_some_da_lista(self):
        outro = self.falta("import docx\n")
        self.assertEqual(self.servico.instalar_biblioteca(outro, "docx")["scripts"][0]["faltando"], [])
        self.assertEqual(self.ambiente.instalados, ["python-docx"])

    def test_so_instala_o_que_o_script_precisa(self):
        outro = self.falta("import docx\n")
        for modulo in ("abc_tools", "--index-url", "os", ""):
            with self.subTest(modulo):
                self.assertIn("erro", self.servico.instalar_biblioteca(outro, modulo))
        self.assertEqual(self.ambiente.instalados, [])

    def test_mostra_o_erro_da_instalacao(self):
        outro = self.falta("import docx\n")
        self.ambiente.resposta = (False, "sem internet")
        self.assertIn("sem internet", self.servico.instalar_biblioteca(outro, "docx")["erro"])

    def test_abre_a_pagina_oficial(self):
        outro = self.falta("import abc_tools\n")
        self.assertEqual(self.servico.abrir_pagina_pacote(outro, "abc_tools"), {})
        self.assertEqual(self.paginas, ["https://pypi.org/project/abc_tools/"])

    def test_aviso_antigo_de_biblioteca_nao_aparece_mais(self):
        outro = self.armazem.guardar("velho", "print(1)\n", "", ["Fica", "Precisa instalar antes: x."])
        self.assertEqual(next(s for s in self.armazem.listar() if s["id"] == outro)["avisos"], ["Fica"])

    def test_nomes_de_pacote(self):
        self.assertTrue(nome_valido("python-docx"))
        for ruim in ("", "--index-url", "a b", "a;b", None):
            with self.subTest(ruim):
                self.assertFalse(nome_valido(ruim))

    def com_pasta(self):
        self.servico.definir_pasta_script(self.id, str(self.raiz))

    def test_colar_codigo_mantem_a_pasta(self):
        self.com_pasta()
        estado = self.servico.salvar_codigo_script(self.id, 'PASTA = r"C:\\Outra"\nprint("novo")\n')
        self.assertIn(repr(str(self.raiz)), estado["scripts"][0]["codigo"])
        self.assertEqual(estado["scripts"][0]["pasta"], str(self.raiz))

    def test_codigo_colado_sem_pasta_limpa_a_escolha(self):
        self.com_pasta()
        self.assertEqual(self.servico.salvar_codigo_script(self.id, "print(1)\n")["scripts"][0]["pasta"], "")

    def test_codigo_colado_passa_pela_checagem(self):
        original = self.armazem.codigo(self.id)
        for ruim in ("import os\nos.remove('a')\n", "def (", "   "):
            with self.subTest(ruim):
                self.assertIn("erro", self.servico.salvar_codigo_script(self.id, ruim))
                self.assertEqual(self.armazem.codigo(self.id), original)

    def test_executar_exige_pasta(self):
        self.assertIn("Escolha a pasta", self.servico.executar_script(self.id)["erro"])

    def test_executa_e_grava_na_pasta_escolhida(self):
        self.servico.salvar_codigo_script(self.id, 'PASTA = "x"\nopen("saida.txt", "x").close()\nprint("olá", PASTA)\n')
        self.com_pasta()
        r = self.servico.executar_script(self.id)
        self.assertTrue(r["ok"], r)
        self.assertIn("olá", r["saida"])
        self.assertIn(str(self.raiz), r["saida"])
        self.assertTrue((self.raiz / "saida.txt").exists())

    def test_mostra_o_erro(self):
        outro = self.armazem.guardar("y", "print(1/0)\n", "", [])
        r = self.servico.executar_script(outro)
        self.assertFalse(r["ok"])
        self.assertIn("ZeroDivisionError", r["erros"])

    def test_nao_executa_arquivo_mudado_a_mao(self):
        outro = self.armazem.guardar("z", "print(1)\n", "", [])
        (self.raiz / "s" / f"{outro}.py").write_text("import shutil\nshutil.rmtree('a')\n", encoding="utf-8")
        self.assertIn("Recusado", self.servico.executar_script(outro)["erro"])

    def test_tempo_limite(self):
        armazem = ArmazemDeScripts(self.raiz / "s", tempo_limite=1)
        outro = armazem.guardar("w", "import time\nprint('a', flush=True)\ntime.sleep(30)\n", "", [])
        r = armazem.executar(outro)
        self.assertTrue(r["tempo_esgotado"])
        self.assertFalse(r["ok"])

    def test_pedido_de_abrir_vale_uma_vez(self):
        api = ApiAutomacoes(self.servico)
        api._pedir_script("abc")
        self.assertEqual(api.script_pedido(), "abc")
        self.assertEqual(api.script_pedido(), "")


class Regra(unittest.TestCase):
    def ler(self, comando):
        return regra(Leitura("gerar_script", "", {}, comando))

    def test_precisa_pedir_script(self):
        self.assertIsNone(self.ler("cria um script que lista arquivos"))
        self.assertIsNone(self.ler("faz um programa que soma"))
        self.assertEqual(self.ler("lista meus arquivos").intencao, "conversar")


if __name__ == "__main__":
    unittest.main()
