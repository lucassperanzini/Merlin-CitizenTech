"""Fechar programa: fecha a janela de um programa aberto, como clicar no X."""
from merlin.habilidades import grupos
from merlin.habilidades.base import ALVO_ASSISTENTE, Correcao, Exemplo, Habilidade
from merlin.habilidades.frases import comeca_com
from merlin.personalidades import NOMES_DO_ASSISTENTE
from merlin.texto import normalizar

# Trava contra a ação oposta: o modelo às vezes confunde "abre" e "liga" com fechar
VERBO_ABRIR = comeca_com(r"abr[ea]|abrir|inici[ae]|iniciar|lig[au]e?|ligar|execut[ae]|executar")
ALVOS_JANELA_DO_ASSISTENTE = {"janela", "essajanela", "estajanela", "ajanela"}


def regra(leitura):
    if VERBO_ABRIR.match(leitura.comando):
        return Correcao("abrir_programa", "a frase começa com um verbo de abrir, não de fechar")
    if normalizar(leitura.alvo) in ALVOS_JANELA_DO_ASSISTENTE:
        return Correcao("dispensar", "fechar esta janela, sem citar programa, é fechar a janela do assistente",
                        alvo=ALVO_ASSISTENTE)
    if leitura.alvo.lower() in NOMES_DO_ASSISTENTE:
        return Correcao("dispensar", "fechar o próprio assistente é dispensá-lo")
    return None


def criar_acao(recursos):
    from merlin.acoes.fechar_programa import FecharPrograma
    return FecharPrograma()


HABILIDADE = Habilidade(
    nome="fechar_programa",
    titulo='Fechar programa',
    resumo="Fecha um programa aberto.",
    icone="❌",
    regras_resumo=(
        'Se a frase começa com abrir, iniciar, ligar ou executar, vira “Abrir programa”.',
        '“Fecha essa janela”, sem citar programa, é dispensar o assistente.',
        'Fechar o próprio assistente é dispensá-lo.',
    ),
    grupo=grupos.PROGRAMAS,
    ordem=20,
    descricao="a pessoa manda fechar, encerrar ou sair de um programa ou janela aberta no computador. "
              "O alvo é o nome do programa.",
    exemplos=(
        Exemplo("feche o word", "word"),
        Exemplo("encerra o navegador", "navegador"),
        Exemplo("sai do outlook", "outlook"),
        Exemplo("como saio do excel", "excel", intencao="conversar"),
    ),
    regra=regra,
    mexe_no_computador=True,
    criar_acao=criar_acao,
)
