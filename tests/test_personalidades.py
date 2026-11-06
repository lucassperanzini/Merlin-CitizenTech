import json
import tempfile
import unittest
from pathlib import Path

from merlin.config import VOZES
from merlin.ia.intencoes import ClassificadorIntencao, TipoIntencao
from merlin.personalidades import JARVIS, MERLIN, PERSONALIDADES
from merlin.preferencias import Preferencias
from merlin.texto import remover_palavra_ativacao, tem_palavra_ativacao
from merlin.voz.envelope import envelope_do_audio
from tests.falsos import ClienteFalso


class TestPreferencias(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.arquivo = Path(pasta.name) / "config.json"

    def test_padrao_e_o_merlin(self):
        self.assertIs(Preferencias(self.arquivo).personalidade, MERLIN)

    def test_formato_antigo_vira_a_voz_do_merlin(self):
        self.arquivo.write_text(json.dumps({"voz": "pt_BR-cadu-medium"}), encoding="utf-8")
        p = Preferencias(self.arquivo)
        self.assertEqual(p.voz, "pt_BR-cadu-medium")
        p.personalidade = "jarvis"
        self.assertEqual(p.voz, JARVIS.voz_padrao)

    def test_cada_personalidade_lembra_a_propria_voz(self):
        p = Preferencias(self.arquivo)
        p.voz = "pt_BR-jeff-medium"
        p.personalidade = "jarvis"
        p.voz = "pt_BR-faber-medium"
        p.personalidade = "merlin"
        self.assertEqual(p.voz, "pt_BR-jeff-medium")
        recarregada = Preferencias(self.arquivo)
        self.assertEqual(recarregada.voz, "pt_BR-jeff-medium")
        recarregada.personalidade = "jarvis"
        self.assertEqual(Preferencias(self.arquivo).voz, "pt_BR-faber-medium")

    def test_personalidade_desconhecida_e_ignorada(self):
        p = Preferencias(self.arquivo)
        p.personalidade = "hal9000"
        self.assertIs(p.personalidade, MERLIN)

    def test_arquivo_estragado_nao_quebra(self):
        self.arquivo.write_text("[1, 2", encoding="utf-8")
        self.assertIs(Preferencias(self.arquivo).personalidade, MERLIN)


class TestPersonalidades(unittest.TestCase):
    def test_vozes_padrao_existem_no_seletor(self):
        for p in PERSONALIDADES.values():
            self.assertIn(p.voz_padrao, VOZES.values(), p.id)

    def test_sons_existem_e_tem_volume(self):
        for p in PERSONALIDADES.values():
            self.assertTrue(p.som_ativacao.is_file(), p.som_ativacao)
            self.assertGreater(max(envelope_do_audio(str(p.som_ativacao))), 0.9)

    def test_cada_um_ativa_so_pelo_proprio_nome(self):
        self.assertTrue(tem_palavra_ativacao("Jarvis, abre o chrome", JARVIS.palavras_ativacao))
        self.assertFalse(tem_palavra_ativacao("merlin, abre o chrome", JARVIS.palavras_ativacao))
        self.assertTrue(tem_palavra_ativacao("merlin, abre o chrome", MERLIN.palavras_ativacao))
        self.assertFalse(tem_palavra_ativacao("jarvis, abre o chrome", MERLIN.palavras_ativacao))

    def test_remove_o_nome_do_pedido(self):
        self.assertEqual(remover_palavra_ativacao("Jarvis, abre o chrome", JARVIS.palavras_ativacao), "abre o chrome")

    def test_dispensar_vale_com_o_nome_jarvis_no_alvo(self):
        resposta = json.dumps({"alvo": "jarvis", "intencao": "dispensar", "busca": "", "local": ""})
        self.assertIs(ClassificadorIntencao(ClienteFalso(resposta)).classificar("pode ir").tipo, TipoIntencao.DISPENSAR)


if __name__ == "__main__":
    unittest.main()
