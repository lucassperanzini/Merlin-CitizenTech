import threading
import time
import unittest
from unittest import mock

from merlin.audio import ouvinte as modulo
from merlin.audio.ouvinte import Ouvinte
from merlin.estado import EstadoAssistente

SILENCIO = bytes(modulo.AMOSTRAS * 2)


class DetectorFalso:
    def probabilidade(self, _dados):
        return 0.0

    def reiniciar(self):
        pass


class MicrofoneFalso:
    """Conta quantas vezes foi aberto e fechado, e quantas leituras teve."""

    def __init__(self):
        self.aberto = False
        self.aberturas = 0
        self.fechamentos = 0
        self.leituras = 0
        self.stream = self

    def __enter__(self):
        self.aberto = True
        self.aberturas += 1
        return self

    def __exit__(self, *_):
        self.aberto = False
        self.fechamentos += 1

    def read(self, _tamanho):
        self.leituras += 1
        time.sleep(0.005)
        return SILENCIO


def esperar(condicao, segundos=2.0):
    fim = time.time() + segundos
    while time.time() < fim:
        if condicao():
            return True
        time.sleep(0.01)
    return False


class TestMudoFechaOMicrofone(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoAssistente()
        self.microfone = MicrofoneFalso()
        self.ouvinte = Ouvinte(self.estado, mock.Mock(), mock.Mock(), mock.Mock())
        self.ouvinte._microfone = self.microfone
        detector = mock.patch.object(modulo, "DetectorVoz", DetectorFalso)
        detector.start()
        self.addCleanup(detector.stop)
        self.escuta = threading.Thread(target=self.ouvinte._escutar, daemon=True)
        self.addCleanup(self._parar)

    def _parar(self):
        self.estado.encerrando.set()
        if self.escuta.ident is not None:  # só se a escuta chegou a começar
            self.escuta.join(2)

    def test_no_mudo_o_microfone_fica_fechado_e_nada_e_lido(self):
        self.escuta.start()
        self.assertTrue(esperar(lambda: self.microfone.aberto and self.microfone.leituras > 3))
        self.estado.microfone_desligado.set()
        self.assertTrue(esperar(lambda: not self.microfone.aberto))
        leituras = self.microfone.leituras
        time.sleep(0.3)
        self.assertEqual(self.microfone.leituras, leituras)  # fechado: nenhum áudio chega

    def test_ao_sair_do_mudo_abre_de_novo(self):
        self.estado.microfone_desligado.set()
        self.escuta.start()
        time.sleep(0.2)
        self.assertEqual(self.microfone.aberturas, 0)  # começou no mudo: nem abriu
        self.estado.microfone_desligado.clear()
        self.assertTrue(esperar(lambda: self.microfone.aberto))
        self.assertEqual(self.microfone.aberturas, 1)

    def test_microfone_que_nao_abre_nao_derruba_a_escuta(self):
        tentativas = []

        def falha():
            tentativas.append(1)
            raise OSError("sem microfone")

        with mock.patch.object(MicrofoneFalso, "__enter__", lambda _self: falha()), \
                mock.patch.object(modulo, "ESPERA_APOS_FALHA", 0.05):
            self.escuta.start()
            self.assertTrue(esperar(lambda: len(tentativas) >= 2))  # tentou de novo
            self.assertTrue(self.escuta.is_alive())

    def test_frase_na_fila_de_antes_do_mudo_nao_e_transcrita(self):
        self.estado.microfone_desligado.set()
        self.ouvinte._ao_ouvir(mock.Mock())
        self.ouvinte._transcritor.transcrever.assert_not_called()


if __name__ == "__main__":
    unittest.main()
