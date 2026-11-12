import html
import json
import tempfile
import unittest
from pathlib import Path

from merlin.interface import moldura
from merlin.interface.central import montar_pagina
from merlin.interface.configuracoes import ServicoConfiguracoes
from merlin.interface.painel_habilidades import ApiPainelHabilidades
from merlin.interface.perfil import AVISO_SO_ADMINISTRADOR, so_administrador
from merlin.nucleo.memoria_conversa import MemoriaConversa
from merlin.preferencias import Preferencias
from tests.falsos import LocutorFalso


class ServicoQueNaoPodeSerChamado:
    def __getattr__(self, nome):
        raise AssertionError(f"o operador chegou ao serviço: {nome}")


class Base(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.arquivo = Path(pasta.name) / "merlin_config.json"

    def preferencias(self, **dados):
        if dados:
            self.arquivo.write_text(json.dumps(dados), encoding="utf-8")
        return Preferencias(self.arquivo)


class TestPerfil(Base):
    def test_sem_o_campo_a_maquina_e_de_operador(self):
        self.assertFalse(self.preferencias().administrador)  # nem o arquivo existe
        for valor in ("operador", "Administrador", "admin", True, ""):
            with self.subTest(valor):
                self.assertFalse(self.preferencias(perfil=valor).administrador)
        self.assertTrue(self.preferencias(perfil="administrador").administrador)

    def test_salvar_outra_preferencia_mantem_o_perfil(self):
        p = self.preferencias(perfil="administrador")
        p.modelo_ia = "llama3.2:latest"
        self.assertEqual(json.loads(self.arquivo.read_text(encoding="utf-8"))["perfil"], "administrador")

    def test_modo_debug_so_para_o_administrador(self):
        operador = self.preferencias(perfil="operador", modo_debug=True)
        self.assertFalse(operador.modo_debug)  # ligado no arquivo, mas não vale
        operador.modo_debug = True
        self.assertFalse(operador.modo_debug)
        admin = self.preferencias(perfil="administrador")
        admin.modo_debug = True
        self.assertTrue(admin.modo_debug)

    def test_operador_nao_troca_o_modelo(self):
        p = self.preferencias(perfil="operador", modelo_ia="qwen3:8b")
        servico = ServicoConfiguracoes(p, LocutorFalso(), None, MemoriaConversa(), None)
        self.assertEqual(servico.trocar_modelo("llama3.2:latest"), AVISO_SO_ADMINISTRADOR)
        self.assertEqual(p.modelo_ia, "qwen3:8b")


class TestBloqueio(unittest.TestCase):
    def test_operador_recebe_as_mesmas_funcoes_todas_recusando(self):
        api = so_administrador(ApiPainelHabilidades(ServicoQueNaoPodeSerChamado()), administrador=False)
        for nome in ("listar", "testar", "salvar", "restaurar", "ligar"):
            with self.subTest(nome):
                self.assertTrue(callable(getattr(api, nome)))  # a página continua achando a função
        with self.assertLogs("merlin.interface.perfil", "WARNING"):
            self.assertEqual(api.ligar("abrir_programa", False), {"erro": AVISO_SO_ADMINISTRADOR})
        self.assertFalse(hasattr(api, "_servico"))  # e não há caminho até o serviço

    def test_administrador_recebe_a_propria_api(self):
        api = ApiPainelHabilidades(object())
        self.assertIs(so_administrador(api, administrador=True), api)


class TestCentralDoOperador(unittest.TestCase):
    def test_sem_editor_e_skills(self):
        pagina = html.unescape(montar_pagina(administrador=False))
        self.assertIn("window.MODO_OPERADOR = true", pagina)
        self.assertNotIn('id="quadro-assistentes"', pagina)
        self.assertNotIn('id="quadro-habilidades"', pagina)
        self.assertIn('id="quadro-alertas"', pagina)  # alertas é uso, continua
        for aba in ("aba-inteligencia", "aba-assistentes", "aba-habilidades"):
            self.assertRegex(pagina, rf'data-so-admin id="{aba}"')

    def test_administrador_ve_tudo(self):
        pagina = montar_pagina(administrador=True)
        self.assertNotIn("window.MODO_OPERADOR = true", pagina)
        self.assertIn('id="quadro-habilidades"', pagina)


class TestBotoesDaBolinha(unittest.TestCase):
    def tearDown(self):
        moldura.usar_botao_debug(True)

    def test_operador_sem_o_botao_de_debug(self):
        moldura.usar_botao_debug(False)
        ids = [b["id"] for b in moldura.desenho_compacto()["botoes"]]
        self.assertEqual(ids, ["alerta", "engrenagem", "microfone"])
        self.assertEqual(len(moldura.formas_compactas(1.0)[2]), 3)  # o recorte acompanha
        moldura.usar_botao_debug(True)
        self.assertEqual([b["id"] for b in moldura.desenho_compacto()["botoes"]],
                         ["alerta", "engrenagem", "microfone", "debug"])

    def test_botoes_cabem_na_janela_sem_se_encostar(self):
        for com_debug in (True, False):
            moldura.usar_botao_debug(com_debug)
            desenho = moldura.desenho_compacto()
            botoes = desenho["botoes"]
            for b in botoes:
                self.assertGreaterEqual(b["y"], 0)
                self.assertLessEqual(b["y"] + b["lado"], desenho["altura"])
            for a, b in zip(botoes, botoes[1:]):
                distancia = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
                self.assertGreater(distancia, a["lado"] + 2, (com_debug, a["id"], b["id"]))
