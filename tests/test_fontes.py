"""A fonte citada pelo especialista vira um botão no cartão, que abre o PDF do protocolo na página do trecho."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from merlin.acoes.consultar_protocolo import ConsultarProtocolo
from merlin.estado import EstadoAssistente
from merlin.ia import especialista
from merlin.ia.especialista import DOCUMENTOS, ORIGEM_PROTOCOLOS, Fonte, RespostaEspecialista
from merlin.ia.intencoes import Intencao, TipoIntencao
from merlin.interface.leitor_protocolos import AVISO_SEM_PDF, LeitorProtocolos
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.sessao import Sessao
from tests.falsos import CanalFalso, ClassificadorFalso, ConfirmadorFalso, DivisorFalso, LocutorFalso, SaudacaoFalsa

APOSTILA = Fonte("DOC005", "Apostila Brigadista de Prevenção e Combate", (49, 51))


class ComPdfs(unittest.TestCase):
    """Uma pasta de protocolos de mentira, com só o DOC005 baixado."""

    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        (self.pasta / "DOC005.pdf").write_bytes(b"%PDF-1.4")
        patch = mock.patch.object(especialista, "PASTA_PROTOCOLOS", self.pasta)
        patch.start()
        self.addCleanup(patch.stop)


class TestFonteNoCartao(ComPdfs):
    def test_botao_abre_na_primeira_pagina_do_trecho(self):
        self.assertEqual(APOSTILA.para_cartao(), {"documento": "DOC005", "titulo": APOSTILA.titulo, "pagina": 49,
                                                  "paginas": "pp. 49-51", "disponivel": True})
        self.assertEqual(Fonte("DOC005", "Apostila", (12, 12)).para_cartao()["paginas"], "p. 12")

    def test_pdf_nao_baixado_fica_indisponivel(self):
        self.assertFalse(Fonte("DOC009", "Instrução Técnica 16", (2, 3)).para_cartao()["disponivel"])

    def test_documentos_fixados_num_commit_e_com_hash(self):
        self.assertRegex(ORIGEM_PROTOCOLOS, r"/[0-9a-f]{40}/")
        self.assertEqual(sorted(DOCUMENTOS), [f"DOC00{i}" for i in range(1, 10)])  # os 9 da base do especialista
        for documento, (caminho, conferencia) in DOCUMENTOS.items():
            self.assertTrue(caminho.endswith(".pdf"), documento)
            self.assertRegex(conferencia, r"^[0-9a-f]{64}$", documento)


class JanelaFalsa:
    def __init__(self, nome, url):
        self.nome, self.url, self.trocas = nome, url, []
        self.events = mock.Mock()
        self.events.closed = mock.MagicMock()
        self.events.closed.__iadd__ = lambda s, f: s

    def load_url(self, url):
        self.url = url
        self.trocas.append(url)

    def set_title(self, nome):
        self.nome = nome

    def show(self):
        pass

    def restore(self):
        pass


class TestLeitor(ComPdfs):
    def setUp(self):
        super().setUp()
        self.criadas = []
        self.leitor = LeitorProtocolos(criar_janela=lambda nome, url: self.criadas.append(JanelaFalsa(nome, url))
                                       or self.criadas[-1])

    def test_abre_o_pdf_na_pagina(self):
        self.assertEqual(self.leitor.abrir("DOC005", 49, "Apostila"), {})
        janela = self.criadas[0]
        self.assertTrue(janela.url.startswith("file:///") and janela.url.endswith("/DOC005.pdf#page=49"))
        self.assertIn("página 49", janela.nome)

    def test_outra_fonte_reaproveita_a_mesma_janela(self):
        self.leitor.abrir("DOC005", 49)
        self.leitor.abrir("DOC005", 12)
        self.assertEqual(len(self.criadas), 1)
        self.assertTrue(self.criadas[0].url.endswith("#page=12"))

    def test_so_documentos_da_base_e_paginas_validas(self):
        # A página não consegue mandar abrir um arquivo qualquer do disco
        for documento in ("../../Windows/win.ini", "DOC999", ""):
            self.assertIn("erro", self.leitor.abrir(documento, 1))
        self.assertIn("erro", self.leitor.abrir("DOC005", "um"))
        self.assertEqual(self.leitor.abrir("DOC009", 2), {"erro": AVISO_SEM_PDF})  # da base, mas não baixado
        self.assertEqual(self.criadas, [])

    def test_pagina_zero_ou_negativa_vira_a_primeira(self):
        self.leitor.abrir("DOC005", 0)
        self.assertTrue(self.criadas[0].url.endswith("#page=1"))


class EspecialistaFalso:
    def __init__(self, fontes):
        self._fontes = fontes

    def responder(self, pergunta):
        return RespostaEspecialista("Óculos, luva, balaclava e capacete, entre outros.", True, self._fontes)

    def parece_protocolo(self, pergunta):
        return False


class TestFontesChegamAoCartao(ComPdfs):
    def processar(self, fontes):
        estado, canal, locutor = EstadoAssistente(), CanalFalso(), LocutorFalso()
        sessao = Sessao(estado, canal)
        protocolo = ConsultarProtocolo(EspecialistaFalso(fontes))
        processador = ProcessadorComandos(
            estado, sessao, canal, locutor, DivisorFalso(),
            ClassificadorFalso(Intencao(TipoIntencao.CONSULTAR_PROTOCOLO, "epi", "quais epis")),
            ConfirmadorFalso(), SaudacaoFalsa(), {t: protocolo for t in TipoIntencao})
        sessao.ativar()
        processador.processar("quais epis")
        return [e for e in canal.eventos if isinstance(e, tuple)], locutor.falas

    def test_um_botao_por_documento_antes_da_fala(self):
        eventos, falas = self.processar((APOSTILA, Fonte("DOC009", "Instrução Técnica 16", (2, 3))))
        self.assertEqual(len(eventos), 1)
        _, botoes = eventos[0]
        self.assertEqual([(b["documento"], b["pagina"], b["disponivel"]) for b in botoes],
                         [("DOC005", 49, True), ("DOC009", 2, False)])
        self.assertTrue(falas)

    def test_mesma_pagina_do_mesmo_documento_aparece_uma_vez(self):
        eventos, _ = self.processar((APOSTILA, APOSTILA))
        self.assertEqual(len(eventos[0][1]), 1)

    def test_sem_fonte_sem_botao(self):
        eventos, _ = self.processar(())
        self.assertEqual(eventos, [])


if __name__ == "__main__":
    unittest.main()
