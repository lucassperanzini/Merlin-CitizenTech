"""O especialista da Defesa Civil: a skill consultar_protocolo, a conferência pela busca e o modo em que ele responde
a tudo. Os testes usam um modelo falso: não carregam o torch nem os pesos."""
import threading
import unittest

from merlin.estado import EstadoAssistente
from merlin.ia.especialista import (AVISO_CARREGANDO, AVISO_CURTA, AVISO_FALHOU, AVISO_FORMATO,
                                    EspecialistaDefesaCivil, Fonte, RespostaEspecialista)
from merlin.ia.frases import GeradorFrases
from merlin.acoes.consultar_protocolo import ConsultarProtocolo
from merlin.habilidades.base import Leitura
from merlin.habilidades.abrir_programa import HABILIDADE as ABRIR_PROGRAMA
from merlin.habilidades.dispensar import HABILIDADE as DISPENSAR
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.resposta import Resultado
from merlin.nucleo.sessao import Sessao
from merlin.personalidades import personalidade_padrao
from tests.falsos import CanalFalso, ClassificadorFalso, ConfirmadorFalso, LocutorFalso, SaudacaoFalsa

CITACAO = {"doc_id": "DOC006", "titulo": "Introdução ao Sistema de Comando de Incidentes", "paginas": [12, 12]}


class ModeloFalso:
    limiar = 0.836

    def __init__(self, resposta=None, erro=None, nota=0.9):
        self.perguntas = []
        self._nota = nota
        self._buscador = self  # a busca do pacote: só a nota do melhor trecho
        self._resposta = resposta or {"status": "ok", "resposta": "O SCI é uma ferramenta de gestão.",
                                      "citacoes": [CITACAO], "avisos": [], "confianca_busca": 0.89}
        self._erro = erro

    def search(self, pergunta, k=1):
        return [{"score": self._nota}]

    def perguntar(self, pergunta):
        self.perguntas.append(pergunta)
        if self._erro:
            raise self._erro
        return self._resposta


class DivisorQueAnota:
    def __init__(self):
        self.comandos = []

    def dividir(self, comando):
        self.comandos.append(comando)
        return [comando]


def pronto(modelo):
    especialista = EspecialistaDefesaCivil(carregar=lambda: modelo)
    especialista._carregar_agora()
    return especialista


class TestEspecialista(unittest.TestCase):
    def test_resposta_com_fonte_falada(self):
        r = pronto(ModeloFalso()).responder("o que é o SCI")
        self.assertTrue(r.encontrou)
        self.assertEqual(r.fontes, (Fonte("DOC006", "Introdução ao Sistema de Comando de Incidentes", (12, 12)),))
        self.assertEqual(r.para_falar(), "O SCI é uma ferramenta de gestão. "
                                         "Fonte: Introdução ao Sistema de Comando de Incidentes, página 12.")

    def test_varias_paginas_e_aviso_do_documento(self):
        r = RespostaEspecialista("Texto.", True, (Fonte("DOC009", "Instrução Técnica 16", (2, 3)),),
                                 ("DOC009: Documento com vigência a verificar.",))
        self.assertEqual(r.para_falar(), "Texto. Fonte: Instrução Técnica 16, páginas 2 a 3. "
                                         "Documento com vigência a verificar.")

    def test_fora_dos_documentos(self):
        modelo = ModeloFalso({"status": "nao_consta", "resposta": "Não consta nos documentos da base de conhecimento.",
                              "citacoes": [], "avisos": [], "confianca_busca": 0.76})
        r = pronto(modelo).responder("qual a capital da frança")
        self.assertFalse(r.encontrou)
        self.assertEqual(r.para_falar(), "Não consta nos documentos da base de conhecimento.")

    def test_erro_de_formato_e_pergunta_curta(self):
        formato = ModeloFalso({"status": "erro_formato", "resposta": "", "confianca_busca": 0.9})
        self.assertEqual(pronto(formato).responder("pergunta longa").texto, AVISO_FORMATO)
        self.assertEqual(pronto(ModeloFalso(erro=ValueError("curta"))).responder("oi").texto, AVISO_CURTA)

    def test_ainda_carregando_nao_espera(self):
        liberar = threading.Event()
        especialista = EspecialistaDefesaCivil(carregar=lambda: liberar.wait() and ModeloFalso())
        especialista.iniciar_carga()
        self.assertEqual(especialista.responder("o que é o SCI").texto, AVISO_CARREGANDO)
        self.assertTrue(especialista.disponivel())  # carregando ainda não acende o aviso de IA fora
        liberar.set()

    def test_carga_que_falha_avisa(self):
        def quebra():
            raise OSError("sem os pesos")
        especialista = EspecialistaDefesaCivil(carregar=quebra)
        with self.assertLogs("merlin.ia.especialista", "ERROR"):
            especialista._carregar_agora()
        self.assertFalse(especialista.disponivel())
        self.assertEqual(especialista.responder("o que é o SCI").texto, AVISO_FALHOU)


