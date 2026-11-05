import time
import unittest
from unittest import mock

from merlin.acoes.clicar import ClicarBotao, e_perigoso
from merlin.acoes.controles import ResultadoClique, desempatar, escolher_controle
from merlin.acoes.janelas import JanelaAberta
from merlin.estado import EstadoAssistente
from merlin.ia.confirmacao import RespostaConfirmacao
from merlin.ia.escolha_botao import EscolhedorBotao
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.sessao import Sessao
from tests.falsos import CanalFalso, ClienteFalso, ClassificadorFalso, ConfirmadorFalso, DivisorFalso, LocutorFalso, SaudacaoFalsa

WORD = JanelaAberta(1, 1, "WINWORD", "Relatório - Word")
BOTOES = ["Salvar", "Salvar como", "Imprimir", "Excluir arquivo", "Enviar", "Cancelar", "Página inicial"]


class EscolhedorFalso:
    def __init__(self, resposta=None):
        self.resposta = resposta
        self.opcoes_recebidas = None

    def escolher(self, pedido, nomes):
        self.opcoes_recebidas = list(nomes)
        return self.resposta


class TestEscolhedorBotao(unittest.TestCase):
    def _escolher(self, resposta, nomes=("Salvar", "Abrir")):
        cliente = ClienteFalso(resposta)
        return EscolhedorBotao(cliente).escolher("gravar", list(nomes)), cliente

    def test_aceita_nome_da_lista(self):
        self.assertEqual(self._escolher('{"botao": "Salvar"}')[0], "Salvar")

    def test_nenhum_e_invalidos_viram_none(self):
        for resposta in ('{"botao": "nenhum"}', '{"botao": "Inventado"}', "lixo", "", "[]"):
            self.assertIsNone(self._escolher(resposta)[0], resposta)

    def test_ia_fora_do_ar_vira_none(self):
        self.assertIsNone(self._escolher(ConnectionError("fora do ar"))[0])

    def test_lista_vazia_nem_consulta(self):
        resultado, cliente = self._escolher('{"botao": "x"}', nomes=())
        self.assertIsNone(resultado)
        self.assertEqual(cliente.chamadas, [])

    def test_opcoes_vao_no_prompt_sem_repetir(self):
        _, cliente = self._escolher('{"botao": "Salvar"}', nomes=("Salvar", "Salvar", "Abrir"))
        texto = cliente.chamadas[0][0]["content"]
        self.assertEqual(texto.count("- Salvar"), 1)


class TestEscolherControle(unittest.TestCase):
    def test_exato_vence_os_parecidos(self):
        self.assertEqual(escolher_controle("salvar", BOTOES).nome, "Salvar")

    def test_sem_acento_e_maiusculas(self):
        self.assertEqual(escolher_controle("PAGINA INICIAL", BOTOES).nome, "Página inicial")

    def test_comeco_do_nome(self):
        self.assertEqual(escolher_controle("excluir", BOTOES).nome, "Excluir arquivo")

    def test_erro_de_transcricao(self):
        self.assertEqual(escolher_controle("imprimi", BOTOES).nome, "Imprimir")

    def test_empate_nunca_e_chutado(self):
        escolha = escolher_controle("sal", ["Salvar", "Salvar como"])
        self.assertIsNone(escolha.nome)
        self.assertEqual(escolha.opcoes, ["Salvar", "Salvar como"])

    def test_nomes_repetidos_sao_empate(self):
        escolha = escolher_controle("fechar", ["Fechar", "Fechar"])
        self.assertIsNone(escolha.nome)

    def test_nada_parecido(self):
        self.assertEqual(escolher_controle("zebra", BOTOES).opcoes, [])
        self.assertIsNone(escolher_controle("", BOTOES).nome)


class TestDesempate(unittest.TestCase):
    def test_spotify_o_play_do_player_vence_os_dos_cartoes(self):
        self.assertEqual(desempatar([5, 1, 1, 1, 1, 1, 1, 1, 1]), 0)
        self.assertEqual(desempatar([1, 1, 5, 1]), 2)

    def test_sem_vencedor_claro_nao_escolhe(self):
        self.assertIsNone(desempatar([1, 1, 1]))  # todos sozinhos
        self.assertIsNone(desempatar([4, 4, 1]))  # duas barras iguais
        self.assertIsNone(desempatar([]))


