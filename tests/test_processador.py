import time
import unittest

from merlin.estado import EstadoAssistente
from merlin.ia.confirmacao import RespostaConfirmacao
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.sessao import Pendencia, Sessao
from merlin.nucleo.trabalhador import TrabalhadorComandos
from tests.falsos import CanalFalso, ClassificadorFalso, ConfirmadorFalso, LocutorFalso, SaudacaoFalsa


class Base(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoAssistente()
        self.canal = CanalFalso()
        self.sessao = Sessao(self.estado, self.canal)
        self.locutor = LocutorFalso()
        self.classificador = ClassificadorFalso(Intencao(TipoIntencao.CONVERSAR, "", "x"))
        self.confirmador = ConfirmadorFalso()
        self.executadas = []
        acoes = {tipo: self._acao(tipo) for tipo in TipoIntencao}
        self.processador = ProcessadorComandos(
            self.estado, self.sessao, self.canal, self.locutor, self.classificador,
            self.confirmador, SaudacaoFalsa(), acoes,
        )
        self.confirmou = []

    def _acao(self, tipo):
        return lambda intencao: self.executadas.append(tipo)

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
        self.assertEqual(self.locutor.falas, [])

    def test_ativo_nao_precisa_do_nome(self):
        self.sessao.ativar()
        self.processador.processar("abre o chrome")
        self.assertEqual(self.classificador.comandos, ["abre o chrome"])


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
