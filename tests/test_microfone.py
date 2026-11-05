import time
import unittest
from unittest import mock

import numpy as np

from merlin.audio.microfone import FluxoComMedidor
from merlin.estado import EstadoAssistente

BLOCO = 1024
ECO = 1000


def bloco(valor):
    return np.full(BLOCO, valor, dtype=np.int16).tobytes()


class FluxoFalso:
    def __init__(self):
        self.proximo = bloco(0)
        self.fechado = False

    def read(self, _tamanho):
        return self.proximo

    def close(self):
        self.fechado = True


class ReconhecedorFalso:
    energy_threshold = 44
    dynamic_energy_threshold = True


class TestFluxoComMedidor(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoAssistente()
        self.fluxo = FluxoFalso()
        self.reconhecedor = ReconhecedorFalso()
        self.medidor = FluxoComMedidor(self.fluxo, self.reconhecedor, self.estado)
        self.tempo = 1000.0
        relogio = mock.patch("merlin.audio.microfone.time.time", side_effect=lambda: self.tempo)
        relogio.start()
        self.addCleanup(relogio.stop)

    def _ler(self, valor):
        self.fluxo.proximo = bloco(valor)
        self.tempo += 0.064
        return int(np.frombuffer(self.medidor.read(BLOCO), dtype=np.int16)[0])

    def test_audio_passa_intacto_fora_da_fala(self):
        self.assertEqual(self._ler(1234), 1234)

    def test_em_espera_nao_mede_volume(self):
        self._ler(9000)
        self.assertEqual(self.estado.consumir_nivel(), 0.0)

    def test_ativo_mede_volume(self):
        self.estado.ativo.set()
        self._ler(9000)
        self.assertGreater(self.estado.consumir_nivel(), 0.0)

    def test_durante_a_fala_entrega_silencio_e_nao_mede(self):
        self.estado.ativo.set()
        self.estado.falando.set()
        self.assertEqual(self._ler(9000), 0)
        self.assertEqual(self.estado.consumir_nivel(), 0.0)

    def test_durante_o_som_de_ativacao_entrega_silencio(self):
        self.estado.ativo.set()
        self.estado.microfone_mudo = lambda: True
        self.assertEqual(self._ler(9000), 0)
        self.assertEqual(self.estado.consumir_nivel(), 0.0)
        self.estado.microfone_mudo = lambda: False
        self.assertEqual(self._ler(1234), 1234)

    def test_limiar_automatico_congela_durante_a_fala_e_volta_depois(self):
        self.estado.falando.set()
        self._ler(0)
        self.assertFalse(self.reconhecedor.dynamic_energy_threshold)
        self.estado.falando.clear()
        self._ler(0)
        self.assertTrue(self.reconhecedor.dynamic_energy_threshold)

    def test_frase_que_interrompe_chega_inteira_em_ordem_e_sem_eco(self):
        self.estado.falando.set()
        self.estado.reproduzindo.set()
        saida = [self._ler(ECO) for _ in range(20)]
        voz = 5000
        while not self.estado.interromper.is_set():
            voz += 1
            saida.append(self._ler(voz))
        voz += 1
        saida.append(self._ler(voz))
        self.estado.reproduzindo.clear()
        self.estado.falando.clear()
        for _ in range(25):
            voz += 1
            saida.append(self._ler(voz))
        for _ in range(15):
            saida.append(self._ler(30))

        recebida = [v for v in saida if v > 5000]
        self.assertEqual(recebida, list(range(5001, voz + 1)))
        self.assertNotIn(ECO, saida)
        self.assertFalse(self.estado.interromper.is_set())

    def test_fim_normal_nao_reaproveita_o_audio_da_fala(self):
        self.estado.falando.set()
        self.estado.reproduzindo.set()
        for _ in range(20):
            self._ler(ECO)
        self.estado.reproduzindo.clear()
        self.estado.falando.clear()
        self.assertEqual(self._ler(30), 30)

    def test_close_e_repassado(self):
        self.medidor.close()
        self.assertTrue(self.fluxo.fechado)


if __name__ == "__main__":
    unittest.main()