class TestPerigo(unittest.TestCase):
    def test_perigosos(self):
        for nome in ("Excluir", "Excluir arquivo", "Apagar tudo", "Enviar", "Enviar e-mail", "Comprar agora",
                     "Pagar", "Finalizar compra", "Desinstalar", "Não salvar", "Descartar alterações", "Delete",
                     "Send", "Publicar", "Confirmar pagamento", "Sair da conta", "Remover"):
            self.assertTrue(e_perigoso(nome), nome)

    def test_comuns(self):
        for nome in ("Salvar", "Abrir", "Imprimir", "Cancelar", "Voltar", "Página inicial", "Copiar", "Pesquisar",
                     "Sete", "Mais", "Igual a", "Configurações", "Ok", "Próximo", "Páginas", "Comprimir pasta"):
            self.assertFalse(e_perigoso(nome), nome)


class TestClicarBotao(unittest.TestCase):
    def setUp(self):
        self.sessao = Sessao(EstadoAssistente(), CanalFalso())
        self.escolhedor = EscolhedorFalso()
        self.acao = ClicarBotao(self.sessao, self.escolhedor)
        for alvo, valor in (("merlin.acoes.janelas.janela_em_uso", WORD),
                            ("merlin.acoes.janelas.listar_janelas", [WORD]),
                            ("merlin.acoes.controles.nomes_clicaveis", BOTOES)):
            p = mock.patch(alvo, return_value=valor)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("merlin.acoes.controles.clicar", return_value=ResultadoClique.CLICOU)
        self.clicar = p.start()
        self.addCleanup(p.stop)

    def _pedir(self, botao, programa=""):
        return self.acao(Intencao(TipoIntencao.CLICAR_BOTAO, botao, "x", programa))

    def test_botao_comum_clica_direto(self):
        r = self._pedir("imprimir")
        self.clicar.assert_called_once_with(WORD.hwnd, WORD.titulo, "Imprimir")
        self.assertEqual(r.fala, "cliquei em Imprimir")

    def test_botao_perigoso_pergunta_e_nao_clica(self):
        r = self._pedir("excluir")
        self.clicar.assert_not_called()
        self.assertIn("Excluir arquivo", r.fala)
        self.assertTrue(r.finaliza)
        self.assertTrue(self.sessao.tem_pendencia())

    def test_confirmacao_clica(self):
        self._pedir("enviar")
        r = self.sessao.pegar_pendencia().ao_confirmar()
        self.clicar.assert_called_once_with(WORD.hwnd, WORD.titulo, "Enviar")
        self.assertEqual(r.fala, "cliquei em Enviar")

    def test_empate_a_ia_escolhe_so_entre_os_empatados_e_pergunta(self):
        self.escolhedor.resposta = "Salvar como"
        r = self._pedir("sal")
        self.assertEqual(self.escolhedor.opcoes_recebidas, ["Salvar", "Salvar como"])
        self.clicar.assert_not_called()
        self.assertIn("Você quer que eu clique em Salvar como?", r.fala)

    def test_sinonimo_a_ia_escolhe_entre_todos_e_pergunta(self):
        self.escolhedor.resposta = "Salvar"
        r = self._pedir("gravar")
        self.assertEqual(self.escolhedor.opcoes_recebidas, BOTOES)
        self.clicar.assert_not_called()
        self.assertTrue(self.sessao.tem_pendencia())
        self.sessao.pegar_pendencia().ao_confirmar()
        self.clicar.assert_called_once_with(WORD.hwnd, WORD.titulo, "Salvar")

    def test_ia_sem_resposta_nao_clica(self):
        r = self._pedir("zebra")
        self.clicar.assert_not_called()
        self.assertFalse(self.sessao.tem_pendencia())
        self.assertIn("não encontrei o botão zebra", r.fala)

    def test_nome_exato_nem_consulta_a_ia(self):
        self._pedir("imprimir")
        self.assertIsNone(self.escolhedor.opcoes_recebidas)

    def test_botoes_repetidos_vao_para_o_desempate_sem_a_ia(self):
        with mock.patch("merlin.acoes.controles.nomes_clicaveis", return_value=["Play"] * 9):
            r = self._pedir("play")
        self.assertIsNone(self.escolhedor.opcoes_recebidas)
        self.clicar.assert_called_once_with(WORD.hwnd, WORD.titulo, "Play")
        self.assertEqual(r.fala, "cliquei em Play")

    def test_repetidos_sem_desempate_nao_clicam_e_explicam(self):
        self.clicar.return_value = ResultadoClique.AMBIGUO
        with mock.patch("merlin.acoes.controles.nomes_clicaveis", return_value=["Fechar", "Fechar"]):
            r = self._pedir("fechar")
        self.assertIn("não consegui saber qual", r.fala)

    def test_repetidos_perigosos_ainda_pedem_confirmacao(self):
        with mock.patch("merlin.acoes.controles.nomes_clicaveis", return_value=["Excluir", "Excluir"]):
            self._pedir("excluir")
        self.clicar.assert_not_called()
        self.assertTrue(self.sessao.tem_pendencia())

    def test_programa_citado_e_fechado(self):
        r = self._pedir("salvar", "excel")
        self.clicar.assert_not_called()
        self.assertIn("não encontrei a janela", r.fala)

    def test_clique_que_falha_e_avisado(self):
        self.clicar.return_value = ResultadoClique.FALHOU
        self.assertIn("não consegui clicar", self._pedir("imprimir").fala)

    def test_botao_que_sumiu_e_avisado(self):
        self.clicar.return_value = ResultadoClique.SUMIU
        self.assertIn("não está mais na tela", self._pedir("imprimir").fala)


