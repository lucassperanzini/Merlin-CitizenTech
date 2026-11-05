import unittest
from unittest import mock

from merlin.audio import transcricao
from merlin.audio.transcricao import Transcritor


class TestEscolhaDoModelo(unittest.TestCase):
    def setUp(self):
        for alvo in ("registrar_bibliotecas_nvidia",):
            substituto = mock.patch.object(transcricao, alvo)
            substituto.start()
            self.addCleanup(substituto.stop)

    def test_usa_a_placa_de_video_quando_funciona(self):
        with mock.patch.object(transcricao, "carregar_na_placa_de_video", return_value="gpu"), \
                mock.patch.object(transcricao, "carregar_na_cpu") as cpu:
            transcritor = Transcritor()
            transcritor.precarregar()
        self.assertEqual(transcritor._modelo, "gpu")
        cpu.assert_not_called()

    def test_volta_para_a_cpu_se_a_placa_falhar(self):
        with mock.patch.object(transcricao, "carregar_na_placa_de_video", side_effect=RuntimeError("sem cublas")), \
                mock.patch.object(transcricao, "carregar_na_cpu", return_value="cpu"):
            transcritor = Transcritor()
            transcritor.precarregar()
        self.assertEqual(transcritor._modelo, "cpu")

    def test_carrega_uma_vez_so(self):
        with mock.patch.object(transcricao, "carregar_na_placa_de_video", return_value="gpu") as gpu:
            transcritor = Transcritor()
            transcritor.precarregar()
            transcritor.precarregar()
        gpu.assert_called_once()


if __name__ == "__main__":
    unittest.main()
