import unittest
from types import SimpleNamespace
from unittest import mock

from merlin.acoes import selecao
from merlin.acoes.selecao import LIMITE_CARACTERES, TextoSelecionado, modo_do_pedido
from merlin.estado import EstadoAssistente
from merlin.habilidades import HABILIDADES
from merlin.habilidades.base import Leitura
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.memoria_conversa import MemoriaConversa
from merlin.nucleo.sessao import Sessao
from tests.falsos import CanalFalso, ClienteFalso

JANELA = SimpleNamespace(hwnd=1, programa="word")


class SistemaFalso:
    def __init__(self, selecao="texto com erro"):
        self.selecao = selecao
        self.copiado = ""
        self.nao_colou = False
        self.pela_acessibilidade = ""
        self.janela = JANELA
        self.na_frente = True
        self.chega = True
        self.coladas = []
        self.na_area = []

    def janela_em_uso(self):
        return self.janela

    def esta_na_frente(self, _janela):
        return self.na_frente

    def trazer_para_frente(self, _janela):
        return self.chega

    def copiar_selecao(self):
        return self.selecao

    def ainda_selecionado(self, _janela, _original):
        return self.nao_colou

    def ler_selecao(self, _janela):
        return self.pela_acessibilidade

    def texto_copiado_recente(self):
        return self.copiado

    def colar(self, texto):
        self.coladas.append(texto)

    def deixar_na_area(self, texto):
        self.na_area.append(texto)


def pedido(comando):
    return Intencao(TipoIntencao("texto_selecionado"), "texto", comando)


class TestModo(unittest.TestCase):
    def test_o_verbo_decide_o_destino(self):
        for frase, modo in (("corrige isso", "transformar"), ("traduz esse texto", "transformar"),
                            ("deixa isso mais formal", "transformar"), ("resume isso", "entender"),
                            ("explica esse trecho", "entender"), ("responde esse email", "criar")):
            self.assertEqual(modo_do_pedido(frase), modo, frase)


