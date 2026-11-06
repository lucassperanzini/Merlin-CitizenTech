"""Abrir configurações: abre a janela de configurações do próprio assistente."""
import re

from merlin.habilidades import grupos
from merlin.habilidades.base import ALVO_ASSISTENTE, Correcao, Exemplo, Habilidade
from merlin.habilidades.frases import PERGUNTA
from merlin.personalidades import NOMES_DO_ASSISTENTE

CONFIGURACOES_DE_OUTRO = re.compile(
    r"(?:configura\w*|ajustes?|op[cç][oõ]es|prefer[eê]ncias)\s+d[oae]s?\s+(?!seu\b|sua\b|voc)(\w+)", re.IGNORECASE
)
DONOS_DO_SISTEMA = {"windows", "pc", "computador", "sistema", "notebook"}


def regra(leitura):
    """Precisa ser uma ordem, e das configurações do assistente, não de outra coisa."""
    if PERGUNTA.match(leitura.comando):
        return Correcao("conversar", "a frase é uma pergunta, não uma ordem")  # "como abro as configurações do celular?"
    outro = CONFIGURACOES_DE_OUTRO.search(leitura.comando)
    if outro and outro.group(1).lower() not in NOMES_DO_ASSISTENTE:
        dono = outro.group(1)
        if dono.lower() in DONOS_DO_SISTEMA:
            return Correcao("abrir_programa", f"são as configurações do {dono}, não as do assistente",
                            alvo="configurações")
        return Correcao("conversar", f"são as configurações do {dono}, que eu não sei abrir")
    return Correcao("abrir_configuracoes", alvo=ALVO_ASSISTENTE)


def criar_acao(recursos):
    from merlin.acoes.sessao import AbrirConfiguracoes
    return AbrirConfiguracoes(recursos.canal)


HABILIDADE = Habilidade(
    nome="abrir_configuracoes",
    grupo=grupos.ASSISTENTE,
    ordem=12,
    descricao="a pessoa pede para abrir as configurações do próprio assistente, como as suas configurações ou os "
              "ajustes. Configurações do Windows ou de outro programa são abrir_programa.",
    exemplos=(
        Exemplo("abre as suas configurações", ALVO_ASSISTENTE),
    ),
    regra=regra,
    criar_acao=criar_acao,
)
