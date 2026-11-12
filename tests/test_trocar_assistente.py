import unittest

from merlin.acoes.assistentes import TrocarAssistente, encontrar_assistente, trocar_personalidade
from merlin.habilidades import HABILIDADES
from merlin.habilidades.base import Leitura
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.memoria_conversa import MemoriaConversa
from merlin.personalidades import PERSONALIDADES
from tests.falsos import com_segundo_assistente


class PreferenciasFalsas:
    def __init__(self, identificador="merlin"):
        self._id = identificador

    @property
    def personalidade(self):
        return PERSONALIDADES[self._id]

    @personalidade.setter
    def personalidade(self, identificador):
        self._id = identificador


class CanalFalso:
    def __init__(self):
        self.avisos = 0

    def personalidade(self):
        self.avisos += 1


def pedido(alvo):
    return Intencao(TipoIntencao("trocar_assistente"), alvo, f"troca para o {alvo}")


class TestTrocarAssistente(unittest.TestCase):
    def setUp(self):
        com_segundo_assistente(self)
        self.preferencias, self.canal, self.memoria = PreferenciasFalsas(), CanalFalso(), MemoriaConversa()
        self.acao = TrocarAssistente(self.preferencias, self.memoria, self.canal)

    def test_acha_pelo_nome_com_artigo_ou_palavra_de_chamada(self):
        for texto in ("sexta-feira", "a Sexta-feira", "pra sexta feira", "SEXTA-FEIRA"):
            self.assertEqual(encontrar_assistente(texto).id, "sexta_feira", texto)
        self.assertEqual(encontrar_assistente("o merlin").id, "merlin")
        self.assertIsNone(encontrar_assistente("ninguém conhecido"))

    def test_troca_e_se_apresenta_com_a_voz_nova(self):
        self.memoria.registrar("oi", "olá")
        resultado = self.acao(pedido("sexta_feira"))
        self.assertEqual(self.preferencias.personalidade.id, "sexta_feira")
        self.assertEqual(resultado.fala, PERSONALIDADES["sexta_feira"].apresentacao)
        self.assertEqual(self.canal.avisos, 1)  # a janela troca o visual
        self.assertEqual(self.memoria.como_mensagens(), [])  # a conversa era com o outro assistente

    def test_desconhecido_diz_quais_existem_e_nao_troca(self):
        resultado = self.acao(pedido("fulano"))
        self.assertIn("fulano", resultado.fala)
        self.assertIn("Sexta-feira", resultado.fala)
        self.assertEqual(self.preferencias.personalidade.id, "merlin")

    def test_o_mesmo_assistente_nao_troca(self):
        self.acao(pedido("merlin"))
        self.assertEqual(self.canal.avisos, 0)
        self.assertFalse(trocar_personalidade(self.preferencias, self.memoria, self.canal, "merlin"))

    def test_pergunta_vira_conversa(self):
        habilidade = next(h for h in HABILIDADES if h.nome == "trocar_assistente")
        correcao = habilidade.regra(Leitura("trocar_assistente", "", {}, "quais assistentes você tem?"))
        self.assertEqual(correcao.intencao, "conversar")
        self.assertIsNone(habilidade.regra(Leitura("trocar_assistente", "sexta_feira", {}, "troca para a sexta-feira")))


if __name__ == "__main__":
    unittest.main()
