import tempfile
import unittest
from datetime import date
from pathlib import Path

from merlin.nucleo.gravador_raciocinio import GravadorRaciocinio, formatar_passo
from merlin.nucleo.raciocinio import Raciocinio, TipoPasso


class TestGravador(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name) / "registros"
        self.dia = date(2026, 11, 5)
        self.gravador = GravadorRaciocinio(self.pasta, 30, hoje=lambda: self.dia)

    def test_grava_cada_passo_no_arquivo_do_dia(self):
        r = Raciocinio(gravador=self.gravador)
        r.registrar(TipoPasso.OUVI, "Abre o chrome", modelo="qwen3:8b")
        r.registrar(TipoPasso.INTENCAO, "“abre o chrome” → abrir_programa", alvo="chrome")
        texto = (self.pasta / "2026-11-05.txt").read_text(encoding="utf-8")
        self.assertIn("OUVI       Abre o chrome", texto)
        self.assertIn("modelo: qwen3:8b", texto)
        self.assertIn("INTENÇÃO   “abre o chrome” → abrir_programa", texto)
        self.assertIn("alvo: chrome", texto)

    def test_dia_novo_vai_para_outro_arquivo(self):
        r = Raciocinio(gravador=self.gravador)
        r.registrar(TipoPasso.OUVI, "ontem")
        self.dia = date(2026, 11, 6)
        r.registrar(TipoPasso.OUVI, "hoje")
        self.assertEqual(sorted(p.name for p in self.pasta.iterdir()), ["2026-11-05.txt", "2026-11-06.txt"])

    def test_limpar_a_tela_nao_apaga_o_arquivo(self):
        r = Raciocinio(gravador=self.gravador)
        r.registrar(TipoPasso.OUVI, "oi")
        r.limpar()
        self.assertIn("oi", (self.pasta / "2026-11-05.txt").read_text(encoding="utf-8"))

    def test_cada_pedido_comeca_com_linha_em_branco(self):
        r = Raciocinio()
        r.registrar(TipoPasso.OUVI, "oi")
        r.registrar(TipoPasso.FALA, "olá")
        ouvi, fala = r.desde(0)
        self.assertTrue(formatar_passo(ouvi).startswith("\n["))
        self.assertTrue(formatar_passo(fala).startswith("["))

    def test_apaga_so_os_antigos_e_so_arquivos_de_data(self):
        self.pasta.mkdir()
        for nome in ("2026-10-05.txt", "2026-10-06.txt", "2026-11-04.txt", "anotacoes.txt", "2026-13-99.txt"):
            (self.pasta / nome).write_text("x", encoding="utf-8")
        self.assertEqual(self.gravador.apagar_antigos(), 1)  # 30 dias antes de 05/11 é 06/10
        self.assertEqual(sorted(p.name for p in self.pasta.iterdir()),
                         ["2026-10-06.txt", "2026-11-04.txt", "2026-13-99.txt", "anotacoes.txt"])

    def test_pasta_inexistente_nao_e_erro(self):
        self.assertEqual(self.gravador.apagar_antigos(), 0)

    def test_falha_no_disco_nao_derruba_o_assistente(self):
        self.pasta.parent.joinpath("registros").write_text("um arquivo no lugar da pasta", encoding="utf-8")
        r = Raciocinio(gravador=self.gravador)
        with self.assertLogs("merlin.nucleo.gravador_raciocinio", level="WARNING"):
            r.registrar(TipoPasso.OUVI, "oi")
        self.assertEqual(len(r.desde(0)), 1)  # a tela continua funcionando


if __name__ == "__main__":
    unittest.main()
