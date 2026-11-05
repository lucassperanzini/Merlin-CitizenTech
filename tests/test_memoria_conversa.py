import unittest

from merlin.estado import EstadoAssistente
from merlin.ia.conversa import Conversa
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.memoria_conversa import MemoriaConversa
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.resposta import Resultado
from merlin.nucleo.sessao import Sessao
from tests.falsos import CanalFalso, ClassificadorFalso, ClienteFalso, ConfirmadorFalso, DivisorFalso, LocutorFalso, SaudacaoFalsa


class TestMemoria(unittest.TestCase):
    def test_guarda_em_ordem_como_conversa(self):
        m = MemoriaConversa()
        m.registrar("qual a capital da frança", "Paris.")
        m.registrar("e a da itália", "Roma.")
        self.assertEqual(m.como_mensagens(), [
            {"role": "user", "content": "qual a capital da frança"}, {"role": "assistant", "content": "Paris."},
            {"role": "user", "content": "e a da itália"}, {"role": "assistant", "content": "Roma."},
        ])

    def test_esquece_as_mais_antigas(self):
        m = MemoriaConversa(limite=2)
        for i in range(5):
            m.registrar(f"pergunta {i}", f"resposta {i}")
        self.assertEqual([x["content"] for x in m.como_mensagens()], ["pergunta 3", "resposta 3", "pergunta 4", "resposta 4"])

    def test_limite_zero_nao_lembra_nada(self):
        m = MemoriaConversa(limite=0)
        m.registrar("meu nome é Lucas", "Olá, Lucas!")
        self.assertEqual(m.como_mensagens(), [])

    def test_limpar(self):
        m = MemoriaConversa()
        m.registrar("a", "b")
        m.limpar()
        self.assertEqual(m.como_mensagens(), [])

    def test_ignora_vazios_e_corta_textos_longos(self):
        m = MemoriaConversa()
        m.registrar("", "b")
        m.registrar("a", "  ")
        m.registrar("a", "x" * 5000)
        mensagens = m.como_mensagens()
        self.assertEqual(len(mensagens), 2)
        self.assertLessEqual(len(mensagens[1]["content"]), 500)


class TestUsoDaMemoria(unittest.TestCase):
    def setUp(self):
        self.memoria = MemoriaConversa()
        self.estado = EstadoAssistente()
        self.sessao = Sessao(self.estado, CanalFalso(), memoria=self.memoria)
        self.locutor = LocutorFalso()
        self.classificador = ClassificadorFalso(Intencao(TipoIntencao.CONVERSAR, "", "x"))
        acoes = {tipo: (lambda i: Resultado("Roma.", frase_completa=True)) for tipo in TipoIntencao}
        self.processador = ProcessadorComandos(self.estado, self.sessao, CanalFalso(), self.locutor, DivisorFalso(),
                                               self.classificador, ConfirmadorFalso(), SaudacaoFalsa(), acoes, self.memoria)
        self.sessao.ativar()

    def test_processador_registra_pergunta_sem_o_nome_e_a_resposta_falada(self):
        self.processador.processar("merlin, e a da itália")
        self.assertEqual(self.memoria.como_mensagens(), [
            {"role": "user", "content": "e a da itália"}, {"role": "assistant", "content": "Roma."},
        ])

    def test_saudacao_nao_entra_na_memoria(self):
        self.sessao.desativar()
        self.processador.processar("merlin")
        self.assertEqual(self.memoria.como_mensagens(), [])

    def test_desativar_comeca_conversa_nova(self):
        self.processador.processar("e a da itália")
        self.sessao.desativar()
        self.assertEqual(self.memoria.como_mensagens(), [])

    def test_conversa_envia_o_historico_antes_da_pergunta(self):
        self.memoria.registrar("qual a capital da frança", "Paris.")
        cliente = ClienteFalso("Roma.")
        Conversa(cliente, self.memoria).responder("e a da itália")
        mensagens = cliente.chamadas[0]
        self.assertEqual(mensagens[0]["role"], "system")
        self.assertEqual([m["content"] for m in mensagens[1:]], ["qual a capital da frança", "Paris.", "e a da itália"])


if __name__ == "__main__":
    unittest.main()
