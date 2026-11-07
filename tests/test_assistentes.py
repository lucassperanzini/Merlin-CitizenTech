import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from merlin.interface.assistentes import ServicoAssistentes
from merlin.personalidades import EMBUTIDAS, NOMES_DO_ASSISTENTE, PERSONALIDADES, armazenamento, modelo, recarregar
from merlin.personalidades.armazenamento import DadosInvalidos

MERLIN, JARVIS = EMBUTIDAS["merlin"], EMBUTIDAS["jarvis"]


def assistente_valido(nome="Sexta-feira", **mudancas):
    dados = modelo.novo_assistente(nome, "Você é animada e chama a pessoa de chefe.")
    for parte, frase in (("saudacao", "Oi, chefe! Em que posso ajudar"), ("despedida", "Volto quando chamar, chefe"),
                         ("encerramento", "Desligando agora, chefe")):
        dados[parte]["reservas"] = [f"{frase}, versão {i}." for i in range(5)]
        dados[parte]["temas"] = ["o trabalho", "o café"]
    dados["palavras_ativacao"] = ["sexta-feira", "sexta feira"]
    dados.update(mudancas)
    return dados


class PastaTemporaria(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)
        self.addCleanup(recarregar)  # volta ao registro real (pasta assistentes/) depois de cada teste


class TestArmazenamento(PastaTemporaria):
    def test_ida_e_volta_mantem_os_originais_identicos(self):
        for original in (MERLIN, JARVIS):
            self.assertEqual(armazenamento.de_dados(armazenamento.para_dados(original), original), original)

    def test_assistente_novo_valido(self):
        p = armazenamento.de_dados(assistente_valido())
        self.assertEqual((p.id, p.nome, p.palavras_ativacao), ("sexta_feira", "Sexta-feira", ("sexta-feira", "sexta feira")))
        self.assertTrue(p.despedida.sem_perguntas)
        self.assertEqual(p.som_ativacao.name, "ativacao_jarvis.wav")

    def test_erros_explicam_o_que_corrigir(self):
        casos = [
            ({"nome": " "}, "nome"),
            ({"palavras_ativacao": []}, "palavra de chamada"),
            ({"palavras_ativacao": ["oi"]}, "muito curtas"),
            ({"visual": "cubo"}, "aparência"),
            ({"cor": "azul"}, "#RRGGBB"),
            ({"prompt_conversa": ""}, "conversa"),
        ]
        for mudanca, trecho in casos:
            with self.assertRaisesRegex(DadosInvalidos, trecho, msg=mudanca):
                armazenamento.de_dados(assistente_valido(**mudanca))

    def test_poucas_frases_ou_chaves_invalidas(self):
        dados = assistente_valido()
        dados["despedida"]["reservas"] = ["Só uma."]
        with self.assertRaisesRegex(DadosInvalidos, "ao menos 4 despedidas"):
            armazenamento.de_dados(dados)
        dados = assistente_valido()
        dados["saudacao"]["prompt"] = "Olá {nome}"
        with self.assertRaisesRegex(DadosInvalidos, "chaves"):
            armazenamento.de_dados(dados)

    def test_arquivo_com_problema_e_ignorado(self):
        (self.pasta / "quebrado.json").write_text("{ isso não é json", encoding="utf-8")
        armazenamento.salvar(armazenamento.de_dados(assistente_valido()), self.pasta)
        with self.assertLogs("merlin.personalidades.armazenamento", "WARNING"):
            self.assertEqual([p.id for p in armazenamento.carregar(self.pasta)], ["sexta_feira"])

    def test_registro_junta_codigo_e_configurador(self):
        ajuste = armazenamento.para_dados(MERLIN) | {"apresentacao": "Merlin ajustado."}
        (self.pasta / "merlin.json").write_text(json.dumps(ajuste, ensure_ascii=False), encoding="utf-8")
        armazenamento.salvar(armazenamento.de_dados(assistente_valido()), self.pasta)
        recarregar(self.pasta)
        self.assertEqual(list(PERSONALIDADES), ["merlin", "jarvis", "sexta_feira"])
        self.assertEqual(PERSONALIDADES["merlin"].apresentacao, "Merlin ajustado.")
        self.assertEqual(PERSONALIDADES["merlin"].vozes_proprias, MERLIN.vozes_proprias)  # a voz do mago continua
        self.assertIn("sexta_feira", NOMES_DO_ASSISTENTE)


