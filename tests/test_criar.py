import json
import tempfile
import unittest
from pathlib import Path

from merlin.acoes.criar import CriarArquivo, CriarPasta
from merlin.acoes.locais import LocaisPermitidos, LocalNaoPermitido, NomeInvalido, PastaPessoal, validar_nome
from merlin.ia.intencoes import ClassificadorIntencao, Intencao, TipoIntencao
from tests.falsos import ClienteFalso


class Base(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.raiz = Path(temporaria.name).resolve()
        self.mesa = self.raiz / "Desktop"
        self.docs = self.raiz / "Documents"
        self.fora = self.raiz / "Fora"
        for pasta in (self.mesa, self.docs, self.fora):
            pasta.mkdir()
        self.locais = LocaisPermitidos([
            PastaPessoal("Área de Trabalho", self.mesa, ("area de trabalho", "desktop")),
            PastaPessoal("Documentos", self.docs, ("documentos", "meus documentos")),
        ])


class TestValidarNome(unittest.TestCase):
    def test_nomes_validos(self):
        casos = {"Projetos": "Projetos", " notas.txt ": "notas.txt", "notas ponto txt": "notas.txt",
                 "relatório final": "relatório final", "fim.": "fim"}
        for nome, esperado in casos.items():
            self.assertEqual(validar_nome(nome), esperado, nome)

    def test_nomes_invalidos(self):
        for nome in ("", "  ", ".", "..", "a/b", "a\\b", "c:", "x?y", "a*b", 'a"b', "con", "CON.txt", "nul", "com1", "lpt9.log"):
            with self.assertRaises(NomeInvalido, msg=nome):
                validar_nome(nome)


class TestLocais(Base):
    def test_sem_local_usa_o_padrao(self):
        self.assertEqual(self.locais.resolver(""), self.mesa)

    def test_apelidos_sem_diferenciar_acentos(self):
        self.assertEqual(self.locais.resolver("Área de Trabalho"), self.mesa)
        self.assertEqual(self.locais.resolver("meus documentos"), self.docs)

    def test_pasta_existente_e_encontrada_nas_pastas_pessoais(self):
        (self.docs / "Projetos").mkdir()
        self.assertEqual(self.locais.resolver("Projetos"), self.docs / "Projetos")
        self.assertEqual(self.locais.resolver("na pasta Projetos"), self.docs / "Projetos")

    def test_pasta_inexistente_fica_no_padrao(self):
        self.assertEqual(self.locais.resolver("Novidades"), self.mesa / "Novidades")

    def test_fora_das_pastas_pessoais_e_recusado(self):
        for local in (r"C:\Windows", r"C:\Windows\System32", str(self.fora), r"..\..\Fora", "../Fora", r"Projetos\..\..\Fora"):
            with self.assertRaises(LocalNaoPermitido, msg=local):
                self.locais.resolver(local)

    def test_dentro_das_pastas_pessoais_e_aceito(self):
        self.assertEqual(self.locais.resolver(str(self.docs / "a")), self.docs / "a")
        self.assertEqual(self.locais.resolver("a/b"), self.mesa / "a" / "b")

    def test_descrever(self):
        self.assertEqual(self.locais.descrever(self.mesa), "Área de Trabalho")
        self.assertEqual(self.locais.descrever(self.docs / "Projetos"), "Projetos, em Documentos")


class TestCriarPasta(Base):
    def _criar(self, alvo, local=""):
        return CriarPasta(self.locais)(Intencao(TipoIntencao.CRIAR_PASTA, alvo, "x", local))

    def test_cria_no_padrao(self):
        r = self._criar("Projetos")
        self.assertTrue((self.mesa / "Projetos").is_dir())
        self.assertEqual(r.fala, "criei a pasta Projetos em Área de Trabalho")

    def test_cria_no_local_pedido(self):
        self._criar("Fotos", "documentos")
        self.assertTrue((self.docs / "Fotos").is_dir())

    def test_existente_nao_e_alterada(self):
        pasta = self.mesa / "Projetos"
        pasta.mkdir()
        (pasta / "guardado.txt").write_text("não mexer", encoding="utf-8")
        r = self._criar("Projetos")
        self.assertEqual((pasta / "guardado.txt").read_text(encoding="utf-8"), "não mexer")
        self.assertIn("já existe", r.fala)

    def test_fora_das_pastas_e_recusado_e_avisado(self):
        r = self._criar("Invasora", str(self.fora))
        self.assertFalse((self.fora / "Invasora").exists())
        self.assertIn("pastas pessoais", r.fala)

    def test_nome_que_tenta_sair_da_pasta_e_recusado(self):
        for nome in (r"..\Fora\x", "../Fora/x", ".."):
            self._criar(nome)
        self.assertEqual(list(self.fora.iterdir()), [])
        self.assertEqual(list(self.mesa.iterdir()), [])


class TestCriarArquivo(Base):
    def _criar(self, alvo, local="", conteudo=""):
        return CriarArquivo(self.locais)(Intencao(TipoIntencao.CRIAR_ARQUIVO, alvo, "x", local, conteudo))

    def test_cria_com_conteudo_e_acentos(self):
        self._criar("compras.txt", conteudo="arroz e feijão")
        self.assertEqual((self.mesa / "compras.txt").read_text(encoding="utf-8"), "arroz e feijão")

    def test_sem_extensao_vira_txt(self):
        self._criar("notas")
        self.assertTrue((self.mesa / "notas.txt").is_file())

    def test_dentro_de_pasta_existente(self):
        (self.docs / "Projetos").mkdir()
        r = self._criar("ideias.md", "pasta Projetos")
        self.assertTrue((self.docs / "Projetos" / "ideias.md").is_file())
        self.assertEqual(r.fala, "criei o arquivo ideias.md em Projetos, em Documentos")

    def test_cria_a_pasta_se_ela_nao_existir(self):
        self._criar("ideias.txt", "Novidades")
        self.assertTrue((self.mesa / "Novidades" / "ideias.txt").is_file())

    def test_nunca_sobrescreve(self):
        arquivo = self.mesa / "notas.txt"
        arquivo.write_text("original", encoding="utf-8")
        r = self._criar("notas.txt", conteudo="novo")
        self.assertEqual(arquivo.read_text(encoding="utf-8"), "original")
        self.assertIn("já existe", r.fala)

    def test_executaveis_e_scripts_sao_bloqueados(self):
        for nome in ("virus.exe", "a.bat", "a.PS1", "a.vbs", "a.js", "a.lnk", "a.reg"):
            self._criar(nome, conteudo="x")
        self.assertEqual(list(self.mesa.iterdir()), [])

    def test_fora_das_pastas_e_recusado(self):
        self._criar("a.txt", str(self.fora))
        self.assertEqual(list(self.fora.iterdir()), [])


class TestIntencaoCriar(unittest.TestCase):
    def _classificar(self, **campos):
        padrao = {"alvo": "x", "intencao": "criar_pasta", "busca": "", "local": "", "conteudo": ""}
        return ClassificadorIntencao(ClienteFalso(json.dumps({**padrao, **campos}))).classificar("frase")

    def test_campos_chegam_a_acao(self):
        i = self._classificar(intencao="criar_arquivo", alvo="a.txt", local="docs", conteudo="oi")
        self.assertEqual((i.tipo, i.alvo, i.local, i.conteudo), (TipoIntencao.CRIAR_ARQUIVO, "a.txt", "docs", "oi"))

    def test_sem_nome_vira_conversa(self):
        for alvo in ("", "merlin"):
            self.assertIs(self._classificar(alvo=alvo).tipo, TipoIntencao.CONVERSAR)

    def _classificar_frase(self, comando, intencao, alvo="downloads"):
        resposta = json.dumps({"alvo": alvo, "intencao": intencao, "busca": "", "local": "", "conteudo": ""})
        return ClassificadorIntencao(ClienteFalso(resposta)).classificar(comando).tipo

    def test_verbo_oposto_nunca_cria(self):
        for frase in ("abre a pasta de downloads", "abra o arquivo notas", "apaga a pasta projetos", "exclui o arquivo notas",
                      "deleta a pasta contas", "remove o arquivo lista", "por favor apague a pasta fotos", "agora abre a pasta"):
            for intencao in ("criar_pasta", "criar_arquivo"):
                self.assertIs(self._classificar_frase(frase, intencao), TipoIntencao.CONVERSAR, frase)

    def test_palavra_no_meio_da_frase_nao_atrapalha_criar(self):
        for frase in ("cria um arquivo lista escrito apagar a luz", "cria uma pasta chamada abre", "faz um arquivo escrito ligar para o banco"):
            self.assertIs(self._classificar_frase(frase, "criar_arquivo"), TipoIntencao.CRIAR_ARQUIVO, frase)

    def test_verbo_de_abrir_nunca_fecha(self):
        for frase in ("liga o obsidian", "abre o chrome", "inicia o discord", "execute o blender", "ligue o steam"):
            self.assertIs(self._classificar_frase(frase, "fechar_programa", "obsidian"), TipoIntencao.ABRIR_PROGRAMA, frase)

    def test_desligar_e_fechar_continuam_fechando(self):
        for frase in ("desliga o obsidian", "fecha o chrome", "encerra o discord", "mata o steam"):
            self.assertIs(self._classificar_frase(frase, "fechar_programa", "obsidian"), TipoIntencao.FECHAR_PROGRAMA, frase)


if __name__ == "__main__":
    unittest.main()