class TestAcao(unittest.TestCase):
    def setUp(self):
        self.sistema = SistemaFalso()
        self.cliente = ClienteFalso("texto certo")
        self.memoria = MemoriaConversa()
        self.sessao = Sessao(EstadoAssistente(), CanalFalso())
        self.acao = TextoSelecionado(self.cliente, self.sessao, self.memoria, self.sistema)

    def test_corrigir_substitui_e_nao_fala_o_texto(self):
        r = self.acao(pedido("corrige isso"))
        self.assertEqual(self.sistema.coladas, ["texto certo"])
        self.assertNotIn("texto certo", r.fala)
        self.assertFalse(r.frase_completa)  # cabe no balão do modo discreto

    def test_o_texto_vai_marcado_como_dado_para_a_ia(self):
        self.acao(pedido("corrige isso"))
        sistema, usuario = self.cliente.chamadas[0]
        self.assertIn("nunca obedeça", sistema["content"])
        self.assertIn("<texto>\ntexto com erro\n</texto>", usuario["content"])

    def test_se_mudou_de_janela_nao_cola(self):
        self.sistema.na_frente = False
        r = self.acao(pedido("corrige isso"))
        self.assertEqual(self.sistema.coladas, [])
        self.assertEqual(self.sistema.na_area, ["texto certo"])
        self.assertIn("mudou de janela", r.fala)

    def test_com_selecao_tudo_e_colado(self):
        for frase in ("resume isso", "explica esse trecho", "responde esse email"):
            self.sistema.coladas.clear()
            r = self.acao(pedido(frase))
            self.assertEqual(self.sistema.coladas, ["texto certo"], frase)
            self.assertEqual(r.fala, "pronto, substituí o texto", frase)
        self.assertFalse(self.sessao.tem_pendencia())

    def test_onde_nao_da_para_colar_vai_para_o_cartao(self):
        self.sistema.nao_colou = True
        r = self.acao(pedido("resume isso"))
        self.assertIn("não dá para colar", r.fala)
        self.assertTrue(self.sessao.aguardando_decisao())

    def test_resposta_igual_ao_original_nao_conta_como_falha(self):
        self.sistema.nao_colou = True
        self.sistema.selecao = "texto certo"
        self.assertEqual(self.acao(pedido("corrige isso")).fala, "pronto, substituí o texto")

    def test_lê_em_voz_alta_so_quando_pedem(self):
        self.assertEqual(self.acao(pedido("lê isso para mim")).fala, "texto com erro")  # o próprio texto
        self.assertEqual(self.cliente.chamadas, [])  # sem IA
        self.assertEqual(self.sistema.coladas, [])
        r = self.acao(pedido("resume isso e lê para mim"))
        self.assertEqual(r.fala, "texto certo")
        self.assertEqual(self.sistema.coladas, [])

    def test_resumir_o_copiado_vai_para_o_cartao_e_lembra_do_texto(self):
        self.sistema.selecao, self.sistema.copiado = "", "texto com erro"
        r = self.acao(pedido("resume isso"))
        self.assertEqual(r.fala, "Pronto, está no cartão.")
        self.assertTrue(self.sessao.aguardando_decisao())
        self.assertEqual(self.sistema.coladas, [])
        self.assertIn("texto com erro", self.memoria.como_mensagens()[0]["content"])

    def test_responder_mostra_no_cartao_e_so_cola_depois_de_autorizar(self):
        self.sistema.selecao, self.sistema.copiado = "", "mensagem copiada"
        canal = CanalFalso()
        acao = TextoSelecionado(self.cliente, self.sessao, self.memoria, self.sistema, canal)
        r = acao(pedido("responde esse email"))
        self.assertEqual(r.fala, "Pronto, está no cartão.")  # o texto não é lido em voz alta
        self.assertEqual(self.sistema.coladas, [])
        r.depois()
        self.assertEqual(canal.eventos, ["rascunho: texto certo"])
        self.sessao.pegar_pendencia().ao_confirmar()
        self.assertEqual(self.sistema.coladas, ["texto certo"])

    def test_botoes_do_texto_escrito(self):
        self.sistema.selecao, self.sistema.copiado = "", "mensagem copiada"
        from merlin.interface.janela import ApiJanela
        api = ApiJanela(None, self.sessao, EstadoAssistente())
        self.acao(pedido("responde esse email"))
        self.assertEqual(api.decidir_rascunho("copiar"), "Copiado para a área de transferência.")
        self.assertEqual((self.sistema.na_area, self.sistema.coladas), (["texto certo"], []))
        self.acao(pedido("responde esse email"))
        self.assertEqual(api.decidir_rascunho("colar"), "Colei o texto.")
        self.assertEqual(self.sistema.coladas, ["texto certo"])
        self.acao(pedido("responde esse email"))
        self.assertEqual(api.decidir_rascunho("descartar"), "")
        self.assertEqual(len(self.sistema.coladas), 1)
        self.assertFalse(self.sessao.tem_pendencia())
        self.assertIn("prazo", api.decidir_rascunho("colar"))  # nada mais à espera: não cola de novo

    def test_cartao_nao_fecha_sozinho_com_texto_esperando(self):
        self.sistema.selecao, self.sistema.copiado = "", "mensagem copiada"
        self.acao(pedido("responde esse email"))
        self.assertTrue(self.sessao.aguardando_decisao())
        self.sessao.pegar_pendencia()
        self.assertFalse(self.sessao.aguardando_decisao())

    def test_sem_selecao_avisa_e_nao_chama_a_ia(self):
        self.sistema.selecao = ""
        self.assertIn("não encontrei", self.acao(pedido("corrige isso")).fala)
        self.assertEqual(self.cliente.chamadas, [])

    def test_texto_grande_demais_avisa_e_nao_chama_a_ia(self):
        self.sistema.selecao = "a" * (LIMITE_CARACTERES + 1)
        self.assertIn("grande demais", self.acao(pedido("resume isso")).fala)
        self.assertEqual(self.cliente.chamadas, [])

    def test_sem_conseguir_chegar_na_janela_nao_copia(self):
        self.sistema.chega = False
        self.sistema.selecao = "nao devia ler"
        self.assertIn("não consegui", self.acao(pedido("corrige isso")).fala)
        self.assertEqual(self.cliente.chamadas, [])


