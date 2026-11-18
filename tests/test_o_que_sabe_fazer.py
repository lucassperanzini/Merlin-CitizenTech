"""A conversa sabe o que o assistente faz de verdade, e uma pergunta sobre ele não vai para os protocolos."""
import unittest

from merlin import habilidades as registro
from merlin.estado import EstadoAssistente
from merlin.habilidades import HABILIDADES
from merlin.ia.conversa import (NAO_SEI_FAZER, PEDIDO_SEM_SKILL, PERGUNTA_SOBRE_CAPACIDADES, Conversa,
                                instrucoes_da_conversa, o_que_sabe_fazer, sem_promessas_falsas)
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.memoria_conversa import MemoriaConversa
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.resposta import Resultado
from merlin.nucleo.sessao import Sessao
from merlin.personalidades import personalidade_padrao
from tests.falsos import (CanalFalso, ClassificadorFalso, ClienteFalso, ConfirmadorFalso, DivisorFalso, LocutorFalso,
                          SaudacaoFalsa)


class TestOQueSabeFazer(unittest.TestCase):
    def test_lista_as_skills_e_proibe_inventar(self):
        texto = o_que_sabe_fazer(HABILIDADES)
        for h in HABILIDADES:
            self.assertIn(h.titulo_legivel.lower(), texto)
        self.assertIn("não acrescente o que você não faz", texto)  # ao contar o que sabe, não lista o que não sabe
        self.assertIn("não ofereça alternativas", texto)

    def test_vai_nas_instrucoes_da_conversa_por_ultimo(self):
        texto = instrucoes_da_conversa(personalidade_padrao(), habilidades=HABILIDADES)
        self.assertTrue(texto.endswith(o_que_sabe_fazer(HABILIDADES)))

    def test_skill_desligada_sai_da_lista(self):
        ligadas = [h for h in HABILIDADES if h.nome != "abrir_pasta"]
        self.assertNotIn("abrir pasta", o_que_sabe_fazer(ligadas))

    def test_sem_lista_usa_as_skills_ligadas(self):
        self.assertEqual(o_que_sabe_fazer(), o_que_sabe_fazer(registro.ativas()))


class TestNaoFingeFazer(unittest.TestCase):
    """A conversa não executa nada: ela nunca pode dizer que fez nem oferecer o que não existe."""

    def test_pedido_de_acao_sem_skill_nem_chega_a_ia(self):
        cliente = ClienteFalso("Já estou marcando o horário, senhor.")
        conversa = Conversa(cliente, MemoriaConversa())
        for pedido in ("me lembra de tomar remédio às 8", "marca uma reunião amanhã", "manda uma mensagem pro joão",
                       "liga pra minha mãe", "põe um alarme às 7", "toca uma música animada"):
            with self.subTest(pedido):
                self.assertEqual(conversa.responder(pedido), NAO_SEI_FAZER)
        self.assertEqual(cliente.chamadas, [])

    def test_pergunta_parecida_continua_conversa(self):
        for frase in ("me lembra qual foi a pergunta", "como marcar uma consulta no sus", "o que é um lembrete",
                      "como funciona um alarme de incêndio"):
            with self.subTest(frase):
                self.assertIsNone(PEDIDO_SEM_SKILL.match(frase))

    def test_resposta_que_finge_ter_feito_vira_nao_sei_fazer(self):
        # Respostas reais do qwen3:4b-instruct a "me lembra de tomar remédio às 8"
        for mentira in ("Senhor, já tenho registrado sua lembrança. Às 8, o assistente irá tocar um sinal suave.",
                        "Senhor, vou registra isso nos protocolos de rotina. Às 8h, tome o seu remédio.",
                        "Senhor, com prazer. Eu me encarrego disso — já estou marcando o horário para as 8h."):
            with self.subTest(mentira):
                self.assertEqual(sem_promessas_falsas(mentira), NAO_SEI_FAZER)

    def test_oferta_falsa_sai_e_a_recusa_fica(self):
        resposta = "Senhor, infelizmente não posso organizar agendas. Mas posso ajudar a criar eventos ou lembrar datas."
        self.assertEqual(sem_promessas_falsas(resposta), "Senhor, infelizmente não posso organizar agendas.")

    def test_resposta_comum_nao_muda(self):
        for resposta in ("Senhor, a capital da França é Paris. Pode deixar que eu explico mais se quiser.",
                         "Eu posso abrir programas, pastas ou configurações e consultar os protocolos de incêndio.",
                         "Certo. Sete vezes oito é cinquenta e seis."):
            with self.subTest(resposta):
                self.assertEqual(sem_promessas_falsas(resposta), resposta)


