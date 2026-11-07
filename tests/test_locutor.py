import os
import threading
import time
import unittest
import wave
from unittest import mock

import numpy as np

from merlin.estado import EstadoAssistente
from merlin.voz.locutor import Locutor


class SintetizadorLento:
    """Grava um WAV curto para cada trecho, demorando um pouco, e anota a ordem dos acontecimentos."""

    def __init__(self, diario, demora=0.05, falhar=False):
        self.diario, self.demora, self.falhar = diario, demora, falhar
        self.textos, self.arquivos = [], []

    def gerar(self, texto, voz, arquivo):
        if self.falhar:
            raise RuntimeError("sem voz")
        time.sleep(self.demora)
        with wave.open(arquivo, "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
            w.writeframes((np.ones(1600) * 1000).astype(np.int16).tobytes())
        self.textos.append(texto)
        self.arquivos.append(arquivo)
        self.diario.append(f"gerou:{texto}")


class TocadorFalso:
    """Substitui o pygame.mixer.music: cada arquivo "toca" por um tempo curto."""

    def __init__(self, diario, duracao=0.05, ao_tocar=None):
        self.diario, self.duracao, self.ao_tocar = diario, duracao, ao_tocar
        self._fim = 0.0
        self.tocados = []

    def load(self, arquivo):
        self._atual = arquivo

    def play(self):
        self.tocados.append(self._atual)
        self.diario.append(f"tocou:{len(self.tocados)}")
        self._fim = time.time() + self.duracao
        if self.ao_tocar:
            self.ao_tocar(len(self.tocados))

    def get_busy(self):
        return time.time() < self._fim

    def stop(self):
        self._fim = 0.0

    def unload(self):
        pass


class TestLocutor(unittest.TestCase):
    def setUp(self):
        self.diario = []
        self.estado = EstadoAssistente()
        self.estado.ativo.set()
        self.canal = mock.Mock()
        self.preferencias = mock.Mock()
        self.preferencias.voz = "clonada:teste"
        self.tocador = TocadorFalso(self.diario)
        p = mock.patch("merlin.voz.locutor.pygame")
        pygame = p.start()
        self.addCleanup(p.stop)
        pygame.mixer.music = self.tocador

    def _falar(self, texto, sintetizador=None):
        self.sintetizador = sintetizador or SintetizadorLento(self.diario)
        Locutor(self.estado, self.canal, self.sintetizador, self.preferencias).falar(texto)

    def test_voz_clonada_comeca_a_tocar_antes_de_gerar_tudo(self):
        self._falar("Primeira frase. Segunda frase. Terceira frase.")
        self.assertEqual(self.sintetizador.textos, ["Primeira frase.", "Segunda frase.", "Terceira frase."])
        self.assertEqual(len(self.tocador.tocados), 3)
        self.assertLess(self.diario.index("tocou:1"), self.diario.index("gerou:Terceira frase."))

    def test_voz_do_piper_vai_inteira(self):
        self.preferencias.voz = "pt_BR-faber-medium"
        self._falar("Primeira frase. Segunda frase.")
        self.assertEqual(self.sintetizador.textos, ["Primeira frase. Segunda frase."])

    def test_interromper_para_de_tocar_e_de_gerar(self):
        self.tocador.ao_tocar = lambda n: self.estado.interromper.set() if n == 1 else None
        self._falar("Um. Dois. Três. Quatro. Cinco. Seis.", SintetizadorLento(self.diario, demora=0.1))
        self.assertEqual(len(self.tocador.tocados), 1)
        self.assertLess(len(self.sintetizador.textos), 6)

    def test_interromper_enquanto_a_proxima_frase_e_gerada(self):
        sintetizador = SintetizadorLento(self.diario, demora=0.4)
        threading.Timer(0.6, self.estado.interromper.set).start()  # depois da 1ª frase, durante a 2ª
        inicio = time.time()
        self._falar("Um. Dois. Três.", sintetizador)
        self.assertLess(time.time() - inicio, 0.9)  # não esperou a 2ª frase ficar pronta
        self.assertEqual(len(self.tocador.tocados), 1)

    def test_arquivos_temporarios_sao_apagados(self):
        self._falar("Um. Dois. Três.")
        time.sleep(0.1)
        self.assertTrue(self.sintetizador.arquivos)
        self.assertFalse(any(os.path.exists(a) for a in self.sintetizador.arquivos))

    def test_estados_voltam_ao_normal(self):
        self._falar("Um. Dois.")
        self.assertFalse(self.estado.falando.is_set())
        self.assertFalse(self.estado.reproduzindo.is_set())

    def test_falha_antes_de_tocar_usa_a_voz_do_windows(self):
        with mock.patch.object(Locutor, "_falar_com_voz_do_windows") as windows, \
                self.assertLogs("merlin.voz.locutor", "WARNING"):
            self._falar("Oi.", SintetizadorLento(self.diario, falhar=True))
        windows.assert_called_once_with("Oi.")


if __name__ == "__main__":
    unittest.main()


class TestRespostaNaJanela(unittest.TestCase):
    def _falar(self, texto, voz):
        estado, canal, preferencias = EstadoAssistente(), mock.Mock(), mock.Mock()
        preferencias.voz = voz
        with mock.patch("merlin.voz.locutor.pygame") as pygame:
            pygame.mixer.music = TocadorFalso([])
            Locutor(estado, canal, SintetizadorLento([]), preferencias).falar(texto)
        return canal

    def test_cada_trecho_vai_para_a_janela_com_a_duracao_do_audio(self):
        canal = self._falar("Primeira frase. Segunda frase.", "clonada:teste")
        canal.resposta.assert_called_once_with()
        trechos = [c.args for c in canal.trecho_falado.call_args_list]
        self.assertEqual([t for t, _ in trechos], ["Primeira frase.", "Segunda frase."])
        self.assertTrue(all(abs(d - 0.1) < 0.06 for _, d in trechos))  # o WAV de teste tem 0,1 s

    def test_voz_do_piper_vai_inteira(self):
        canal = self._falar("A capital da França é Paris.", "pt_BR-faber-medium")
        self.assertEqual(canal.trecho_falado.call_args.args[0], "A capital da França é Paris.")

    def test_interromper_avisa_a_janela(self):
        estado, canal, preferencias = EstadoAssistente(), mock.Mock(), mock.Mock()
        preferencias.voz = "clonada:teste"
        tocador = TocadorFalso([], ao_tocar=lambda n: estado.interromper.set())
        with mock.patch("merlin.voz.locutor.pygame") as pygame:
            pygame.mixer.music = tocador
            Locutor(estado, canal, SintetizadorLento([]), preferencias).falar("Um. Dois. Três.")
        canal.fala_interrompida.assert_called_once_with()
        self.assertEqual(canal.trecho_falado.call_count, 1)

    def test_canal_entrega_os_eventos_em_ordem(self):
        from merlin.interface.eventos import CanalInterface, TipoEvento
        canal = CanalInterface()
        canal.legenda("Qual a capital da França?")
        canal.resposta()
        canal.trecho_falado("Paris.", 0.8)
        canal.fala_interrompida()
        self.assertEqual(canal.proximo(0.1), (TipoEvento.LEGENDA, "Qual a capital da França?"))
        self.assertEqual(canal.proximo(0.1), (TipoEvento.RESPOSTA, None))
        self.assertEqual(canal.proximo(0.1), (TipoEvento.TRECHO_FALADO, {"texto": "Paris.", "duracao": 0.8}))
        self.assertEqual(canal.proximo(0.1), (TipoEvento.FALA_INTERROMPIDA, None))