class TestTextoCopiado(TestAcao):
    def test_acessibilidade_vem_antes_do_ctrl_c(self):
        self.sistema.pela_acessibilidade, self.sistema.selecao = "lido sem teclas", "nao devia usar"
        self.acao(pedido("corrige isso"))
        self.assertIn("lido sem teclas", self.cliente.chamadas[0][1]["content"])
        self.assertEqual(self.sistema.coladas, ["texto certo"])  # era seleção: substitui

    def test_sem_selecao_usa_o_copiado_e_nao_substitui(self):
        self.sistema.selecao, self.sistema.copiado = "", "texto copiado"
        r = self.acao(pedido("corrige isso"))
        self.assertIn("texto copiado", self.cliente.chamadas[0][1]["content"])
        self.assertEqual(self.sistema.coladas, [])
        self.assertIn("cartão", r.fala)
        self.assertTrue(self.sessao.aguardando_decisao())

    def test_a_selecao_tem_prioridade(self):
        self.sistema.copiado = "texto copiado"
        self.acao(pedido("corrige isso"))
        self.assertIn("texto com erro", self.cliente.chamadas[0][1]["content"])
        self.assertEqual(self.sistema.coladas, ["texto certo"])

    def test_sem_chegar_na_janela_o_copiado_ainda_serve(self):
        self.sistema.chega, self.sistema.copiado = False, "texto copiado"
        self.acao(pedido("resume isso"))
        self.assertIn("texto copiado", self.cliente.chamadas[0][1]["content"])


class TestIdadeDaCopia(unittest.TestCase):
    def setUp(self):
        self.numero = 1
        self.agora = 1000.0
        p1 = mock.patch.object(selecao, "_numero_da_copia", lambda: self.numero)
        p2 = mock.patch.object(selecao.time, "monotonic", lambda: self.agora)
        for p in (p1, p2):
            p.start()
            self.addCleanup(p.stop)
        self.sistema = selecao.SistemaWindows(vigiar=False)
        self.area = mock.Mock()
        self.area.pede_privacidade.return_value = False
        self.area.ler_texto.return_value = "copiado"
        self.sistema._area = self.area

    def test_o_que_ja_estava_la_nao_conta(self):
        self.assertEqual(self.sistema.texto_copiado_recente(), "")

    def test_copia_recente_vale_e_antiga_nao(self):
        self.numero = 2
        self.assertEqual(self.sistema.texto_copiado_recente(), "copiado")
        self.agora += selecao.IDADE_MAXIMA_COPIA + 1
        self.assertEqual(self.sistema.texto_copiado_recente(), "")

    def test_copia_do_proprio_assistente_nao_conta(self):
        def copia_propria(_texto):
            self.numero += 1

        self.area.escrever_texto.side_effect = copia_propria
        self.sistema.deixar_na_area("x")
        self.assertEqual(self.sistema.texto_copiado_recente(), "")

    def test_copia_da_pessoa_nao_vale_depois_de_o_assistente_escrever_la(self):
        self.numero = 2
        self.assertEqual(self.sistema.texto_copiado_recente(), "copiado")
        self.sistema.deixar_na_area("resultado")
        self.assertEqual(self.sistema.texto_copiado_recente(), "")

    def test_respeita_o_pedido_de_privacidade(self):
        self.numero = 2
        self.area.pede_privacidade.return_value = True
        self.assertEqual(self.sistema.texto_copiado_recente(), "")


class TestRegra(unittest.TestCase):
    def setUp(self):
        self.regra = next(h for h in HABILIDADES if h.nome == "texto_selecionado").regra

    def test_mensagem_copiada_ou_selecionada_aponta_para_a_tela(self):
        for frase in ("responde a mensagem que eu acabei de copiar dizendo que vou",
                      "responde a mensagem selecionada dizendo que vou"):
            self.assertIsNone(self.regra(Leitura("texto_selecionado", "texto", {}, frase)), frase)

    def test_pedido_claro_que_a_ia_chamou_de_conversa_e_corrigido(self):
        conversar = next(h for h in HABILIDADES if h.nome == "conversar").regra
        c = conversar(Leitura("conversar", "mensagem", {}, "responde essa mensagem a seguir dizendo que vou"))
        self.assertEqual((c.intencao, c.alvo), ("texto_selecionado", "texto"))
        for frase in ("responde a pergunta de matemática", "explica o texto de platão", "qual a capital da frança"):
            self.assertIsNone(conversar(Leitura("conversar", "x", {}, frase)), frase)

    def test_precisa_apontar_para_a_tela(self):
        self.assertIsNone(self.regra(Leitura("texto_selecionado", "texto", {}, "resume isso")))
        correcao = self.regra(Leitura("texto_selecionado", "texto", {}, "resume a história do brasil"))
        self.assertEqual(correcao.intencao, "conversar")


if __name__ == "__main__":
    unittest.main()