class TestSemRessalvas(unittest.TestCase):
    def test_lista_de_capacidades_sai_sem_o_que_ele_nao_faz(self):
        # Resposta real do qwen3:4b-instruct a "quais as suas capacidades"
        resposta = ("Minhas capacidades incluem abrir programas e consultar os protocolos de combate a incêndios. "
                    "Não posso realizar ações diretas no sistema ou operar equipamentos físicos.")
        conversa = Conversa(ClienteFalso(resposta), MemoriaConversa())
        self.assertEqual(conversa.responder("quais as suas capacidades"),
                         "Minhas capacidades incluem abrir programas e consultar os protocolos de combate a incêndios.")

    def test_recusa_continua_quando_nao_e_pergunta_sobre_ele(self):
        resposta = "Infelizmente não posso organizar agendas. Não tenho acesso ao seu calendário."
        self.assertEqual(Conversa(ClienteFalso(resposta), MemoriaConversa()).responder("organiza minha agenda?"), resposta)

    def test_so_pergunta_dirigida_ao_assistente(self):
        for frase in ("quais as suas capacidades", "o que você sabe fazer?", "pra que você serve", "quais são suas funções"):
            with self.subTest(frase):
                self.assertTrue(PERGUNTA_SOBRE_CAPACIDADES.search(frase))
        self.assertIsNone(PERGUNTA_SOBRE_CAPACIDADES.search("qual a função do comandante do incidente"))


class EspecialistaQueSempreAcha:
    """A busca acha um trecho parecido para qualquer frase: só a regra do processador decide."""

    nome = "falso"

    def parece_protocolo(self, pergunta):
        return True


class TestPerguntaSobreOAssistente(unittest.TestCase):
    def setUp(self):
        estado, canal = EstadoAssistente(), CanalFalso()
        self.sessao = Sessao(estado, canal)
        self.feitas = []

        def anotar(tipo):
            return lambda i: self.feitas.append(tipo) or Resultado("ok", frase_completa=True)
        self.anotar = anotar
        self.estado, self.canal = estado, canal

    def processar(self, frase, alvo=""):
        processador = ProcessadorComandos(
            self.estado, self.sessao, self.canal, LocutorFalso(), DivisorFalso(),
            ClassificadorFalso(Intencao(TipoIntencao.CONVERSAR, alvo, frase)), ConfirmadorFalso(), SaudacaoFalsa(),
            {t: self.anotar(t) for t in TipoIntencao}, especialista=EspecialistaQueSempreAcha())
        self.sessao.ativar()
        processador.processar(frase)
        return self.feitas[-1]

    def test_pergunta_ao_assistente_fica_na_conversa(self):
        # "quais as suas capacidades" teve nota 0,837 na busca, para um limite de 0,836
        for frase in ("quais as suas capacidades", "o que você sabe fazer", "qual o seu nome"):
            with self.subTest(frase):
                self.assertEqual(self.processar(frase), TipoIntencao.CONVERSAR)

    def test_alvo_e_o_proprio_assistente(self):
        self.assertEqual(self.processar("me fala das capacidades do merlin", alvo="merlin"), TipoIntencao.CONVERSAR)

    def test_pergunta_sobre_o_assunto_ainda_vai_aos_protocolos(self):
        self.assertEqual(self.processar("e se o vento virar"), TipoIntencao.CONSULTAR_PROTOCOLO)


if __name__ == "__main__":
    unittest.main()
