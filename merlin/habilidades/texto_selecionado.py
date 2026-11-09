"""Texto selecionado: corrige, traduz, resume, explica ou responde o texto selecionado em qualquer programa."""
import re

from merlin.habilidades import grupos
from merlin.habilidades.base import Correcao, Exemplo, Habilidade

# O pedido precisa apontar para algo que está na tela. "Resume a história do Brasil" é conversa.
APONTA_PARA_A_TELA = re.compile(r"\b(?:isso|isto|disso|nisso|esse|essa|este|esta|desse|dessa|deste|desta|nesse|nessa|"
                                r"selecion\w*|sele[çc][ãa]o|copi\w*|trecho)\b", re.IGNORECASE)
# Um verbo de editar texto seguido do que será editado: "responde essa mensagem...". A IA às vezes chama de conversa.
PEDIDO_CLARO = re.compile(r"^(?:por favor,?\s+|me\s+)?(?:respond\w*|corrig\w*|corrij\w*|traduz\w*|resum\w*|reescrev\w*|"
                          r"melhor\w*|explic\w*)\s+(?:(?:[ao]|ess[ae]|est[ae])\s+)(?:mensagem|texto|e-?mail|"
                          r"par[aá]grafo|trecho|frase)\b", re.IGNORECASE)


def e_pedido_claro(comando: str) -> bool:
    return bool(PEDIDO_CLARO.search(comando) and APONTA_PARA_A_TELA.search(comando))


def regra(leitura):
    if not APONTA_PARA_A_TELA.search(leitura.comando):
        return Correcao("conversar", "a frase não aponta para um texto na tela")
    return None


def criar_acao(recursos):
    from merlin.acoes.selecao import TextoSelecionado
    return TextoSelecionado(recursos.cliente_ia, recursos.sessao, recursos.memoria, canal=recursos.canal)


HABILIDADE = Habilidade(
    nome="texto_selecionado",
    titulo="Usar o texto selecionado",
    resumo="Corrige, traduz, resume ou responde o texto que você selecionou.",
    icone="📝",
    regras_resumo=(
        'Precisa apontar para a tela (“isso”, “esse texto”, “o selecionado”); senão, vira conversa.',
        'Com texto selecionado, o resultado sempre substitui a seleção, seja qual for o pedido.',
        'Onde não dá para escrever, como uma página da web, o resultado vai para o cartão, com os botões.',
        'Sem seleção, usa o que você copiou no último minuto, e o resultado vai para o cartão, com os botões.',
        'O resultado só é lido em voz alta se você pedir (“lê isso para mim”, “resume isso e lê”).',
    ),
    grupo=grupos.TEXTO,
    ordem=35,
    descricao="a pessoa manda fazer algo com um texto que está selecionado na tela: corrigir, traduzir, reescrever, "
              "resumir, explicar, responder ou ler em voz alta, usando palavras como isso, esse texto, esse e-mail ou esse trecho. "
              "O alvo é sempre texto.",
    exemplos=(
        Exemplo("corrige isso", "texto"),
        Exemplo("traduz esse texto para inglês", "texto"),
        Exemplo("resume isso pra mim", "texto"),
        Exemplo("explica esse trecho", "texto"),
        Exemplo("lê isso para mim", "texto"),
        Exemplo("me dá um resumo desse texto", "texto"),
        Exemplo("deixa isso mais formal", "texto"),
        Exemplo("responde esse email dizendo que aceito", "texto"),
        Exemplo("resume a história do brasil", "história do brasil", intencao="conversar"),
        Exemplo("traduz bom dia para inglês", "bom dia", intencao="conversar"),
    ),
    regra=regra,
    mexe_no_computador=True,
    frase_inteira=True,
    criar_acao=criar_acao,
)
