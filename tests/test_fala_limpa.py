"""O que a IA devolve é lido em voz alta: nada de raciocínio interno, formatação de texto nem emojis."""
import unittest

from merlin.ia.cliente import sem_raciocinio
from merlin.ia.conversa import Conversa, para_falar
from merlin.nucleo.memoria_conversa import MemoriaConversa
from tests.falsos import ClienteFalso


class TestSemRaciocinio(unittest.TestCase):
    def test_descarta_o_raciocinio_de_um_modelo_que_so_pensa(self):
        # Como o Qwen3-4B-Thinking respondeu a um "olá": o raciocínio em inglês, e a resposta depois do </think>
        bruto = "Okay, the user said \"olá\"...\nI think that's good.\n</think>\n\nOlá, senhor! Como posso ajudar hoje?"
        with self.assertLogs("merlin.ia.cliente", "WARNING"):
            self.assertEqual(sem_raciocinio(bruto), "Olá, senhor! Como posso ajudar hoje?")

    def test_resposta_normal_nao_muda(self):
        self.assertEqual(sem_raciocinio("  Sete vezes oito é cinquenta e seis.  "), "Sete vezes oito é cinquenta e seis.")

    def test_bloco_de_raciocinio_completo(self):
        with self.assertLogs("merlin.ia.cliente", "WARNING"):
            self.assertEqual(sem_raciocinio("<think>vou responder</think>Bom dia."), "Bom dia.")


class TestParaFalar(unittest.TestCase):
    def test_tira_formatacao_e_emojis(self):
        self.assertEqual(para_falar("Usa a *varinha*. 😊"), "Usa a varinha.")
        self.assertEqual(para_falar("**Atenção**: use o _EPI_ 👍🏽 sempre !"), "Atenção: use o EPI sempre!")
        self.assertEqual(para_falar("# Título ✅"), "Título")

    def test_mantem_acentos_e_pontuacao(self):
        frase = "Não, senhor: são cinquenta e seis. Algo mais?"
        self.assertEqual(para_falar(frase), frase)

    def test_conversa_ja_devolve_pronta_para_falar(self):
        resposta = Conversa(ClienteFalso("Claro, senhor! 😄 **Aqui está.**"), MemoriaConversa()).responder("oi")
        self.assertEqual(resposta, "Claro, senhor! Aqui está.")


if __name__ == "__main__":
    unittest.main()
