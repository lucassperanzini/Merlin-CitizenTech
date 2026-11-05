import json
import unittest
from unittest import mock

from merlin.acoes.sessao import Dispensar, Encerrar
from merlin.estado import EstadoAssistente
from merlin.ia.confirmacao import ClassificadorConfirmacao, RespostaConfirmacao
from merlin.ia.despedida import GeradorDespedida, GeradorEncerramento
from merlin.ia.frase_mago import frase_valida
from merlin.ia.divisao import DivisorTarefas
from merlin.ia.intencoes import ClassificadorIntencao, TipoIntencao
from merlin.ia.prompts import DESPEDIDAS_RESERVA, ENCERRAMENTOS_RESERVA, SAUDACOES_RESERVA
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


class TestDivisao(unittest.TestCase):
    def _dividir(self, comando, tarefas):
        cliente = ClienteFalso(json.dumps({"tarefas": tarefas}))
        return DivisorTarefas(cliente).dividir(comando), cliente

    def test_sem_conectivo_nem_consulta_a_ia(self):
        resultado, cliente = self._dividir("abre o chrome", ["inventada"])
        self.assertEqual(resultado, ["abre o chrome"])
        self.assertEqual(cliente.chamadas, [])

    def test_palavra_que_contem_e_nao_e_conectivo(self):
        _, cliente = self._dividir("pesquisa elefante", ["x"])
        self.assertEqual(cliente.chamadas, [])

    def test_divide(self):
        resultado, _ = self._dividir("abre o chrome e pesquisa gatos", ["abre o chrome", "pesquisa gatos"])
        self.assertEqual(resultado, ["abre o chrome", "pesquisa gatos"])

    def test_verbo_repetido_e_aceito(self):
        resultado, _ = self._dividir("abre o paint e o word", ["abre o paint", "abre o word"])
        self.assertEqual(resultado, ["abre o paint", "abre o word"])

    def test_tarefa_inventada_e_recusada(self):
        frase = "abre o chrome e pesquisa gatos"
        resultado, _ = self._dividir(frase, ["abre o chrome", "apaga meus documentos"])
        self.assertEqual(resultado, [frase])

    def test_resposta_invalida_mantem_a_frase(self):
        frase = "abre o chrome e pesquisa gatos"
        for resposta in ("lixo", "[]", '{"tarefas": []}', '{"tarefas": 3}', "", '{"tarefas": [""]}'):
            self.assertEqual(DivisorTarefas(ClienteFalso(resposta)).dividir(frase), [frase], resposta)


class TestDespedida(unittest.TestCase):
    TEXTO = "Recolho meu cajado sob a lua. Basta chamar meu nome."

    def test_usa_a_frase_do_modelo(self):
        self.assertEqual(GeradorDespedida(ClienteFalso(self.TEXTO)).gerar(), self.TEXTO)

    def test_nao_exige_o_nome_do_merlin(self):
        self.assertNotIn("merlin", self.TEXTO.lower())
        self.assertEqual(GeradorEncerramento(ClienteFalso(self.TEXTO)).gerar(), self.TEXTO)

    def test_pergunta_e_lixo_viram_reserva(self):
        for texto in ("Precisa de mais alguma coisa antes de eu ir?", 'vron {"name": "x"}', "", "Tchau."):
            self.assertIn(GeradorDespedida(ClienteFalso(texto)).gerar(), DESPEDIDAS_RESERVA, texto)

    def test_sem_ia_usa_reserva_sem_repetir_em_seguida(self):
        for classe, reservas in ((GeradorDespedida, DESPEDIDAS_RESERVA), (GeradorEncerramento, ENCERRAMENTOS_RESERVA)):
            gerador = classe(ClienteFalso(ConnectionError("fora do ar")))
            frases = [gerador.gerar() for _ in range(30)]
            self.assertTrue(all(f in reservas for f in frases))
            self.assertTrue(all(a != b for a, b in zip(frases, frases[1:])))

    def test_frase_repetida_do_modelo_vira_reserva(self):
        gerador = GeradorDespedida(ClienteFalso(self.TEXTO))
        gerador.gerar()
        self.assertIn(gerador.gerar(), DESPEDIDAS_RESERVA)

    def test_exemplo_sorteado_vai_no_pedido_e_varia(self):
        cliente = ClienteFalso(ConnectionError("fora do ar"))
        gerador = GeradorDespedida(cliente)
        for _ in range(40):
            gerador.gerar()
        pedidos = [chamada[0]["content"] for chamada in cliente.chamadas]
        self.assertNotIn("{exemplo}", pedidos[0])
        usados = {e for e in GeradorDespedida.EXEMPLOS for p in pedidos if e in p}
        self.assertGreater(len(usados), 1)

    def test_palavrao_vira_reserva_em_todas_as_frases_do_mago(self):
        texto = "Vou mijar perto do caldeirão, eu sou Merlin. Volto quando chamar."
        self.assertIn(GeradorDespedida(ClienteFalso(texto)).gerar(), DESPEDIDAS_RESERVA)
        self.assertIn(GeradorEncerramento(ClienteFalso(texto)).gerar(), ENCERRAMENTOS_RESERVA)
        self.assertIn(GeradorSaudacao(ClienteFalso(texto)).gerar(), SAUDACOES_RESERVA)

    def test_filtro_nao_barra_palavras_normais(self):
        for texto in ("Consulto o grimório sob a lua. Basta chamar.", "Sigo para a floresta computada. Basta chamar.",
                      "A cauda da coruja repousa no ramo. Basta chamar.", "Recolho o cajado de pau-brasil. Basta me chamar."):
            self.assertEqual(frase_valida(texto), "pau" not in texto, texto)

    def test_copia_do_exemplo_vira_reserva(self):
        copia = GeradorDespedida.EXEMPLOS[0]
        self.assertIn(GeradorDespedida(ClienteFalso(copia)).gerar(), DESPEDIDAS_RESERVA)

    def test_reservas_sao_validas_e_nao_prometem_o_errado(self):
        gerador = GeradorDespedida(ClienteFalso(""))
        for frase in DESPEDIDAS_RESERVA + ENCERRAMENTOS_RESERVA:
            self.assertTrue(gerador.valida(frase), frase)
        for frase in ENCERRAMENTOS_RESERVA:
            self.assertNotIn("chamar", frase.lower())

    def test_acoes_usam_o_gerador_e_so_saem_depois(self):
        sessao, estado = mock.Mock(), EstadoAssistente()
        r = Dispensar(sessao, GeradorDespedida(ClienteFalso(self.TEXTO)))(None)
        self.assertEqual(r.fala, self.TEXTO)
        sessao.desativar.assert_not_called()
        r.depois()
        sessao.desativar.assert_called_once()

        r = Encerrar(estado, GeradorEncerramento(ClienteFalso(self.TEXTO)))(None)
        self.assertFalse(estado.encerrando.is_set())
        r.depois()
        self.assertTrue(estado.encerrando.is_set())


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
