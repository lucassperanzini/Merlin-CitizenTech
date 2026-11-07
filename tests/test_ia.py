import json
import unittest
from unittest import mock

from merlin.acoes.sessao import Dispensar
from merlin.ia.confirmacao import ClassificadorConfirmacao, RespostaConfirmacao
from merlin.ia.frases import GeradorFrases, frase_valida, valida_para
from merlin.ia.divisao import DivisorTarefas
from merlin.ia.intencoes import ClassificadorIntencao, TipoIntencao
from merlin.personalidades import EMBUTIDAS
from tests.falsos import ClienteFalso

MERLIN, JARVIS = EMBUTIDAS["merlin"], EMBUTIDAS["jarvis"]


def classificar(alvo, intencao, busca="", comando="frase"):
    resposta = json.dumps({"alvo": alvo, "intencao": intencao, "busca": busca})
    return ClassificadorIntencao(ClienteFalso(resposta)).classificar(comando)


class TestRegrasDeIntencao(unittest.TestCase):
    def test_sair_exige_que_o_alvo_seja_o_merlin(self):
        self.assertIs(classificar("merlin", "dispensar").tipo, TipoIntencao.DISPENSAR)
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

    def test_clique_aceita_verbos_de_acao_e_pedidos_educados(self):
        for frase in ("clica em salvar", "dá play", "da play no spotify", "pausa a música", "salva", "pula pra próxima",
                      "avança", "confirma", "envia", "pode clicar em enviar", "você pode apertar ok",
                      "quero que você clique em cancelar", "por favor, seleciona a opção dois"):
            self.assertIs(classificar("x", "clicar_botao", comando=frase).tipo, TipoIntencao.CLICAR_BOTAO, frase)

    def test_pergunta_sobre_botao_nao_clica(self):
        for frase in ("o que acontece se eu clicar em formatar", "vale a pena salvar em pdf",
                      "como faço para pausar o spotify", "playlist boa para estudar"):
            self.assertIs(classificar("x", "clicar_botao", comando=frase).tipo, TipoIntencao.CONVERSAR, frase)

    def test_configuracoes_do_assistente(self):
        for frase in ("abre as configurações", "abre suas configurações", "abre as configurações do jarvis",
                      "quero mexer nos seus ajustes"):
            self.assertIs(classificar("merlin", "abrir_configuracoes", comando=frase).tipo,
                          TipoIntencao.ABRIR_CONFIGURACOES, frase)

    def test_configuracoes_de_outra_coisa_nao_abrem_as_dele(self):
        windows = classificar("configurações", "abrir_configuracoes", comando="abre as configurações do windows")
        self.assertEqual((windows.tipo, windows.alvo), (TipoIntencao.ABRIR_PROGRAMA, "configurações"))
        for frase in ("como abro as configurações do celular", "abre as configurações do spotify"):
            self.assertIs(classificar("merlin", "abrir_configuracoes", comando=frase).tipo, TipoIntencao.CONVERSAR, frase)

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


def gerador(conjunto, resposta):
    return GeradorFrases(ClienteFalso(resposta), lambda: conjunto)


