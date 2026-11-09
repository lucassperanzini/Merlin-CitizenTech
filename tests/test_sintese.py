import unittest
from unittest import mock

from merlin.config import VOZ_RESERVA
from merlin.voz.sintese import Sintetizador


class TestVozInexistente(unittest.TestCase):
    def test_voz_antiga_usa_a_reserva(self):
        with mock.patch("merlin.voz.sintese.PiperVoice") as piper, self.assertLogs("merlin.voz.sintese", "WARNING"):
            Sintetizador().precarregar("clonada:voz_que_nao_existe")
        self.assertIn(VOZ_RESERVA, piper.load.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
