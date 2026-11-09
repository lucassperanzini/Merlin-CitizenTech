"""Gerar script: a IA escreve um script e o guarda na aba Automações, com a explicação."""
import re

from merlin.habilidades import grupos
from merlin.habilidades.base import Correcao, Exemplo, Habilidade

PEDE_SCRIPT = re.compile(r"\b(?:e?scripts?|python|c[oó]digo|programa\s+(?:que|para|pra))\b", re.IGNORECASE)


def regra(leitura):
    if not PEDE_SCRIPT.search(leitura.comando):
        return Correcao("conversar", "a frase não pede um script")
    return None


def criar_acao(recursos):
    from merlin.acoes.gerar_script import criar
    return criar(recursos)


HABILIDADE = Habilidade(
    nome="gerar_script",
    titulo="Gerar script",
    resumo="Escreve um script para o que você pedir e explica o que ele faz. Só roda se você clicar em Executar.",
    icone="📜",
    regras_resumo=(
        'Você precisa dizer “script”, “código”, “python” ou “programa que…”.',
        'O script fica na aba Automações, com a explicação, os avisos e o botão para escolher a pasta.',
        'Scripts que mexem em arquivos existentes, abrem programas ou usam a internet são recusados.',
    ),
    grupo=grupos.SCRIPTS,
    ordem=27,
    descricao="a pessoa manda escrever, criar ou gerar um script, código em python ou programa que faça alguma tarefa. "
              "O alvo é a tarefa. Abrir um programa que já existe não é este pedido.",
    exemplos=(
        Exemplo("cria um script que lista os maiores arquivos de uma pasta", "listar maiores arquivos"),
        Exemplo("escreve um código em python que gera uma planilha com os nomes dos arquivos", "planilha com nomes"),
        Exemplo("faz um programa que mostra o espaço de cada pasta", "espaço de cada pasta"),
        Exemplo("abre o programa word", "word", intencao="abrir_programa"),
        Exemplo("o que é um script", "script", intencao="conversar"),
    ),
    regra=regra,
    frase_inteira=True,
    criar_acao=criar_acao,
)