class TestSoClicaComOrdem(unittest.TestCase):
    def _tipo(self, comando):
        import json
        from merlin.ia.intencoes import ClassificadorIntencao
        from tests.falsos import ClienteFalso
        resposta = json.dumps({"alvo": "salvar", "intencao": "clicar_botao", "busca": "", "local": ""})
        return ClassificadorIntencao(ClienteFalso(resposta)).classificar(comando).tipo

    def test_ordens_clicam(self):
        for frase in ("clica no botão salvar", "clica em ok", "aperta o botão de enviar", "pressiona cancelar",
                      "clique em salvar", "dá um clique no botão próximo", "aperta o sete", "por favor clica em salvar",
                      "seleciona a aba inicio", "toca em salvar", "marca a caixa lembrar"):
            self.assertIs(self._tipo(frase), TipoIntencao.CLICAR_BOTAO, frase)

    def test_perguntas_nunca_clicam(self):
        for frase in ("o que acontece se eu clicar em salvar", "como eu clico com o botão direito",
                      "qual botão eu aperto", "devo clicar em salvar", "posso apertar enviar", "quero saber onde clicar"):
            self.assertIs(self._tipo(frase), TipoIntencao.CONVERSAR, frase)


class TestConfirmacaoPeloProcessador(unittest.TestCase):
    def test_sim_clica_e_fala_o_resultado(self):
        estado = EstadoAssistente()
        sessao, locutor = Sessao(estado, CanalFalso()), LocutorFalso()
        processador = ProcessadorComandos(estado, sessao, CanalFalso(), locutor, DivisorFalso(), ClassificadorFalso(),
                                          ConfirmadorFalso(RespostaConfirmacao.SIM), SaudacaoFalsa(), {})
        sessao.ativar()
        from merlin.nucleo.resposta import Resultado
        from merlin.nucleo.sessao import Pendencia
        sessao.aguardar_confirmacao(Pendencia("Posso?", lambda: Resultado("cliquei em Enviar"), "Não cliquei.", time.time() + 20))
        processador.processar("pode")
        self.assertEqual(locutor.falas, ["Cliquei em Enviar."])


if __name__ == "__main__":
    unittest.main()
