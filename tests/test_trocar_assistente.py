import unittest

from merlin.acoes.assistentes import trocar_personalidade
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


class TestTrocarPersonalidade(unittest.TestCase):
    """A troca pela lista no nome da bolinha (a troca por voz foi removida)."""

    def setUp(self):
        com_segundo_assistente(self)
        self.preferencias, self.canal, self.memoria = PreferenciasFalsas(), CanalFalso(), MemoriaConversa()

    def test_troca_avisa_a_janela_e_limpa_a_conversa(self):
        self.memoria.registrar("oi", "olá")
        self.assertTrue(trocar_personalidade(self.preferencias, self.memoria, self.canal, "sexta_feira"))
        self.assertEqual(self.preferencias.personalidade.id, "sexta_feira")
        self.assertEqual(self.canal.avisos, 1)  # a janela troca o visual
        self.assertEqual(self.memoria.como_mensagens(), [])  # a conversa era com o outro assistente

    def test_o_mesmo_assistente_nao_troca(self):
        self.assertFalse(trocar_personalidade(self.preferencias, self.memoria, self.canal, "merlin"))
        self.assertEqual(self.canal.avisos, 0)

    def test_assistente_inexistente_nao_troca(self):
        self.assertFalse(trocar_personalidade(self.preferencias, self.memoria, self.canal, "fulano"))
        self.assertEqual(self.preferencias.personalidade.id, "merlin")


if __name__ == "__main__":
    unittest.main()