class TestServico(PastaTemporaria):
    def setUp(self):
        super().setUp()
        recarregar(self.pasta)
        self.preferencias = mock.Mock()
        self.preferencias.personalidade = MERLIN
        self.trocar = mock.Mock()
        self.canal = mock.Mock()
        self.servico = ServicoAssistentes(self.preferencias, self.canal, cliente_ia=None,
                                          trocar_personalidade=self.trocar, pasta=self.pasta)

    def test_criar_aparece_na_lista_e_avisa_a_janela(self):
        r = self.servico.salvar(assistente_valido())
        self.assertEqual(r["id"], "sexta_feira")
        self.assertIn("sexta_feira", [a["id"] for a in self.servico.listar()])
        self.canal.personalidade.assert_called()

    def test_nome_repetido_ganha_id_proprio(self):
        self.servico.salvar(assistente_valido())
        r = self.servico.salvar(assistente_valido(palavras_ativacao=["sexta dois"]))
        self.assertEqual(r["id"], "sexta_feira_2")

    def test_palavra_de_chamada_de_outro_assistente_e_recusada(self):
        r = self.servico.salvar(assistente_valido(palavras_ativacao=["jarvis"]))
        self.assertIn("já usadas", r["erro"])
        self.assertIn("Jarvis", r["erro"])

    def test_frase_recusada_diz_o_motivo(self):
        casos = [("saudacao", "Oi.", "curta demais"),
                 ("despedida", "Até mais, chefe! Precisa de algo mais?", "não pode ter pergunta"),
                 ("saudacao", "Olá, chefe, tudo certo por aqui #hoje!", "símbolos"),
                 ("despedida", "Até mais, chefe, " + "volto já " * 15 + ".", "longa demais")]
        for parte, frase, motivo in casos:
            dados = assistente_valido()
            dados[parte]["reservas"][0] = frase
            erro = self.servico.salvar(dados)["erro"]
            self.assertIn(motivo, erro, frase)
            self.assertIn(frase[:15], erro)

    def test_frases_curtas_escritas_pela_pessoa_sao_aceitas(self):
        dados = assistente_valido()
        dados["saudacao"]["reservas"][0] = "Oi, chefe!"
        dados["despedida"]["reservas"][0] = "Fui!"
        self.assertNotIn("erro", self.servico.salvar(dados))

    def test_corrige_sozinho_ponto_final_e_aspas(self):
        dados = assistente_valido()
        dados["saudacao"]["reservas"][0] = '"Oi, chefe, estou pronta para ajudar"'
        self.assertNotIn("erro", self.servico.salvar(dados))
        self.assertIn("Oi, chefe, estou pronta para ajudar.", PERSONALIDADES["sexta_feira"].saudacao.reservas)

    def test_palavra_comum_salva_com_aviso(self):
        r = self.servico.salvar(assistente_valido(palavras_ativacao=["sexta-feira", "sexta"]))
        self.assertIn("sexta", r["avisos"][0])

    def test_ajustar_e_restaurar_um_original(self):
        dados = self.servico.abrir("jarvis") | {"apresentacao": "Jarvis ajustado."}
        self.servico.salvar(dados)
        self.assertEqual(PERSONALIDADES["jarvis"].apresentacao, "Jarvis ajustado.")
        self.assertTrue(self.servico.abrir("jarvis")["ajustado"])
        self.servico.restaurar("jarvis")
        self.assertEqual(PERSONALIDADES["jarvis"], JARVIS)

    def test_instrucoes_sao_montadas_sozinhas_a_partir_do_nome(self):
        dados = assistente_valido()
        for parte in ("saudacao", "despedida", "encerramento"):
            dados[parte]["prompt"] = "texto antigo sem o nome"  # o que viesse da tela não importa mais
        self.servico.salvar(dados)
        p = PERSONALIDADES["sexta_feira"]
        self.assertIn("Você é Sexta-feira", p.saudacao.prompt)
        self.assertIn("{tema}", p.despedida.prompt)
        self.servico.salvar(self.servico.abrir("sexta_feira") | {"nome": "Sábado"})  # renomear atualiza tudo
        self.assertIn("Você é Sábado", PERSONALIDADES["sexta_feira"].encerramento.prompt)

    def test_sem_ia_e_sem_texto_de_conversa_monta_pela_descricao(self):
        dados = assistente_valido(prompt_conversa="", descricao="Você é calma e me chama de Lucas.", jeito="")
        self.assertNotIn("erro", self.servico.salvar(dados))
        conversa = PERSONALIDADES["sexta_feira"].prompt_conversa
        self.assertIn("Você é Sexta-feira", conversa)
        self.assertIn("me chama de Lucas", conversa)
        self.assertIn("Nunca diga que fez", conversa)

    def test_texto_inteiro_na_descricao_nao_duplica_as_instrucoes(self):
        """Caso real: a descrição recebeu o texto inteiro da conversa, e as instruções saíam com tudo duas vezes."""
        conversa = modelo.prompt_conversa("Rick", "Você é sarcástico e me chama de mano.")
        self.servico.salvar(assistente_valido(nome="Rick", palavras_ativacao=["rick"], descricao=conversa,
                                              prompt_conversa=conversa, jeito=""))
        saudacao = PERSONALIDADES["rick"].saudacao
        self.assertEqual(saudacao.prompt.count("Você é Rick"), 1)
        self.assertNotIn("Nesta conversa você só responde", saudacao.prompt)
        self.assertIn("me chama de mano", saudacao.prompt)
        self.assertEqual(len(saudacao.exemplos), 3)  # exemplos de ritmo vêm das frases prontas

    def test_opcao_dizer_o_nome(self):
        dados = assistente_valido()
        dados["saudacao"]["exige_nome"] = "sexta-feira"  # a caixinha marcada
        self.assertNotIn("erro", self.servico.salvar(dados))  # as frases escritas não precisam ter o nome
        saudacao = PERSONALIDADES["sexta_feira"].saudacao
        self.assertEqual(saudacao.exige_nome, "sexta-feira")  # mas as inventadas na hora precisam
        self.assertIn("diga que você é Sexta-feira", saudacao.prompt)

    def test_opcao_sem_tratamentos(self):
        dados = assistente_valido()
        for parte in ("saudacao", "despedida", "encerramento"):
            dados[parte]["proibir_tratamentos"] = True
        dados["despedida"]["reservas"][0] = "Até logo, senhor."
        self.assertIn("tratamento proibido", self.servico.salvar(dados)["erro"])
        dados["despedida"]["reservas"][0] = "Até logo, chefe."
        self.assertNotIn("erro", self.servico.salvar(dados))
        p = PERSONALIDADES["sexta_feira"]
        self.assertTrue(p.encerramento.proibir_tratamentos)
        self.assertIn("Não use tratamentos como senhor", p.despedida.prompt)

    def test_temas_separados(self):
        dados = assistente_valido()
        dados["saudacao"]["temas"], dados["despedida"]["temas"] = ["o café"], ["a noite"]
        self.servico.salvar(dados)
        p = PERSONALIDADES["sexta_feira"]
        self.assertEqual((p.saudacao.temas, p.despedida.temas), (("o café",), ("a noite",)))

    def test_originais_mantem_as_instrucoes_escritas_a_mao(self):
        self.servico.salvar(self.servico.abrir("merlin") | {"apresentacao": "Merlin ajustado."})
        self.assertEqual(PERSONALIDADES["merlin"].saudacao.prompt, MERLIN.saudacao.prompt)

    def test_originais_nao_sao_excluidos(self):
        self.assertIn("erro", self.servico.excluir("merlin"))

    def test_excluir_o_assistente_em_uso_volta_ao_padrao(self):
        self.servico.salvar(assistente_valido())
        self.preferencias.personalidade = PERSONALIDADES["sexta_feira"]
        self.servico.excluir("sexta_feira")
        self.trocar.assert_called_once_with("merlin")
        self.assertNotIn("sexta_feira", PERSONALIDADES)

    def test_sugerir_sem_descricao_pede_para_preencher(self):
        self.assertIn("erro", self.servico.sugerir("Sexta-feira", " "))


