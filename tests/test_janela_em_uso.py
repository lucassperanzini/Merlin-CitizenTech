import unittest
from unittest import mock

from merlin.acoes import janelas
from merlin.acoes.janelas import JanelaAberta

WIDGET = JanelaAberta(1, 10, "pythonw", "Agenda")
BLOCO = JanelaAberta(2, 20, "notepad", "Bloco de Notas")
CHROME = JanelaAberta(3, 30, "chrome", "Chrome")


class TestJanelaEmUso(unittest.TestCase):
    def _com(self, foco, abertas, sempre_na_frente=(1,)):
        with mock.patch.object(janelas, "_janela_com_foco", return_value=foco), \
                mock.patch.object(janelas, "listar_janelas", return_value=abertas), \
                mock.patch.object(janelas, "_sempre_na_frente", lambda hwnd: hwnd in sempre_na_frente), \
                mock.patch.object(janelas.win32gui, "IsIconic", return_value=False):
            return janelas.janela_em_uso()

    def test_a_janela_com_foco_vence_um_widget_sempre_na_frente(self):
        self.assertEqual(self._com(BLOCO, [WIDGET, CHROME, BLOCO]), BLOCO)

    def test_foco_no_merlin_pula_as_janelas_sempre_na_frente(self):
        self.assertEqual(self._com(None, [WIDGET, BLOCO, CHROME]), BLOCO)

    def test_so_ha_janela_sempre_na_frente(self):
        self.assertEqual(self._com(None, [WIDGET]), WIDGET)

    def test_sem_janelas(self):
        self.assertIsNone(self._com(None, []))


if __name__ == "__main__":
    unittest.main()