class TestModoEspecialista(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoAssistente()
        self.canal = CanalFalso()
        self.sessao = Sessao(self.estado, self.canal)
        self.locutor = LocutorFalso()
        self.divisor = DivisorQueAnota()
        self.classificador = ClassificadorFalso()
        self.modelo = ModeloFalso()
        self.processador = ProcessadorComandos(
            self.estado, self.sessao, self.canal, self.locutor, self.divisor, self.classificador,
            ConfirmadorFalso(), SaudacaoFalsa(), {t: None for t in TipoIntencao}, especialista=pronto(self.modelo),
            so_especialista=True)

    def test_toda_pergunta_vai_ao_especialista_sem_skills(self):
        self.sessao.ativar()
        self.processador.processar("o que é o sistema de comando de incidentes")
        self.assertEqual(self.modelo.perguntas, ["o que é o sistema de comando de incidentes"])
        self.assertEqual((self.divisor.comandos, self.classificador.comandos), ([], []))
        self.assertTrue(self.locutor.falas[0].startswith("O SCI é uma ferramenta de gestão. Fonte:"))

    def test_mesmo_um_pedido_de_acao_vai_ao_especialista(self):
        self.sessao.ativar()
        self.processador.processar("abre o chrome")
        self.assertEqual(self.modelo.perguntas, ["abre o chrome"])
        self.assertEqual(self.classificador.comandos, [])

    def test_chamado_com_a_pergunta_abre_o_cartao(self):
        self.processador.processar("merlin, o que é o SCI")
        self.assertEqual(self.modelo.perguntas, ["o que é o sci"])  # a remoção do nome deixa em minúsculas
        self.assertIn("mostrar", self.canal.eventos)  # a resposta é longa para o balão
        self.assertEqual(len(self.locutor.falas), 1)

    def test_so_o_nome_ainda_sauda(self):
        self.processador.processar("merlin")
        self.assertEqual(self.locutor.falas, ["saudação"])
        self.assertEqual(self.modelo.perguntas, [])

    def test_falha_inesperada_e_avisada(self):
        especialista = pronto(ModeloFalso(erro=RuntimeError("placa de vídeo sem memória")))
        self.processador._especialista = especialista
        self.sessao.ativar()
        with self.assertLogs("merlin.nucleo.processador", "ERROR"):
            self.processador.processar("o que é o SCI")
        self.assertIn("problema ao consultar os protocolos", self.locutor.falas[0])


class TestSkillConsultarProtocolo(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoAssistente()
        self.canal = CanalFalso()
        self.sessao = Sessao(self.estado, self.canal)
        self.locutor = LocutorFalso()
        self.executadas = []

    def montar(self, intencao, nota=0.9):
        especialista = pronto(ModeloFalso(nota=nota))
        protocolo = ConsultarProtocolo(especialista)

        def anotar(tipo):
            def acao(i):
                self.executadas.append(tipo)
                if tipo is TipoIntencao.CONSULTAR_PROTOCOLO:
                    return protocolo(i)
                return Resultado("conversei", frase_completa=True)
            return acao
        self.processador = ProcessadorComandos(
            self.estado, self.sessao, self.canal, self.locutor, DivisorQueAnota(), ClassificadorFalso(intencao),
            ConfirmadorFalso(), SaudacaoFalsa(), {t: anotar(t) for t in TipoIntencao}, especialista=especialista)
        self.sessao.ativar()

    def test_skill_responde_pelo_especialista_com_a_fonte(self):
        self.montar(Intencao(TipoIntencao.CONSULTAR_PROTOCOLO, "sci", "o que é o sci"))
        self.processador.processar("o que é o sci")
        self.assertEqual(self.executadas, [TipoIntencao.CONSULTAR_PROTOCOLO])
        self.assertIn("Fonte: Introdução ao Sistema de Comando de Incidentes", self.locutor.falas[0])

    def test_conversa_parecida_com_os_protocolos_vai_ao_especialista(self):
        self.montar(Intencao(TipoIntencao.CONVERSAR, "vento", "e se o vento virar"), nota=0.86)
        self.processador.processar("e se o vento virar")
        self.assertEqual(self.executadas, [TipoIntencao.CONSULTAR_PROTOCOLO])

    def test_conversa_comum_continua_conversa(self):
        self.montar(Intencao(TipoIntencao.CONVERSAR, "piada", "me conta uma piada"), nota=0.77)
        self.processador.processar("me conta uma piada")
        self.assertEqual(self.executadas, [TipoIntencao.CONVERSAR])
        self.assertEqual(self.locutor.falas, ["conversei"])

    def test_sem_os_protocolos_nao_inventa(self):
        r = ConsultarProtocolo(pronto(ModeloFalso({"status": "nao_consta", "resposta": "Não consta nos documentos.",
                                                    "citacoes": [], "avisos": []})))(
            Intencao(TipoIntencao.CONSULTAR_PROTOCOLO, "", "como pilotar um helicóptero de combate"))
        self.assertEqual(r.fala, "Não consta nos documentos.")
        self.assertTrue(r.frase_completa)

    def test_especialista_carregando_nao_desvia_a_conversa(self):
        especialista = EspecialistaDefesaCivil(carregar=lambda: None)
        self.assertFalse(especialista.parece_protocolo("e se o vento virar"))


class TestRegrasDoModeloPequeno(unittest.TestCase):
    def ler(self, habilidade, comando, alvo):
        return habilidade.regra(Leitura(habilidade.nome, alvo, {}, comando))

    def test_tudo_bem_puxa_conversa_e_nao_dispensa(self):
        for frase in ("tudo bem com você", "como vai", "tudo certo por aí"):
            with self.subTest(frase):
                self.assertEqual(self.ler(DISPENSAR, frase, "merlin").intencao, "conversar")

    def test_tudo_bem_com_despedida_ainda_dispensa(self):
        for frase in ("tudo bem, pode ir", "beleza, obrigado", "valeu, por hoje é só"):
            with self.subTest(frase):
                self.assertIsNone(self.ler(DISPENSAR, frase, "merlin"))

    def test_pergunta_nao_abre_programa(self):
        correcao = self.ler(ABRIR_PROGRAMA, "como abro as configurações do celular", "configurações")
        self.assertEqual(correcao.intencao, "conversar")
        self.assertIsNone(self.ler(ABRIR_PROGRAMA, "abre o paint", "paint"))


class TestSaudacaoSemIA(unittest.TestCase):
    def test_usa_as_frases_prontas_sem_chamar_o_ollama(self):
        saudacao = personalidade_padrao().saudacao
        frase = GeradorFrases(None, lambda: saudacao).gerar()
        self.assertIn(frase, saudacao.reservas)


if __name__ == "__main__":
    unittest.main()
