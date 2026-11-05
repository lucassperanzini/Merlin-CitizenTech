import time
import unittest

from merlin.estado import EstadoAssistente
from merlin.ia.confirmacao import RespostaConfirmacao
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.resposta import Resultado, montar_resposta
from merlin.nucleo.sessao import Pendencia, Sessao
from merlin.nucleo.trabalhador import TrabalhadorComandos
from tests.falsos import CanalFalso, ClassificadorFalso, ConfirmadorFalso, DivisorFalso, LocutorFalso, SaudacaoFalsa


class Base(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoAssistente()
        self.canal = CanalFalso()
        self.sessao = Sessao(self.estado, self.canal)
        self.locutor = LocutorFalso()
        self.classificador = ClassificadorFalso(Intencao(TipoIntencao.CONVERSAR, "", "x"))
        self.confirmador = ConfirmadorFalso()
        self.divisor = DivisorFalso()
        self.executadas = []
        acoes = {tipo: self._acao(tipo) for tipo in TipoIntencao}
        self.processador = ProcessadorComandos(
            self.estado, self.sessao, self.canal, self.locutor, self.divisor, self.classificador,
            self.confirmador, SaudacaoFalsa(), acoes,
        )
        self.confirmou = []

    def _acao(self, tipo):
        def acao(intencao):
            self.executadas.append(tipo)
            return Resultado(f"fiz {tipo.value}")

        return acao

    def _pendencia(self, expira_em=None):
        return Pendencia("Posso?", lambda: self.confirmou.append(True), "Tudo bem.", expira_em or time.time() + 20)


class TestAtivacao(Base):
    def test_em_espera_sem_o_nome_ignora(self):
        self.processador.processar("qual a capital da itália")
        self.assertFalse(self.estado.ativo.is_set())
        self.assertEqual(self.classificador.comandos, [])
        self.assertEqual(self.locutor.falas, [])

    def test_so_o_nome_ativa_e_sauda(self):
        self.processador.processar("merlin")
        self.assertTrue(self.estado.ativo.is_set())
        self.assertIn("mostrar", self.canal.eventos)
        self.assertEqual(self.locutor.falas, ["saudação"])

    def test_nome_com_ativo_responde_pois_nao(self):
        self.sessao.ativar()
        self.processador.processar("merlin")
        self.assertEqual(self.locutor.falas, ["Pois não?"])

    def test_nome_junto_com_pedido_vai_direto(self):
        self.processador.processar("merlin, abre o chrome")
        self.assertEqual(self.classificador.comandos, ["abre o chrome"])
        self.assertNotIn("saudação", self.locutor.falas)

    def test_ativo_nao_precisa_do_nome(self):
        self.sessao.ativar()
        self.processador.processar("abre o chrome")
        self.assertEqual(self.classificador.comandos, ["abre o chrome"])


class TestSomDeAtivacao(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoAssistente()
        self.tocadas = []
        self.sessao = Sessao(self.estado, CanalFalso(), self)

    def tocar(self):
        self.tocadas.append(True)

    def test_toca_ao_ativar(self):
        self.sessao.ativar()
        self.assertEqual(len(self.tocadas), 1)

    def test_nao_repete_se_ja_estiver_ativo(self):
        self.sessao.ativar()
        self.sessao.ativar()
        self.assertEqual(len(self.tocadas), 1)

    def test_toca_de_novo_depois_de_desativar(self):
        self.sessao.ativar()
        self.sessao.desativar()
        self.sessao.ativar()
        self.assertEqual(len(self.tocadas), 2)

    def test_microfone_fica_mudo_so_durante_o_tempo_pedido(self):
        self.assertFalse(self.estado.microfone_mudo())
        self.estado.silenciar_microfone(0.05)
        self.assertTrue(self.estado.microfone_mudo())
        time.sleep(0.07)
        self.assertFalse(self.estado.microfone_mudo())


class TestRoteamento(Base):
    def test_cada_intencao_vai_para_a_sua_acao(self):
        self.sessao.ativar()
        for tipo in TipoIntencao:
            self.classificador.intencao = Intencao(tipo, "alvo", "x")
            self.processador.processar("frase")
        self.assertEqual(self.executadas, list(TipoIntencao))

    def test_falha_da_ia_vira_aviso_falado(self):
        self.sessao.ativar()
        self.classificador.erro = ConnectionError("fora do ar")
        self.processador.processar("frase")
        self.assertIn("Ollama", self.locutor.falas[0])


class TestVariasTarefas(Base):
    def setUp(self):
        super().setUp()
        self.classificador.intencao = Intencao(TipoIntencao.ABRIR_PROGRAMA, "x", "x")
        self.sessao.ativar()
        self.divisor.tarefas = ["abre o chrome", "fecha o telegram", "pesquisa gatos"]
        self.feitas = []

    def _acoes(self, *resultados):
        """Cada chamada devolve o próximo resultado da lista."""
        fila = list(resultados)

        def acao(intencao):
            self.feitas.append(intencao)
            item = fila.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        self.processador._acoes = {tipo: acao for tipo in TipoIntencao}

    def test_uma_unica_resposta_depois_de_tudo(self):
        self._acoes(Resultado("abri o chrome"), Resultado("fechei o telegram"), Resultado("pesquisei por gatos"))
        self.processador.processar("frase longa")
        self.assertEqual(self.locutor.falas, ["Abri o chrome, fechei o telegram e pesquisei por gatos."])
        self.assertEqual(self.classificador.comandos, ["abre o chrome", "fecha o telegram", "pesquisa gatos"])

    def test_limite_avisa_e_faz_so_as_primeiras(self):
        self.divisor.tarefas = [f"tarefa {i}" for i in range(5)]
        self._acoes(*[Resultado("feito") for _ in range(3)])
        self.processador.processar("frase longa")
        self.assertEqual(len(self.classificador.comandos), 3)
        self.assertIn("3 primeiras", self.locutor.falas[0])
        self.assertEqual(len(self.locutor.falas), 1)

    def test_finaliza_cancela_o_resto(self):
        self._acoes(Resultado("Até mais.", frase_completa=True, finaliza=True))
        self.processador.processar("frase longa")
        self.assertEqual(len(self.feitas), 1)  # todas foram entendidas, mas só a primeira foi executada

    def test_depois_roda_so_depois_de_falar(self):
        ordem = []
        self.locutor.falar = lambda texto: ordem.append("falou")
        self._acoes(Resultado("Até mais.", frase_completa=True, depois=lambda: ordem.append("escondeu"), finaliza=True))
        self.processador.processar("frase longa")
        self.assertEqual(ordem, ["falou", "escondeu"])

    def test_falha_no_meio_mantem_o_que_ja_foi_feito(self):
        self._acoes(Resultado("abri o chrome"), ConnectionError("fora do ar"))
        self.processador.processar("frase longa")
        self.assertEqual(len(self.locutor.falas), 1)
        self.assertIn("Abri o chrome.", self.locutor.falas[0])
        self.assertIn("Ollama", self.locutor.falas[0])

    def test_falha_ao_dividir_avisa(self):
        class Quebrado:
            def dividir(self, _comando):
                raise ConnectionError("fora do ar")

        self.processador._divisor = Quebrado()
        self.processador.processar("frase longa")
        self.assertIn("Ollama", self.locutor.falas[0])


class ClassificadorPorFrase:
    def __init__(self, tipos):
        self.tipos = tipos
        self.comandos = []

    def classificar(self, comando):
        self.comandos.append(comando)
        return Intencao(self.tipos.get(comando, TipoIntencao.CONVERSAR), comando, comando)


class TestSoSeparaComAcao(Base):
    def setUp(self):
        super().setUp()
        self.sessao.ativar()

    def _processar(self, partes, tipos):
        self.divisor.tarefas = partes
        self.processador._classificador = ClassificadorPorFrase(tipos)
        self.processador.processar("frase inteira")
        return self.processador._classificador.comandos

    def test_conversa_e_despedida_juntas_viram_uma_frase_so(self):
        comandos = self._processar(["fala aí", "tudo bem"], {"tudo bem": TipoIntencao.DISPENSAR})
        self.assertEqual(comandos, ["fala aí", "tudo bem", "frase inteira"])
        self.assertEqual(self.executadas, [TipoIntencao.CONVERSAR])
        self.assertTrue(self.estado.ativo.is_set())

    def test_com_uma_acao_separa(self):
        self._processar(["fecha o chrome", "pode ir"], {"fecha o chrome": TipoIntencao.FECHAR_PROGRAMA,
                                                        "pode ir": TipoIntencao.DISPENSAR})
        self.assertEqual(self.executadas, [TipoIntencao.FECHAR_PROGRAMA, TipoIntencao.DISPENSAR])

    def test_pergunta_e_acao_separam(self):
        self._processar(["qual a capital", "abre o chrome"], {"abre o chrome": TipoIntencao.ABRIR_PROGRAMA})
        self.assertEqual(self.executadas, [TipoIntencao.CONVERSAR, TipoIntencao.ABRIR_PROGRAMA])


class TestMontarResposta(unittest.TestCase):
    def test_uma_acao(self):
        self.assertEqual(montar_resposta([Resultado("abri o chrome")]), "Abri o chrome.")

    def test_duas_acoes_como_no_pedido(self):
        r = [Resultado("abri o chrome"), Resultado("fechei o telegram")]
        self.assertEqual(montar_resposta(r), "Abri o chrome e fechei o telegram.")

    def test_tres_acoes(self):
        r = [Resultado("abri a"), Resultado("fechei b"), Resultado("criei c")]
        self.assertEqual(montar_resposta(r), "Abri a, fechei b e criei c.")

    def test_sucesso_e_falha_juntos(self):
        r = [Resultado("abri o chrome"), Resultado("não encontrei telegram aberto")]
        self.assertEqual(montar_resposta(r), "Abri o chrome e não encontrei telegram aberto.")

    def test_frase_completa_nao_se_junta(self):
        r = [Resultado("A capital é Roma.", frase_completa=True), Resultado("abri o chrome"), Resultado("fechei o word")]
        self.assertEqual(montar_resposta(r), "A capital é Roma. Abri o chrome e fechei o word.")

    def test_acao_depois_de_frase_completa_recomeca_maiuscula(self):
        r = [Resultado("abri o chrome"), Resultado("Roma.", frase_completa=True), Resultado("fechei o word")]
        self.assertEqual(montar_resposta(r), "Abri o chrome. Roma. Fechei o word.")

    def test_duas_respostas_da_ia(self):
        r = [Resultado("Roma.", frase_completa=True), Resultado("Quatro.", frase_completa=True)]
        self.assertEqual(montar_resposta(r), "Roma. Quatro.")


class TestConfirmacao(Base):
    def setUp(self):
        super().setUp()
        self.sessao.ativar()

    def test_sim_executa_e_nao_passa_pelo_classificador(self):
        self.confirmador.resposta = RespostaConfirmacao.SIM
        self.sessao.aguardar_confirmacao(self._pendencia())
        self.processador.processar("pode")
        self.assertEqual(self.confirmou, [True])
        self.assertEqual(self.classificador.comandos, [])

    def test_nao_recusa_sem_agir(self):
        self.confirmador.resposta = RespostaConfirmacao.NAO
        self.sessao.aguardar_confirmacao(self._pendencia())
        self.processador.processar("melhor não")
        self.assertEqual(self.confirmou, [])
        self.assertEqual(self.locutor.falas, ["Tudo bem."])

    def test_outro_assunto_cancela_e_atende_o_pedido(self):
        self.sessao.aguardar_confirmacao(self._pendencia())
        self.processador.processar("quanto é dois mais dois")
        self.assertEqual(self.confirmou, [])
        self.assertFalse(self.sessao.tem_pendencia())
        self.assertEqual(self.classificador.comandos, ["quanto é dois mais dois"])

    def test_resposta_depois_do_prazo_nao_executa(self):
        self.confirmador.resposta = RespostaConfirmacao.SIM
        self.sessao.aguardar_confirmacao(self._pendencia(expira_em=time.time() - 1))
        self.processador.processar("pode")
        self.assertEqual(self.confirmou, [])

    def test_so_o_nome_cancela_a_pergunta(self):
        self.confirmador.resposta = RespostaConfirmacao.SIM
        self.sessao.aguardar_confirmacao(self._pendencia())
        self.processador.processar("merlin")
        self.processador.processar("pode")
        self.assertEqual(self.confirmou, [])

    def test_desativar_cancela_a_pergunta(self):
        self.sessao.aguardar_confirmacao(self._pendencia())
        self.sessao.desativar()
        self.assertFalse(self.sessao.tem_pendencia())
        self.assertIn("esconder", self.canal.eventos)


class TestTrabalhador(Base):
    def test_erro_em_um_comando_nao_para_o_atendimento(self):
        class Quebrado:
            def processar(self, _frase):
                raise RuntimeError("falha")

        trabalhador = TrabalhadorComandos(self.estado, self.sessao, self.canal, Quebrado())
        self.sessao.ativar()
        trabalhador._atender("frase")
        self.assertEqual(self.canal.eventos[-1], "ouvindo")

    def test_inatividade_volta_para_a_espera(self):
        trabalhador = TrabalhadorComandos(self.estado, self.sessao, self.canal, self.processador)
        self.sessao.ativar()
        self.estado._ultima_atividade = time.time() - 1000
        trabalhador._verificar_inatividade()
        self.assertFalse(self.estado.ativo.is_set())

    def test_nao_desativa_enquanto_fala(self):
        trabalhador = TrabalhadorComandos(self.estado, self.sessao, self.canal, self.processador)
        self.sessao.ativar()
        self.estado.falando.set()
        self.estado._ultima_atividade = time.time() - 1000
        trabalhador._verificar_inatividade()
        self.assertTrue(self.estado.ativo.is_set())


if __name__ == "__main__":
    unittest.main()
