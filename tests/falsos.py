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
