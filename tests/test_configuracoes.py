import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from merlin.config import MODELO_IA
from merlin.ia.cliente import ModeloInstalado
from merlin.interface.configuracoes import ServicoConfiguracoes
from merlin.nucleo.memoria_conversa import MemoriaConversa
from merlin.preferencias import Preferencias
from tests.falsos import LocutorFalso

INSTALADOS = [ModeloInstalado("llama3.2:latest", 2.0, "3.2B"), ModeloInstalado("qwen3:8b", 5.2, "8.2B")]


class CanalFalso:
    def __init__(self):
        self.avisos = 0

    def personalidade(self):
        self.avisos += 1


class ClienteFalso:
    def __init__(self):
        self.preaquecido = 0

    def preaquecer(self):
        self.preaquecido += 1


class TestConfiguracoes(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.arquivo = Path(pasta.name) / "config.json"
        self.preferencias = Preferencias(self.arquivo)
        self.canal, self.cliente, self.memoria = CanalFalso(), ClienteFalso(), MemoriaConversa()
        self.servico = ServicoConfiguracoes(self.preferencias, LocutorFalso(), self.canal, self.memoria, self.cliente)
        p = mock.patch("merlin.interface.configuracoes.listar_modelos", return_value=INSTALADOS)
        self.listar = p.start()
        self.addCleanup(p.stop)
        t = mock.patch("merlin.interface.configuracoes.threading.Thread")  # executa na hora, sem thread
        self.thread = t.start()
        self.thread.side_effect = lambda target, args=(), daemon=True: mock.Mock(start=lambda: target(*args))
        self.addCleanup(t.stop)

    def test_estado_atual(self):
        dados = self.servico.estado_atual()
        self.assertEqual(dados["personalidade"], "merlin")
        self.assertEqual(dados["modelo"], MODELO_IA)
        self.assertEqual([m["nome"] for m in dados["modelos"]], ["llama3.2:latest", "qwen3:8b"])
        self.assertIn("8.2B", dados["modelos"][1]["detalhe"])
        self.assertEqual(dados["erro_modelos"], "")

    def test_trocar_modelo_salva_e_preaquece(self):
        self.assertEqual(self.servico.trocar_modelo("llama3.2:latest"), "")
        self.assertEqual(Preferencias(self.arquivo).modelo_ia, "llama3.2:latest")
        self.assertEqual(self.cliente.preaquecido, 1)

    def test_modelo_nao_instalado_e_recusado(self):
        self.assertIn("não está instalado", self.servico.trocar_modelo("gpt-inexistente"))
        self.assertEqual(self.preferencias.modelo_ia, MODELO_IA)
        self.assertEqual(self.cliente.preaquecido, 0)

    def test_ollama_fechado(self):
        self.listar.side_effect = ConnectionError("fora do ar")
        self.assertIn("Ollama", self.servico.trocar_modelo("qwen3:8b"))
        dados = self.servico.estado_atual()
        self.assertIn("Ollama", dados["erro_modelos"])
        self.assertEqual([m["nome"] for m in dados["modelos"]], [MODELO_IA])  # o atual continua visível

    def test_trocar_assistente_avisa_a_janela_limpa_a_memoria_e_mostra_a_voz_dele(self):
        self.memoria.registrar("oi", "olá")
        dados = self.servico.trocar_personalidade("jarvis")
        self.assertEqual(self.preferencias.personalidade.id, "jarvis")
        self.assertEqual(self.canal.avisos, 1)
        self.assertEqual(self.memoria.como_mensagens(), [])
        self.assertEqual(dados["voz"], "Jarvis (digital)")

    def test_mesmo_assistente_nao_faz_nada(self):
        self.servico.trocar_personalidade("merlin")
        self.assertEqual(self.canal.avisos, 0)

    def test_trocar_voz(self):
        self.servico.trocar_voz("Cadu (masculina)")
        self.assertEqual(self.preferencias.voz, "pt_BR-cadu-medium")
        self.servico.trocar_voz("voz inventada")
        self.assertEqual(self.preferencias.voz, "pt_BR-cadu-medium")

    def test_modelo_salvo_sobrevive_ao_reiniciar(self):
        self.arquivo.write_text(json.dumps({"modelo_ia": "llama3.2:latest"}), encoding="utf-8")
        self.assertEqual(Preferencias(self.arquivo).modelo_ia, "llama3.2:latest")


    def test_estado_traz_a_cor_e_o_nome_do_assistente(self):
        dados = self.servico.estado_atual()
        personalidade = self.preferencias.personalidade
        self.assertEqual(dados["nome"], personalidade.nome)
        self.assertTrue(dados["cor"].startswith("#"))  # sem cor escolhida, vale a padrão do visual
        self.assertEqual(dados["sistema"]["ollama"], ("ok", "online"))

    def test_sistema_mostra_ollama_microfone_e_reconhecimento(self):
        from merlin.estado import EstadoAssistente

        class TranscritorFalso:
            dispositivo = "gpu"

        estado = EstadoAssistente()
        servico = ServicoConfiguracoes(self.preferencias, LocutorFalso(), self.canal, self.memoria, self.cliente,
                                       estado, TranscritorFalso())
        sistema = servico.sistema()
        self.assertEqual(sistema["reconhecimento"], ("ok", "placa de vídeo"))
        self.assertEqual(sistema["microfone"], ("ok", "ativo"))
        estado.microfone_desligado.set()
        self.assertEqual(servico.sistema()["microfone"], ("desligado", "mudo"))
        with mock.patch("merlin.interface.configuracoes.listar_modelos", side_effect=ConnectionError):
            self.assertEqual(servico.sistema()["ollama"], ("erro", "offline"))


if __name__ == "__main__":
    unittest.main()
