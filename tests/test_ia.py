import json
import unittest

from merlin.ia.confirmacao import ClassificadorConfirmacao, RespostaConfirmacao
from merlin.ia.intencoes import ClassificadorIntencao, TipoIntencao
from merlin.ia.prompts import SAUDACOES_RESERVA
from merlin.ia.saudacao import GeradorSaudacao, saudacao_valida
from tests.falsos import ClienteFalso


def classificar(alvo, intencao, busca="", comando="frase"):
    resposta = json.dumps({"alvo": alvo, "intencao": intencao, "busca": busca})
    return ClassificadorIntencao(ClienteFalso(resposta)).classificar(comando)


class TestRegrasDeIntencao(unittest.TestCase):
    def test_sair_exige_que_o_alvo_seja_o_merlin(self):
        self.assertIs(classificar("merlin", "dispensar").tipo, TipoIntencao.DISPENSAR)
        self.assertIs(classificar("merlin", "encerrar").tipo, TipoIntencao.ENCERRAR)
        self.assertIs(classificar("discord", "encerrar").tipo, TipoIntencao.CONVERSAR)
        self.assertIs(classificar("colega", "dispensar").tipo, TipoIntencao.CONVERSAR)

    def test_fechar_outro_programa(self):
        intencao = classificar("chrome", "fechar_programa")
        self.assertIs(intencao.tipo, TipoIntencao.FECHAR_PROGRAMA)
        self.assertEqual(intencao.alvo, "chrome")

    def test_fechar_a_janela_e_dispensar(self):
        self.assertIs(classificar("essa janela", "fechar_programa").tipo, TipoIntencao.DISPENSAR)
        self.assertIs(classificar("merlin", "fechar_programa").tipo, TipoIntencao.DISPENSAR)

    def test_abrir_exige_um_programa(self):
        self.assertEqual(classificar("spotify", "abrir_programa").alvo, "spotify")
        self.assertIs(classificar("merlin", "abrir_programa").tipo, TipoIntencao.CONVERSAR)
        self.assertIs(classificar("", "abrir_programa").tipo, TipoIntencao.CONVERSAR)

    def test_pesquisa_usa_o_termo_completo(self):
        self.assertEqual(classificar("vim", "pesquisar_web", "como sair do vim").alvo, "como sair do vim")

    def test_pesquisa_sem_termo_usa_a_frase(self):
        self.assertEqual(classificar("x", "pesquisar_web", "", comando="procura gatos").alvo, "procura gatos")

    def test_resposta_invalida_vira_conversa(self):
        for resposta in ("não é json", "[1, 2]", '{"intencao": "inventada", "alvo": "x", "busca": ""}', ""):
            intencao = ClassificadorIntencao(ClienteFalso(resposta)).classificar("frase")
            self.assertIs(intencao.tipo, TipoIntencao.CONVERSAR, resposta)

    def test_comando_original_e_preservado(self):
        self.assertEqual(classificar("x", "conversar", comando="minha frase").comando, "minha frase")


class TestConfirmacao(unittest.TestCase):
    def _classificar(self, resposta):
        return ClassificadorConfirmacao(ClienteFalso(resposta)).classificar("Posso?", "pode")

    def test_respostas_validas(self):
        self.assertIs(self._classificar('{"resposta": "sim"}'), RespostaConfirmacao.SIM)
        self.assertIs(self._classificar('{"resposta": "nao"}'), RespostaConfirmacao.NAO)

    def test_resposta_invalida_nunca_autoriza(self):
        for resposta in ("lixo", "[]", '{"resposta": "talvez"}', ""):
            self.assertIs(self._classificar(resposta), RespostaConfirmacao.OUTRO, resposta)

    def test_pergunta_vai_no_prompt(self):
        cliente = ClienteFalso('{"resposta": "sim"}')
        ClassificadorConfirmacao(cliente).classificar("Posso fechar chrome?", "pode")
        self.assertIn("Posso fechar chrome?", cliente.chamadas[0][0]["content"])


class TestSaudacao(unittest.TestCase):
    def test_validacao(self):
        self.assertTrue(saudacao_valida("Saudações, sou Merlin, seu mago conselheiro. Como posso ajudar?"))
        for texto in ('vron {"name": "x"}', "Olá! Como posso ajudar você hoje?", "Sou Merlin, o mago conselheiro, e",
                      "Merlin.", "**Saudações**, sou Merlin, mago. O que deseja?", ""):
            self.assertFalse(saudacao_valida(texto), texto)

    def test_sem_ia_usa_reserva_sem_repetir_em_seguida(self):
        gerador = GeradorSaudacao(ClienteFalso(ConnectionError("fora do ar")))
        saudacoes = [gerador.gerar() for _ in range(30)]
        self.assertTrue(all(s in SAUDACOES_RESERVA for s in saudacoes))
        self.assertTrue(all(a != b for a, b in zip(saudacoes, saudacoes[1:])))

    def test_saudacao_do_modelo_e_usada(self):
        texto = "Sob a lua, eu sou Merlin, seu mago. Como posso ajudar?"
        self.assertEqual(GeradorSaudacao(ClienteFalso(texto)).gerar(), texto)

    def test_tema_e_recentes_vao_no_pedido(self):
        cliente = ClienteFalso("Sob a lua, eu sou Merlin, seu mago. Como posso ajudar?")
        gerador = GeradorSaudacao(cliente)
        gerador.gerar()
        gerador.gerar()
        self.assertIn("Sob a lua", cliente.chamadas[1][0]["content"])
        self.assertNotIn("{tema}", cliente.chamadas[1][0]["content"])


if __name__ == "__main__":
    unittest.main()
