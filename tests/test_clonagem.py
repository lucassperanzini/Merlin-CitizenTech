import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from merlin.voz import amostra, clonagem
from merlin.voz.sintese import Sintetizador

TAXA = amostra.TAXA_AMOSTRA


def fala(segundos, taxa=TAXA):
    """Um tom com silêncio nas pontas, no lugar de uma voz."""
    t = np.arange(int(segundos * taxa)) / taxa
    silencio = np.zeros(int(0.5 * taxa), dtype=np.float32)
    return np.concatenate([silencio, (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), silencio])


class TestAmostra(unittest.TestCase):
    def test_tira_silencio_das_pontas_e_normaliza(self):
        audio, taxa = amostra.preparar(fala(5), TAXA)
        self.assertEqual(taxa, TAXA)
        self.assertAlmostEqual(len(audio) / taxa, 5.2, delta=0.05)  # 5 s de fala + 0,1 s de margem de cada lado
        self.assertAlmostEqual(float(np.max(np.abs(audio))), 0.9, places=3)

    def test_converte_a_taxa(self):
        audio, taxa = amostra.preparar(fala(4, 16000), 16000)
        self.assertEqual(taxa, TAXA)
        self.assertAlmostEqual(len(audio) / taxa, 4.2, delta=0.05)

    def test_limita_a_duracao(self):
        audio, taxa = amostra.preparar(fala(30), TAXA)
        self.assertEqual(len(audio) / taxa, amostra.DURACAO_MAXIMA)

    def test_curta_ou_em_silencio_e_recusada_com_mensagem(self):
        with self.assertRaisesRegex(amostra.AmostraInvalida, "menos de 3 segundos"):
            amostra.preparar(fala(1), TAXA)
        with self.assertRaisesRegex(amostra.AmostraInvalida, "silêncio"):
            amostra.preparar(np.zeros(TAXA * 5, dtype=np.float32), TAXA)

    def test_para_o_whisper(self):
        dados = amostra.para_16bits(fala(2), TAXA)
        self.assertEqual(len(dados), round(len(fala(2)) * 16000 / TAXA) * 2)


