"""Abrir pasta: abre uma pasta do computador no Explorador de Arquivos (Downloads, Documentos, um disco ou
qualquer pasta pelo nome)."""
import re

from merlin.habilidades import grupos
from merlin.habilidades.base import Correcao, Exemplo, Habilidade
from merlin.habilidades.frases import PERGUNTA


# Outras coisas que se faz com uma pasta, e que o assistente não faz: só abrir. Só o verbo do pedido conta (o começo
# da frase): uma pasta chamada "Movies" ou "Novas fotos" pode ser aberta normalmente.
OUTRAS_ACOES = re.compile(r"^(?:por favor,?\s+|(?:voc[eê]\s+)?pode\s+|me\s+)?"
                          r"((?:cri|faz|fa[çc]|apag|delet|exclu|remov|renome|mov|mud|copi|compact|zip)\w*)",
                          re.IGNORECASE)


def regra(leitura):
    acao = OUTRAS_ACOES.search(leitura.comando)
    if acao:
        return Correcao("conversar", f"“{acao.group(1)}” uma pasta não é abrir: isso eu ainda não sei fazer")
    if PERGUNTA.match(leitura.comando):
        return Correcao("conversar", "a frase é uma pergunta, não uma ordem")  # "onde fica a pasta downloads?"
    if not leitura.alvo:
        return Correcao("conversar", "abrir pasta precisa do nome da pasta")
    return None


def criar_acao(recursos):
    from merlin.acoes import pastas
    # Os da aba Pastas da Central (sem preferências, como em alguns testes, não há apelidos)
    pastas.definir_apelidos(lambda: getattr(recursos.preferencias, "apelidos_pastas", None) or [])
    return pastas.AbrirPasta()


HABILIDADE = Habilidade(
    nome="abrir_pasta",
    titulo="Abrir pasta",
    resumo="Abre uma pasta ou um disco no Explorador de Arquivos.",
    icone="📁",
    regras_resumo=(
        'Perguntas (“onde fica a pasta downloads?”) viram conversa.',
        'Criar, apagar, renomear, mover ou copiar uma pasta vira conversa: ele só abre.',
        'Procura primeiro nos seus apelidos (aba Pastas) e no Acesso Rápido do Windows; depois pelo nome, na pasta '
        'do usuário e nos outros discos, até 3 níveis de profundidade.',
    ),
    grupo=grupos.PROGRAMAS,
    ordem=22,
    descricao="a pessoa manda abrir uma pasta do computador: downloads, documentos, área de trabalho, imagens, "
              "músicas, vídeos, uma unidade de disco, um atalho de pasta dela ou uma pasta pelo nome. "
              "O alvo é só o nome da pasta.",
    exemplos=(
        Exemplo("abre a pasta downloads", "downloads"),
        Exemplo("abre meus documentos", "documentos"),
        Exemplo("abre a pasta fotos da viagem", "fotos da viagem"),
        Exemplo("abre o disco d", "disco d"),
        Exemplo("abre o explorador de arquivos", "explorador de arquivos", intencao="abrir_programa"),
        Exemplo("cria uma pasta chamada contas", "contas", intencao="conversar"),
    ),
    regra=regra,
    mexe_no_computador=True,
    criar_acao=criar_acao,
)
