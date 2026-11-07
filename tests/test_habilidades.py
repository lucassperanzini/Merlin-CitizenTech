import json
import subprocess
import sys
import unittest
from pathlib import Path

import merlin.habilidades as habilidades_pkg
from merlin.habilidades import HABILIDADES, NOME_CONVERSAR, grupos, validar
from merlin.habilidades.base import ALVO_ASSISTENTE, Campo, Correcao, Exemplo, Grupo, Habilidade, Recursos
from merlin.ia import prompt_intencao
from merlin.ia.intencoes import ClassificadorIntencao, TipoIntencao
from merlin.personalidades import EMBUTIDAS, PERSONALIDADES, personalidade_padrao


class ClienteRoteirizado:
    """Responde em sequência (uma resposta por pergunta) e guarda o que recebeu."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def perguntar(self, mensagens, formato=None, opcoes=None):
        self.chamadas.append((mensagens[0]["content"], formato))
        return json.dumps(self.respostas.pop(0))


def habilidade_nova(**mudancas):
    """Uma habilidade inventada, como alguém faria ao criar um arquivo novo em merlin/habilidades/."""
    dados = dict(
        nome="tocar_musica",
        grupo=Grupo("musica", "tocar ou controlar músicas", 35),
        descricao="a pessoa pede para tocar uma música ou artista.",
        campos=(Campo("artista", "o artista pedido"),),
        exemplos=(Exemplo("toca legião urbana", "legião urbana", campos={"artista": "legião urbana"}),
                  Exemplo("o que é rock", "rock", intencao=NOME_CONVERSAR)),
        criar_acao=lambda recursos: (lambda intencao: "tocando"),
        mexe_no_computador=True,
    )
    dados.update(mudancas)
    return Habilidade(**dados)


ARQUIVO_HABILIDADE_NOVA = '''
from merlin.habilidades.base import Campo, Exemplo, Grupo, Habilidade

HABILIDADE = Habilidade(
    nome="tocar_musica",
    grupo=Grupo("musica", "tocar ou controlar músicas", 35),
    descricao="a pessoa pede para tocar uma música ou artista.",
    campos=(Campo("artista", "o artista pedido"),),
    exemplos=(Exemplo("toca legião urbana", "legião urbana", campos={"artista": "legião urbana"}),),
    criar_acao=lambda recursos: (lambda intencao: "tocando:" + intencao.campos["artista"]),
    mexe_no_computador=True,
)
'''

ROTEIRO_HABILIDADE_NOVA = '''
import json, main
from merlin.habilidades.base import Recursos
from merlin.ia.intencoes import ACOES_NO_COMPUTADOR, ClassificadorIntencao, TipoIntencao

class Cliente:
    def perguntar(self, mensagens, formato=None, opcoes=None):
        assert "tocar_musica" in mensagens[0]["content"]
        return json.dumps({"alvo": "legião", "intencao": "tocar_musica", "busca": "", "local": "", "artista": "legião"})

intencao = ClassificadorIntencao(Cliente()).classificar("toca legião")
acoes = main.construir_acoes(Recursos(*(None,) * 7))
print(intencao.tipo.value, intencao.campos["artista"], acoes[intencao.tipo](intencao),
      TipoIntencao.TOCAR_MUSICA in ACOES_NO_COMPUTADOR)
'''


class TestRegistro(unittest.TestCase):
    def test_encontra_todas_as_habilidades_com_conversar_por_ultimo(self):
        nomes = [h.nome for h in HABILIDADES]
        self.assertEqual(set(nomes), {"dispensar", "abrir_configuracoes", "trocar_assistente", "fechar_programa",
                                      "abrir_programa", "pesquisar_web", "clicar_botao", "conversar"})
        self.assertEqual(nomes[-1], NOME_CONVERSAR)

    def test_tipo_intencao_e_gerado_das_habilidades(self):
        self.assertEqual([t.value for t in TipoIntencao], [h.nome for h in HABILIDADES])
        self.assertEqual(TipoIntencao.CLICAR_BOTAO, "clicar_botao")

    def test_validacao_aponta_erros_de_montagem(self):
        conversar = [h for h in HABILIDADES if h.nome == NOME_CONVERSAR]
        with self.assertRaisesRegex(ValueError, "mesmo nome"):
            validar(conversar + [habilidade_nova(), habilidade_nova()])
        with self.assertRaisesRegex(ValueError, "obrigatória"):
            validar([habilidade_nova()])
        with self.assertRaisesRegex(ValueError, "inexistente"):
            validar(conversar + [habilidade_nova(exemplos=(Exemplo("x", "y", intencao="voar"),))])
        with self.assertRaisesRegex(ValueError, "não declara"):
            validar(conversar + [habilidade_nova(exemplos=(Exemplo("x", "y", campos={"cor": "azul"}),))])
        with self.assertRaisesRegex(ValueError, "Nome inválido"):
            validar(conversar + [habilidade_nova(nome="Tocar Música")])

    def test_toda_habilidade_cria_a_propria_acao(self):
        recursos = Recursos(*(None,) * 7)
        for h in HABILIDADES:
            self.assertTrue(callable(h.criar_acao(recursos)), h.nome)

    def test_objetos_compartilhados_sao_criados_uma_vez(self):
        recursos = Recursos(*(None,) * 7)
        self.assertIs(recursos.compartilhado("x", object), recursos.compartilhado("x", object))


class TestPrompt(unittest.TestCase):
    def test_prompt_tem_descricoes_campos_e_exemplos_de_todas(self):
        prompt = prompt_intencao.montar_prompt(HABILIDADES)
        for h in HABILIDADES:
            self.assertIn(f"- {h.nome}: {h.descricao}", prompt)
            for exemplo in h.exemplos:
                self.assertIn(f'"{exemplo.frase}" -> ', prompt)
        self.assertIn("busca: somente em pesquisar_web", prompt)
        self.assertIn("local: somente em clicar_botao", prompt)

    def test_contraexemplo_aparece_com_a_intencao_certa(self):
        prompt = prompt_intencao.montar_prompt(HABILIDADES)
        self.assertIn('"o que acontece se eu clicar em formatar" -> {"alvo": "formatar", "intencao": "conversar"', prompt)

    def test_esquema_tem_os_campos_de_todas(self):
        esquema = prompt_intencao.montar_esquema(HABILIDADES)
        self.assertEqual(esquema["required"], ["alvo", "intencao", "busca", "local"])
        self.assertEqual(esquema["properties"]["intencao"]["enum"], [h.nome for h in HABILIDADES])


class TestHabilidadeNova(unittest.TestCase):
    """O motivo da reorganização: uma habilidade nova funciona sem mexer em nenhum outro arquivo."""

    def setUp(self):
        self.habilidades = (*HABILIDADES[:-1], habilidade_nova(), HABILIDADES[-1])

    def test_entra_no_prompt_e_no_esquema(self):
        prompt = prompt_intencao.montar_prompt(self.habilidades)
        self.assertIn("- tocar_musica: a pessoa pede para tocar", prompt)
        self.assertIn("artista: somente em tocar_musica", prompt)
        self.assertIn('"toca legião urbana" -> {"alvo": "legião urbana", "intencao": "tocar_musica"', prompt)
        self.assertIn("artista", prompt_intencao.montar_esquema(self.habilidades)["required"])

    def test_arquivo_novo_na_pasta_funciona_sem_mexer_em_mais_nada(self):
        """Cria de verdade um arquivo em merlin/habilidades/ e roda o assistente em outro processo."""
        pasta = Path(habilidades_pkg.__file__).parent
        arquivo = pasta / "zz_teste_tocar_musica.py"
        arquivo.write_text(ARQUIVO_HABILIDADE_NOVA, encoding="utf-8")
        self.addCleanup(arquivo.unlink, missing_ok=True)
        saida = subprocess.run([sys.executable, "-c", ROTEIRO_HABILIDADE_NOVA], capture_output=True, text=True,
                               encoding="utf-8", cwd=pasta.parent.parent, timeout=60)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        ultima_linha = saida.stdout.strip().splitlines()[-1]  # antes vem a mensagem de boas-vindas do pygame
        self.assertEqual(ultima_linha.split(), ["tocar_musica", "legião", "tocando:legião", "True"])


class TestRegras(unittest.TestCase):
    def _classificar(self, resposta, comando, duas_etapas=False):
        cliente = ClienteRoteirizado(*resposta)
        return ClassificadorIntencao(cliente, duas_etapas=duas_etapas).classificar(comando), cliente

    def test_correcoes_em_sequencia_juntam_os_motivos(self):
        # fechar -> (verbo de abrir) abrir -> (alvo é o assistente) conversar
        intencao, _ = self._classificar([{"alvo": "merlin", "intencao": "fechar_programa", "busca": "", "local": ""}],
                                        "abre o merlin")
        self.assertIs(intencao.tipo, TipoIntencao.CONVERSAR)
        self.assertIn("verbo de abrir", intencao.motivo_regra)
        self.assertIn("não o próprio assistente", intencao.motivo_regra)

    def test_clique_sem_dizer_qual_botao_fica_sem_alvo(self):
        intencao, _ = self._classificar([{"alvo": "merlin", "intencao": "clicar_botao", "busca": "", "local": ""}],
                                        "clica num botão")
        self.assertEqual((intencao.tipo, intencao.alvo), (TipoIntencao.CLICAR_BOTAO, ""))
        self.assertIn("sem dizer qual botão", intencao.motivo_regra)

    def test_campo_de_outra_habilidade_nao_sobra(self):
        resposta = {"alvo": "chrome", "intencao": "abrir_programa", "busca": "", "local": "word"}
        intencao, _ = self._classificar([resposta], "abre o chrome")
        self.assertEqual((intencao.local, intencao.campos), ("", {}))

    def test_resposta_com_intencao_desconhecida_vira_conversa(self):
        intencao, _ = self._classificar([{"alvo": "x", "intencao": "voar", "busca": "", "local": ""}], "voa")
        self.assertIs(intencao.tipo, TipoIntencao.CONVERSAR)
        self.assertIn("inválida", intencao.motivo_regra)


class TestDuasEtapas(unittest.TestCase):
    def test_escolhe_o_grupo_e_depois_so_entre_as_habilidades_dele(self):
        cliente = ClienteRoteirizado({"grupo": "tela"},
                                     {"alvo": "salvar", "intencao": "clicar_botao", "local": "word"})
        intencao = ClassificadorIntencao(cliente, duas_etapas=True).classificar("clica em salvar no word")
        self.assertEqual((intencao.tipo, intencao.alvo, intencao.local), (TipoIntencao.CLICAR_BOTAO, "salvar", "word"))
        self.assertEqual(intencao.resposta_modelo["grupo"], "tela")
        prompt_grupos, esquema_grupos = cliente.chamadas[0]
        self.assertIn("- programas:", prompt_grupos)
        prompt, esquema = cliente.chamadas[1]
        self.assertEqual(esquema["properties"]["intencao"]["enum"], ["clicar_botao", "conversar"])
        self.assertNotIn("abrir_programa", prompt)  # a segunda pergunta é curta: só o que importa
        self.assertNotIn("busca", esquema["properties"])

    def test_grupo_conversa_responde_com_uma_pergunta_so(self):
        cliente = ClienteRoteirizado({"grupo": "conversa"})
        intencao = ClassificadorIntencao(cliente, duas_etapas=True).classificar("qual a capital do chile")
        self.assertIs(intencao.tipo, TipoIntencao.CONVERSAR)
        self.assertEqual(len(cliente.chamadas), 1)

    def test_regras_valem_nas_duas_etapas(self):
        cliente = ClienteRoteirizado({"grupo": "tela"}, {"alvo": "formatar", "intencao": "clicar_botao", "local": ""})
        intencao = ClassificadorIntencao(cliente, duas_etapas=True).classificar("o que faz o formatar")
        self.assertIs(intencao.tipo, TipoIntencao.CONVERSAR)

    def test_grupo_invalido_vira_conversa(self):
        cliente = ClienteRoteirizado({"grupo": "voar"})
        self.assertIs(ClassificadorIntencao(cliente, duas_etapas=True).classificar("x").tipo, TipoIntencao.CONVERSAR)

    def test_decide_sozinho_pelo_numero_de_habilidades(self):
        self.assertFalse(ClassificadorIntencao(None).duas_etapas)  # 8 habilidades hoje
        muitas = (*[habilidade_nova(nome=f"extra_{i}") for i in range(10)], *HABILIDADES)
        self.assertTrue(ClassificadorIntencao(None, muitas).duas_etapas)

    def test_todo_grupo_tem_descricao_no_prompt_dos_grupos(self):
        prompt = prompt_intencao.montar_prompt_grupos(HABILIDADES)
        for g in (grupos.ASSISTENTE, grupos.PROGRAMAS, grupos.TELA, grupos.INTERNET, grupos.CONVERSA):
            self.assertIn(f"- {g.nome}: {g.descricao}", prompt)


class TestPersonalidadesDescobertas(unittest.TestCase):
    def test_encontra_as_duas_em_ordem_e_o_padrao(self):
        # os do código, em ordem; os criados no configurador (como os seus) vêm depois
        self.assertEqual(list(EMBUTIDAS), ["merlin", "jarvis"])
        self.assertEqual(list(PERSONALIDADES)[:2], ["merlin", "jarvis"])
        self.assertEqual(personalidade_padrao().id, "merlin")

    def test_alvo_do_assistente_e_um_nome_de_personalidade(self):
        self.assertIn(ALVO_ASSISTENTE, PERSONALIDADES)

    def test_correcao_mantem_alvo_quando_nao_informado(self):
        self.assertIsNone(Correcao("conversar").alvo)


if __name__ == "__main__":
    unittest.main()
