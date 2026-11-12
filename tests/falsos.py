"""Substitutos simples para testar a lógica sem microfone, caixas de som, janela ou IA."""
from merlin.ia.confirmacao import RespostaConfirmacao


class LocutorFalso:
    def __init__(self):
        self.falas = []

    def falar(self, texto):
        self.falas.append(texto)


class CanalFalso:
    def __init__(self):
        self.eventos = []

    def mostrar(self):
        self.eventos.append("mostrar")

    def esconder(self):
        self.eventos.append("esconder")

    def estado(self, estado):
        self.eventos.append(estado.value)

    def legenda(self, texto):
        self.eventos.append(texto)

    def rascunho(self, texto):
        self.eventos.append(f"rascunho: {texto}")

    def aviso(self, texto):
        self.eventos.append(f"aviso: {texto}")


class ClienteFalso:
    """Devolve sempre a resposta configurada e guarda o que recebeu."""

    def __init__(self, resposta=""):
        self.resposta = resposta
        self.chamadas = []

    def perguntar(self, mensagens, formato=None, opcoes=None):
        self.chamadas.append(mensagens)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


class DivisorFalso:
    """Por padrão, a frase inteira é uma tarefa só."""

    def __init__(self, tarefas=None):
        self.tarefas = tarefas

    def dividir(self, comando):
        return self.tarefas if self.tarefas is not None else [comando]


class ClassificadorFalso:
    def __init__(self, intencao=None, erro=None):
        self.intencao = intencao
        self.erro = erro
        self.comandos = []

    def classificar(self, comando):
        self.comandos.append(comando)
        if self.erro:
            raise self.erro
        return self.intencao


class ConfirmadorFalso:
    def __init__(self, resposta=RespostaConfirmacao.OUTRO):
        self.resposta = resposta

    def classificar(self, pergunta, comando):
        return self.resposta


class SaudacaoFalsa:
    def gerar(self):
        return "saudação"


# --- Assistentes de teste: o projeto vem com um assistente original só (o Merlin)
def assistente_de_teste(nome="Sexta-feira", **mudancas):
    """Os dados de um assistente novo, válido, como o Editor da Central salvaria."""
    from merlin.personalidades import modelo
    dados = modelo.novo_assistente(nome, "Você é animada e chama a pessoa de chefe.")
    for parte, frase in (("saudacao", "Oi, chefe! Em que posso ajudar"), ("despedida", "Volto quando chamar, chefe")):
        dados[parte]["reservas"] = [f"{frase}, versão {i}." for i in range(5)]
        dados[parte]["temas"] = ["o trabalho", "o café"]
    dados["palavras_ativacao"] = ["sexta-feira", "sexta feira"]
    dados.update(mudancas)
    return dados


def com_segundo_assistente(teste):
    """Registra a Sexta-feira (id "sexta_feira") ao lado do Merlin só durante o teste, para testar trocas."""
    import tempfile
    from pathlib import Path

    from merlin.personalidades import armazenamento, recarregar
    pasta = tempfile.TemporaryDirectory()
    teste.addCleanup(pasta.cleanup)
    teste.addCleanup(recarregar)  # volta ao registro real depois do teste
    armazenamento.salvar(armazenamento.de_dados(assistente_de_teste()), Path(pasta.name))
    recarregar(Path(pasta.name))


def assistente_mago():
    """O antigo Merlin mago, guardado só para os testes: as regras das frases dele (exigir o nome, não chamar de
    senhor) continuam valendo para os assistentes criados no Editor."""
    import json
    from pathlib import Path

    from merlin.personalidades import armazenamento
    dados = json.loads((Path(__file__).parent / "assistente_mago.json").read_text(encoding="utf-8"))
    return armazenamento.de_dados(dados)