class TestFrasesDoMerlin(unittest.TestCase):
    TEXTO = "Recolho meu cajado sob a lua. Basta chamar meu nome."

    def test_usa_a_frase_do_modelo(self):
        self.assertEqual(gerador(MERLIN.despedida, self.TEXTO).gerar(), self.TEXTO)

    def test_pergunta_lixo_e_tratamento_viram_reserva(self):
        for texto in ("Precisa de mais alguma coisa antes de eu ir?", 'vron {"name": "x"}', "", "Tchau.",
                      "Vou descansar, meu senhor. Basta chamar."):
            self.assertIn(gerador(MERLIN.despedida, texto).gerar(), MERLIN.despedida.reservas, texto)

    def test_sem_ia_usa_reserva_sem_repetir_em_seguida(self):
        for conjunto in (MERLIN.despedida, MERLIN.saudacao):
            g = gerador(conjunto, ConnectionError("fora do ar"))
            frases = [g.gerar() for _ in range(30)]
            self.assertTrue(all(f in conjunto.reservas for f in frases))
            self.assertTrue(all(a != b for a, b in zip(frases, frases[1:])))

    def test_frase_repetida_e_copia_do_exemplo_viram_reserva(self):
        g = gerador(MERLIN.despedida, self.TEXTO)
        g.gerar()
        self.assertIn(g.gerar(), MERLIN.despedida.reservas)
        self.assertIn(gerador(MERLIN.despedida, MERLIN.despedida.exemplos[0]).gerar(), MERLIN.despedida.reservas)

    def test_saudacao_do_merlin_precisa_do_nome(self):
        self.assertIn(gerador(MERLIN.saudacao, "Sob a lua, eu ofereço meus conselhos. O que deseja?").gerar(),
                      MERLIN.saudacao.reservas)
        texto = "Sob a lua, eu sou Merlin, seu mago. Como posso ajudar?"
        self.assertEqual(gerador(MERLIN.saudacao, texto).gerar(), texto)

    def test_palavrao_vira_reserva(self):
        texto = "Vou mijar perto do caldeirão, eu sou Merlin. Volto quando chamar."
        for conjunto in (MERLIN.despedida, MERLIN.saudacao):
            self.assertIn(gerador(conjunto, texto).gerar(), conjunto.reservas)

    def test_filtro_nao_barra_palavras_normais(self):
        for texto in ("Consulto o grimório sob a lua. Basta chamar.", "A cauda da coruja repousa no ramo. Basta chamar."):
            self.assertTrue(frase_valida(texto), texto)

    def test_tema_exemplo_e_recentes_vao_no_pedido(self):
        cliente = ClienteFalso("Sob a lua, eu sou Merlin, seu mago. Como posso ajudar?")
        g = GeradorFrases(cliente, lambda: MERLIN.saudacao)
        g.gerar()
        g.gerar()
        pedido = cliente.chamadas[1][0]["content"]
        self.assertIn("Sob a lua", pedido)
        self.assertNotIn("{tema}", pedido)
        self.assertNotIn("{exemplo}", pedido)


class TestFrasesDoJarvis(unittest.TestCase):
    def test_jarvis_pode_chamar_de_senhor(self):
        texto = "Reduzindo a energia por ora, senhor. É só me chamar."
        self.assertEqual(gerador(JARVIS.despedida, texto).gerar(), texto)

    def test_saudacao_do_jarvis_nao_exige_o_nome(self):
        texto = "Sistemas prontos e a rede estável, senhor. Em que posso ajudar?"
        self.assertEqual(gerador(JARVIS.saudacao, texto).gerar(), texto)

    def test_reservas_sao_validas(self):
        for p in (MERLIN, JARVIS):
            for conjunto in (p.saudacao, p.despedida):
                for frase in conjunto.reservas:
                    self.assertTrue(valida_para(frase, conjunto), f"{p.id}: {frase}")
                self.assertGreater(len(conjunto.reservas), 3)  # sempre sobra uma além das recentes

    def test_troca_de_personalidade_muda_as_frases_na_hora(self):
        escolhida = {"p": MERLIN}
        g = GeradorFrases(ClienteFalso(ConnectionError("x")), lambda: escolhida["p"].despedida)
        self.assertIn(g.gerar(), MERLIN.despedida.reservas)
        escolhida["p"] = JARVIS
        self.assertIn(g.gerar(), JARVIS.despedida.reservas)


class TestAcoesDeSaida(unittest.TestCase):
    def test_so_saem_depois_de_falar(self):
        sessao = mock.Mock()
        r = Dispensar(sessao, gerador(MERLIN.despedida, "Recolho meu cajado sob a lua. Basta chamar meu nome."))(None)
        sessao.desativar.assert_not_called()
        r.depois()
        sessao.desativar.assert_called_once()

if __name__ == "__main__":
    unittest.main()