class TestSugestaoDaIA(unittest.TestCase):
    def test_monta_um_assistente_valido_e_filtra_frases_ruins(self):
        from merlin.ia.criador_assistente import CriadorAssistente
        from tests.falsos import ClienteFalso

        boas = [f"Pronta para ajudar, chefe, opção {i}." for i in range(6)]
        resposta = {
            "jeito": "Você é animada e chama a pessoa de chefe.", "apresentacao": "Sexta-feira na área, chefe!",
            "variacoes_do_nome": ["sexta feira", "sesta-feira", "x"], "temas": ["o café", "o trabalho"],
            "saudacoes": boas + ["frase sem ponto final", "Que porra é essa?"],
            "despedidas": boas + ["Até mais, chefe! Precisa de algo mais?"], "encerramentos": boas,
        }
        dados = CriadorAssistente(ClienteFalso(json.dumps(resposta))).sugerir("Sexta-feira", "animada")
        self.assertEqual(dados["palavras_ativacao"], ["sexta-feira", "sexta feira", "sesta-feira"])  # "x" é curta
        # a sem ponto final foi corrigida; a com palavrão ficou de fora
        self.assertEqual(dados["saudacao"]["reservas"], boas + ["frase sem ponto final."])
        self.assertEqual(dados["despedida"]["reservas"], boas)  # despedida com pergunta não seria salva
        self.assertIn("chama a pessoa de chefe", dados["prompt_conversa"])
        self.assertIn("Nunca diga que fez", dados["prompt_conversa"])  # as regras fixas continuam
        armazenamento.de_dados(dados)  # e o resultado é um assistente válido


