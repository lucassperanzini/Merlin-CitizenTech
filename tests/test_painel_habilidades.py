import json
import unittest

from merlin.habilidades import HABILIDADES
from merlin.interface.painel_habilidades import ServicoPainelHabilidades
from tests.falsos import ClienteFalso


class TestPainelHabilidades(unittest.TestCase):
    def _servico(self, resposta=None):
        return ServicoPainelHabilidades(ClienteFalso(json.dumps(resposta) if resposta else ""))

    def test_lista_todas_agrupadas_com_titulos(self):
        dados = self._servico().listar()
        nomes = [h["nome"] for g in dados["grupos"] for h in g["habilidades"]]
        self.assertEqual(sorted(nomes), sorted(h.nome for h in HABILIDADES))
        self.assertEqual(dados["total"], len(HABILIDADES))
        self.assertIn("uma etapa", dados["modo"])
        clicar = next(h for g in dados["grupos"] for h in g["habilidades"] if h["nome"] == "clicar_botao")
        self.assertEqual(clicar["titulo"], "Clicar em botão")
        self.assertTrue(clicar["mexe_no_computador"])
        self.assertTrue(clicar["regras"])
        onde_age = {h["nome"]: h["age"] for g in dados["grupos"] for h in g["habilidades"]}
        self.assertEqual((onde_age["clicar_botao"], onde_age["abrir_configuracoes"], onde_age["conversar"]),
                         ("computador", "assistente", "fala"))

    def test_separa_exemplos_e_contraexemplos(self):
        dados = self._servico().listar()
        clicar = next(h for g in dados["grupos"] for h in g["habilidades"] if h["nome"] == "clicar_botao")
        self.assertIn({"frase": "pausa a música no spotify", "alvo": "pausar", "campos": {"local": "spotify"}},
                      clicar["exemplos"])
        self.assertIn({"frase": "o que acontece se eu clicar em formatar", "vira": "Conversar"},
                      clicar["contraexemplos"])

    def test_toda_habilidade_tem_titulo_e_regras_explicadas(self):
        for h in HABILIDADES:
            self.assertTrue(h.titulo, h.nome)
            if h.regra:
                self.assertTrue(h.regras_resumo, f"{h.nome} tem regra, mas o painel não a explica")

    def test_testar_mostra_a_escolha_e_a_regra(self):
        servico = self._servico({"alvo": "chrome", "intencao": "fechar_programa", "busca": "", "local": ""})
        r = servico.testar("abre o chrome")
        self.assertEqual((r["habilidade"], r["titulo"], r["alvo"]), ("abrir_programa", "Abrir programa", "chrome"))
        self.assertEqual(r["ia_escolheu"], "Fechar programa")
        self.assertIn("verbo de abrir", r["motivo_regra"])

    def test_testar_sem_frase_ou_sem_ia(self):
        self.assertIn("erro", self._servico().testar("  "))
        servico = ServicoPainelHabilidades(ClienteFalso(ConnectionError("fora")))
        self.assertIn("Ollama", servico.testar("abre o chrome")["erro"])


if __name__ == "__main__":
    unittest.main()