class TestVozesClonadas(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)

    def _salvar(self, nome="Minha Voz!", texto="olá, esta é a minha voz"):
        with mock.patch.dict("sys.modules", {"soundfile": mock.Mock(write=self._gravar_wav)}):
            return clonagem.salvar_voz_clonada(nome, np.zeros(TAXA, dtype=np.float32), TAXA, texto, self.pasta)

    @staticmethod
    def _gravar_wav(caminho, audio, taxa):
        with wave.open(str(caminho), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(taxa)
            w.writeframes((audio * 32767).astype(np.int16).tobytes())

    def test_salva_lista_e_encontra(self):
        voz = self._salvar()
        self.assertEqual((voz.id, voz.nome, voz.rotulo), ("clonada:minha_voz", "Minha Voz!", "Minha Voz! (clonada)"))
        self.assertTrue(voz.audio.is_file())
        self.assertEqual(json.loads((voz.pasta / "voz.json").read_text(encoding="utf-8"))["texto"],
                         "olá, esta é a minha voz")
        self.assertEqual(clonagem.listar_vozes_clonadas(self.pasta), [voz])
        self.assertEqual(clonagem.buscar_voz_clonada("clonada:minha_voz", self.pasta), voz)

    def test_nome_de_pasta_sem_acentos_nem_simbolos(self):
        self.assertEqual(clonagem.nome_de_pasta("Voz do Avô João!"), "voz_do_avo_joao")
        self.assertEqual(clonagem.nome_de_pasta("???"), "voz")

    def test_pasta_incompleta_e_ignorada(self):
        (self.pasta / "quebrada").mkdir()
        (self.pasta / "quebrada" / "voz.json").write_text("{}", encoding="utf-8")  # sem o áudio
        self.assertEqual(clonagem.listar_vozes_clonadas(self.pasta), [])

    def test_apagar(self):
        voz = self._salvar()
        clonagem.apagar_voz_clonada(voz)
        self.assertFalse(voz.pasta.exists())
        self.assertEqual(clonagem.listar_vozes_clonadas(self.pasta), [])

    def test_pasta_inexistente(self):
        self.assertEqual(clonagem.listar_vozes_clonadas(self.pasta / "nao_existe"), [])


class TestDividirTexto(unittest.TestCase):
    def test_divide_por_frases(self):
        self.assertEqual(clonagem.dividir_texto("Abri o chrome. Fechei o telegram! Algo mais?"),
                         ["Abri o chrome.", "Fechei o telegram!", "Algo mais?"])

    def test_frase_longa_quebra_nas_virgulas_sem_passar_do_limite(self):
        frase = ", ".join(["uma parte da frase bem comprida"] * 12) + "."
        trechos = clonagem.dividir_texto(frase, limite=80)
        self.assertGreater(len(trechos), 1)
        self.assertTrue(all(len(t) <= 80 for t in trechos), trechos)
        self.assertEqual(" ".join(trechos), frase)  # nada se perde

    def test_sem_virgulas_quebra_nos_espacos(self):
        frase = " ".join(["palavra"] * 60)
        trechos = clonagem.dividir_texto(frase, limite=50)
        self.assertTrue(all(len(t) <= 50 for t in trechos))
        self.assertEqual(" ".join(trechos), frase)

    def test_primeiro_trecho_curto_para_comecar_logo(self):
        frase = "A fotossíntese é o processo pelo qual as plantas, as algas e algumas bactérias transformam a luz, "                 "a água e o gás carbônico em glicose. Sem ela, nada viveria."
        trechos = clonagem.dividir_texto(frase, limite_primeiro=70)
        self.assertLessEqual(len(trechos[0]), 70)
        self.assertEqual(" ".join(trechos), frase)  # nada se perde nem muda de ordem
        self.assertEqual(trechos[-1], "Sem ela, nada viveria.")

    def test_so_o_primeiro_trecho_e_cortado_na_virgula(self):
        """Cortar todas as frases nas vírgulas deixava a fala picotada: cada pedaço termina como fim de frase."""
        texto = ("A fotossíntese é o processo pelo qual as plantas, as algas e algumas bactérias transformam a luz "
                 "do sol, a água e o gás carbônico em glicose. Sem ela, quase nada viveria na Terra, nem nós.")
        trechos = clonagem.dividir_texto(texto, limite=180, limite_primeiro=70)
        self.assertEqual(trechos[0], "A fotossíntese é o processo pelo qual as plantas,")
        self.assertEqual(trechos[1], "as algas e algumas bactérias transformam a luz do sol, a água e o gás carbônico "
                                     "em glicose.")  # o resto da frase vai inteiro
        self.assertEqual(trechos[2], "Sem ela, quase nada viveria na Terra, nem nós.")  # frase seguinte: inteira
        self.assertEqual(" ".join(trechos), texto)

    def test_texto_curto_ou_vazio(self):
        self.assertEqual(clonagem.dividir_texto("Pois não?"), ["Pois não?"])
        self.assertEqual(clonagem.dividir_texto("   "), ["."])


class MotorFalso:
    def __init__(self, erro=None):
        self.erro = erro
        self.chamadas = []

    def gerar(self, texto, voz):
        self.chamadas.append((texto, voz.id))
        if self.erro:
            raise self.erro
        return fala(1), TAXA

    def esquecer(self, voz_id):
        pass


class TestSintetizador(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.arquivo = str(Path(temporaria.name) / "saida.wav")
        self.voz = clonagem.VozClonada("clonada:teste", "Teste", Path(temporaria.name), "texto")
        p = mock.patch("merlin.voz.sintese.buscar_voz_clonada", side_effect=lambda v: self.voz if v == self.voz.id else None)
        p.start()
        self.addCleanup(p.stop)

    def test_voz_clonada_usa_o_motor_de_clonagem(self):
        motor = MotorFalso()
        Sintetizador(motor).gerar("oi", "clonada:teste", self.arquivo)
        self.assertEqual(motor.chamadas, [("oi", "clonada:teste")])
        with wave.open(self.arquivo) as w:
            self.assertEqual(w.getframerate(), TAXA)

    def test_falha_na_clonagem_fala_com_a_voz_reserva(self):
        sintetizador = Sintetizador(MotorFalso(erro=RuntimeError("sem placa de vídeo")))
        with mock.patch.object(sintetizador, "_gerar_piper") as piper, self.assertLogs("merlin.voz.sintese", "WARNING"):
            sintetizador.gerar("oi", "clonada:teste", self.arquivo)
        piper.assert_called_once_with("oi", "pt_BR-faber-medium", self.arquivo)

    def test_voz_clonada_apagada_tambem_cai_na_reserva(self):
        sintetizador = Sintetizador(MotorFalso())
        with mock.patch.object(sintetizador, "_gerar_piper") as piper, self.assertLogs("merlin.voz.sintese", "WARNING"):
            sintetizador.gerar("oi", "clonada:sumiu", self.arquivo)
        piper.assert_called_once()

    def test_voz_do_piper_nao_toca_na_clonagem(self):
        motor = MotorFalso()
        sintetizador = Sintetizador(motor)
        with mock.patch.object(sintetizador, "_gerar_piper") as piper:
            sintetizador.gerar("oi", "pt_BR-jeff-medium", self.arquivo)
        piper.assert_called_once()
        self.assertEqual(motor.chamadas, [])


class TestServicoClonagem(unittest.TestCase):
    def setUp(self):
        from merlin.interface.clonagem_voz import ServicoClonagem

        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)
        self.preferencias = mock.Mock(voz="pt_BR-faber-medium")
        self.preferencias.personalidade.voz_padrao = "mago_anciao"
        ouvinte = mock.Mock(gravar=lambda s: (fala(6, 16000) * 32767).astype(np.int16).tobytes())
        transcritor = mock.Mock(transcrever=lambda audio: "olá, esta é a minha voz")
        self.canal, self.sintetizador = mock.Mock(), mock.Mock()
        self.servico = ServicoClonagem(ouvinte, transcritor, self.preferencias, mock.Mock(), self.sintetizador,
                                       self.canal, pasta=self.pasta)
        p = mock.patch.dict("sys.modules", {"soundfile": mock.Mock(write=TestVozesClonadas._gravar_wav)})
        p.start()
        self.addCleanup(p.stop)

    def test_gravar_transcreve_e_salvar_passa_a_usar_a_voz(self):
        r = self.servico.gravar()
        self.assertEqual(r["texto"], "olá, esta é a minha voz")
        self.assertAlmostEqual(r["duracao"], 6.2, delta=0.1)
        self.assertEqual(self.servico.salvar("Minha voz", r["texto"]), {"voz": "Minha voz (clonada)"})
        self.assertEqual(self.preferencias.voz, "clonada:minha_voz")
        self.canal.personalidade.assert_called_once()
        self.sintetizador.esquecer_voz_clonada.assert_called_once_with("clonada:minha_voz")

    def test_salvar_sem_amostra_ou_sem_nome(self):
        self.assertIn("erro", self.servico.salvar("x", "y"))
        self.servico.gravar()
        self.assertIn("erro", self.servico.salvar("  ", "texto"))
        self.assertNotIn("erro", self.servico.salvar("Sem texto", ""))  # o XTTS só precisa do áudio

    def test_gravacao_em_silencio_avisa(self):
        self.servico._ouvinte.gravar = lambda s: bytes(16000 * 2 * 5)
        self.assertIn("silêncio", self.servico.gravar()["erro"])

    def test_apagar_volta_para_a_voz_padrao(self):
        self.servico.gravar()
        self.servico.salvar("Minha voz", "texto")
        self.assertEqual(self.servico.apagar_voz_atual(), {})
        self.assertEqual(self.preferencias.voz, "mago_anciao")
        self.assertEqual(clonagem.listar_vozes_clonadas(self.pasta), [])


if __name__ == "__main__":
    unittest.main()