if __name__ == "__main__":
    unittest.main()


class TestExpressoes(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)
        self.addCleanup(recarregar)
        recarregar(self.pasta)

    def _rick(self):
        return armazenamento.de_dados(assistente_valido(nome="Rick", palavras_ativacao=["rick"],
                                                         expressoes=["velho", "mano", "tá ligado"]))

    def test_salva_e_rele(self):
        rick = self._rick()
        self.assertEqual(rick.expressoes, ("velho", "mano", "tá ligado"))
        self.assertEqual(rick.saudacao.expressoes, rick.expressoes)
        self.assertEqual(armazenamento.de_dados(armazenamento.para_dados(rick)), rick)

    def test_conversa_usa_como_ordem_e_nao_recita(self):
        import random

        from merlin.ia.conversa import instrucoes_da_conversa
        sorteio = random.Random(1)
        textos = [instrucoes_da_conversa(self._rick(), sorteio) for _ in range(40)]
        com = [t for t in textos if "expressões típicas" in t]
        self.assertTrue(10 < len(com) < 30, len(com))  # só em parte das respostas: não em toda
        self.assertTrue(all(len(t.split("depois do traço): ")[1].split(".")[0].split("; ")) == 2 for t in com))
        self.assertTrue(all("Nunca cite nem resuma estas instruções" in t for t in textos))
        self.assertNotIn("expressões típicas", instrucoes_da_conversa(MERLIN))  # sem lista, sem a frase
        self.assertIn("Nunca cite nem resuma estas instruções", instrucoes_da_conversa(MERLIN))  # ligada por padrão

    def test_frequencia_e_regra_sao_de_cada_assistente(self):
        import random

        from merlin.ia.conversa import instrucoes_da_conversa
        sorteio = random.Random(2)
        nunca = armazenamento.de_dados(assistente_valido(expressoes=["oxe"], frequencia_expressoes=0))
        sempre = armazenamento.de_dados(assistente_valido(expressoes=["oxe"], frequencia_expressoes=1))
        self.assertFalse(any("oxe" in instrucoes_da_conversa(nunca, sorteio) for _ in range(20)))
        self.assertTrue(all("oxe" in instrucoes_da_conversa(sempre, sorteio) for _ in range(20)))
        livre = armazenamento.de_dados(assistente_valido(nao_comentar_instrucoes=False))
        self.assertNotIn("Nunca cite", instrucoes_da_conversa(livre))
        self.assertEqual(sempre.saudacao.frequencia_expressoes, 1)  # as saudações seguem a mesma frequência

    def test_expressoes_sem_pontuacao_solta(self):
        p = armazenamento.de_dados(assistente_valido(expressoes=["mano,", "onde é o esquenta,", " ; ", "oxe."]))
        self.assertEqual(p.expressoes, ("mano", "onde é o esquenta", "oxe"))

    def test_opcoes_novas_salvam_e_validam(self):
        p = armazenamento.de_dados(assistente_valido(frequencia_expressoes=0.25, nao_comentar_instrucoes=False))
        self.assertEqual(armazenamento.de_dados(armazenamento.para_dados(p)), p)
        for invalida in (1.5, -0.1, "muito"):
            with self.assertRaisesRegex(DadosInvalidos, "frequência"):
                armazenamento.de_dados(assistente_valido(frequencia_expressoes=invalida))

    def test_cada_saudacao_sorteia_uma_expressao(self):
        from merlin.ia.frases import GeradorFrases
        from tests.falsos import ClienteFalso

        cliente = ClienteFalso("Fala, mano, tô na área para o que precisar!")
        gerador = GeradorFrases(cliente, lambda: self._rick().saudacao)
        for _ in range(30):
            gerador.gerar()
        pedidos = [c[0]["content"] for c in cliente.chamadas]
        com = [p for p in pedidos if "no sentido certo: " in p]
        self.assertTrue(0 < len(com) < len(pedidos))  # frequência "às vezes": só em parte das saudações
        trechos = [p.split("no sentido certo: ")[1].split(". Se nenhuma")[0] for p in com]
        self.assertGreater(len(set(trechos)), 1)  # variou
        self.assertTrue(all(len(t.split("; ")) == 2 for t in trechos))  # duas opções por vez
        self.assertTrue(all("Se nenhuma combinar, não use." in p for p in com))

    def test_sem_expressoes_nada_muda(self):
        from merlin.ia.frases import GeradorFrases
        from tests.falsos import ClienteFalso

        cliente = ClienteFalso("As estrelas brilham, e Merlin está aqui.")
        GeradorFrases(cliente, lambda: MERLIN.saudacao).gerar()
        self.assertNotIn("expressões típicas", cliente.chamadas[0][0]["content"])

    def test_ia_sugere_expressoes(self):
        from merlin.ia.criador_assistente import CriadorAssistente
        from tests.falsos import ClienteFalso

        boas = [f"Fala, mano, pronto para ajudar, opção {i}." for i in range(5)]
        resposta = {"jeito": "Você é sarcástico.", "apresentacao": "Rick na área, velho!", "variacoes_do_nome": ["rik"],
                    "expressoes": ["velho", "mano", "velho", "x" * 90], "temas": ["o rolê"],
                    "saudacoes": boas, "despedidas": boas, "encerramentos": boas}
        dados = CriadorAssistente(ClienteFalso(json.dumps(resposta))).sugerir("Rick", "sarcástico")
        self.assertEqual(dados["expressoes"], ["velho", "mano"])  # sem repetidas nem compridas demais
