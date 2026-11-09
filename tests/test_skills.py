import json
import tempfile
import unittest
from pathlib import Path

from merlin import habilidades as registro
from merlin.habilidades import HABILIDADES
from merlin.ia.intencoes import ClassificadorIntencao
from merlin.interface.painel_habilidades import ServicoPainelHabilidades
from tests.falsos import ClienteFalso


class TestSkillsEditaveis(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        registro.recarregar(self.pasta)
        self.addCleanup(registro.recarregar)
        self.cliente = ClienteFalso(json.dumps({"alvo": "x", "intencao": "conversar"}))
        self.servico = ServicoPainelHabilidades(self.cliente, pasta=self.pasta)

    def _dados(self, **mudancas):
        return {"titulo": "Abrir apps", "descricao": "abrir um programa instalado",
                "exemplos": [{"frase": "bota o bloco de notas", "alvo": "bloco de notas"}], **mudancas}

    def test_exemplo_novo_chega_na_ia_sem_reiniciar(self):
        classificador = ClassificadorIntencao(self.cliente)
        self.assertNotIn("bota o bloco de notas", classificador._uma_etapa[0])
        self.assertNotIn("erro", self.servico.salvar("abrir_programa", self._dados()))
        classificador.classificar("oi")
        self.assertIn("bota o bloco de notas", self.cliente.chamadas[-1][0]["content"])
        self.assertIn("abrir um programa instalado", self.cliente.chamadas[-1][0]["content"])

    def test_painel_mostra_o_ajuste_e_a_regra_continua(self):
        self.servico.salvar("abrir_programa", self._dados())
        h = self._skill("abrir_programa")
        self.assertEqual((h["titulo"], h["ajustada"]), ("Abrir apps", True))
        self.assertTrue(h["regras"])

    def test_restaurar_volta_ao_original(self):
        self.servico.salvar("abrir_programa", self._dados())
        self.servico.restaurar("abrir_programa")
        original = next(h for h in HABILIDADES if h.nome == "abrir_programa")
        self.assertEqual(registro.por_nome("abrir_programa"), original)
        self.assertFalse(self._skill("abrir_programa")["ajustada"])

    def test_contraexemplo_e_dados_extras_sao_guardados(self):
        self.servico.salvar("pesquisar_web", self._dados(exemplos=[
            {"frase": "procura gatos", "alvo": "gatos", "campos": {"busca": "gatos"}},
            {"frase": "fala sobre gatos", "alvo": "gatos", "intencao": "conversar"}]))
        exemplos = registro.por_nome("pesquisar_web").exemplos
        self.assertEqual(exemplos[0].campos, {"busca": "gatos"})
        self.assertEqual(exemplos[1].intencao, "conversar")

    def test_recusa_o_que_estragaria_a_skill(self):
        for dados in (self._dados(titulo=" "), self._dados(descricao=""), self._dados(exemplos=[]),
                      self._dados(exemplos=[{"frase": "abre", "alvo": ""}]),
                      self._dados(exemplos=[{"frase": "a", "alvo": "b"}, {"frase": "A", "alvo": "c"}]),
                      self._dados(exemplos=[{"frase": "a", "alvo": "b", "intencao": "conversar"}]),
                      self._dados(exemplos=[{"frase": "a", "alvo": "b"}, {"frase": "c", "alvo": "d", "intencao": "nao_existe"}])):
            self.assertIn("erro", self.servico.salvar("abrir_programa", dados), dados)
        self.assertEqual(list(self.pasta.iterdir()), [])
        self.assertIn("erro", self.servico.salvar("nao_existe", self._dados()))

    def test_arquivo_estragado_e_ignorado(self):
        (self.pasta / "abrir_programa.json").write_text("{quebrado", encoding="utf-8")
        registro.recarregar(self.pasta)
        self.assertEqual(registro.por_nome("abrir_programa"), next(h for h in HABILIDADES if h.nome == "abrir_programa"))

    def test_toda_skill_tem_icone_e_resumo_para_a_pessoa(self):
        for h in HABILIDADES:
            self.assertTrue(h.resumo, h.nome)
            self.assertNotEqual(h.icone, "✨", h.nome)

    def test_skill_desligada_sai_da_ia_na_hora_e_volta(self):
        classificador = ClassificadorIntencao(self.cliente)
        self.assertIn("abrir_pasta", classificador._uma_etapa[0])
        self.servico.ligar("abrir_pasta", False)
        classificador.classificar("oi")
        prompt = self.cliente.chamadas[-1][0]["content"]
        self.assertNotIn("abrir_pasta", prompt)  # nem como destino de um exemplo de outra skill
        self.assertFalse(self._skill("abrir_pasta")["ligada"])
        self.servico.ligar("abrir_pasta", True)
        classificador.classificar("oi")
        self.assertIn("abrir_pasta", self.cliente.chamadas[-1][0]["content"])

    def test_regra_que_aponta_para_skill_desligada_vira_conversa(self):
        self.servico.ligar("abrir_pasta", False)
        resposta = json.dumps({"alvo": "downloads", "intencao": "abrir_programa"})
        intencao = ClassificadorIntencao(ClienteFalso(resposta)).classificar("abre a pasta downloads")
        self.assertEqual(intencao.tipo.value, "conversar")

    def test_conversar_nao_desliga(self):
        self.assertIn("erro", self.servico.ligar("conversar", False))
        self.assertTrue(self._skill("conversar")["ligada"])
        self.assertFalse(self._skill("conversar")["pode_desligar"])

    def test_desligar_e_editar_nao_se_atrapalham(self):
        self.servico.ligar("abrir_pasta", False)
        self.servico.salvar("abrir_programa", self._dados())
        self.assertFalse(self._skill("abrir_pasta")["ligada"])
        self.assertEqual(self._skill("abrir_programa")["titulo"], "Abrir apps")

    def _skill(self, nome):
        return next(h for g in self.servico.listar()["grupos"] for h in g["habilidades"] if h["nome"] == nome)


if __name__ == "__main__":
    unittest.main()
