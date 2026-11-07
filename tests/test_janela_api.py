import unittest

from merlin.estado import EstadoAssistente
from merlin.interface.janela import ApiJanela


class TestBotaoMudo(unittest.TestCase):
    def test_alterna_e_devolve_o_estado_novo(self):
        estado = EstadoAssistente()
        api = ApiJanela(None, None, estado)
        self.assertTrue(api.alternar_microfone())
        self.assertTrue(estado.microfone_desligado.is_set())
        self.assertFalse(api.alternar_microfone())
        self.assertFalse(estado.microfone_desligado.is_set())


if __name__ == "__main__":
    unittest.main()
