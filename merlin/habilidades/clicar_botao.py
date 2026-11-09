"""Clicar em botão: aperta um botão ou opção de um programa aberto (pergunta antes nos perigosos)."""
from merlin.habilidades import grupos
from merlin.habilidades.base import Campo, Correcao, Exemplo, Habilidade
from merlin.habilidades.frases import comeca_com
from merlin.personalidades import NOMES_DO_ASSISTENTE

# Clicar exige uma ordem: a frase precisa começar pelo verbo, e não por uma pergunta.
# Além de "clica" e "aperta", valem os verbos que já dizem qual botão é ("dá play", "salva", "pula").
VERBO_CLICAR = comeca_com(
    r"clic[ae]|clique|clicar|apert[ae]|apertar|pression[ae]|pressionar|"
    r"d[aá] um clique|toc[ae]|toque|tocar|selecion[ae]|selecionar|marc[ae]|marcar|aciona|acione|acionar|"
    r"d[aá]\s+(?:um\s+)?(?:play|pause|pausa|ok|enter)|play|pause|paus[ae]|pausar|"
    r"salv[ae]|salvar|confirm[ae]|confirmar|cancel[ae]|cancelar|envi[ae]|enviar|"
    r"avan[cç][ae]|avan[cç]ar|pul[ae]|pular|volt[ae]|voltar|aceit[ae]|aceitar|continu[ae]|continuar|"
    r"escolh[ae]|escolher"
)


def regra(leitura):
    if not VERBO_CLICAR.match(leitura.comando):
        return Correcao("conversar", "a frase não começa com uma ordem de clicar: é pergunta ou comentário")
    if leitura.alvo.lower() in NOMES_DO_ASSISTENTE:
        # "clica num botão" sem dizer qual: a ação pergunta qual é, em vez de deixar a IA adivinhar
        return Correcao("clicar_botao", "pediu um clique sem dizer qual botão", alvo="")
    return None


def criar_acao(recursos):
    from merlin.acoes.clicar import ClicarBotao
    from merlin.ia.escolha_botao import EscolhedorBotao
    return ClicarBotao(recursos.sessao, EscolhedorBotao(recursos.cliente_ia), recursos.raciocinio)


HABILIDADE = Habilidade(
    nome="clicar_botao",
    titulo='Clicar em botão',
    resumo="Clica em um botão da janela que você está usando.",
    icone="🖱️",
    regras_resumo=(
        'A frase precisa começar com uma ordem (clica, aperta, dá play, salva, pula…); perguntas viram conversa.',
        'Sem dizer qual botão, o assistente pergunta “Em qual botão?”.',
        'Botões perigosos (excluir, pagar, enviar…) ou escolhidos pela IA pedem confirmação antes.',
    ),
    grupo=grupos.TELA,
    ordem=41,
    descricao="a pessoa manda clicar, apertar ou pressionar um botão ou opção de um programa, ou manda fazer algo que "
              "é apertar um botão (dar play, pausar, salvar, confirmar, enviar, pular, avançar, voltar). O alvo é o "
              "nome do botão, sem a palavra botão. Em local, o programa, se ela citar; se não citar, deixe vazio: o "
              "clique é no programa que está em uso.",
    campos=(Campo("local", "o programa onde clicar, se a frase disser"),),
    exemplos=(
        Exemplo("clica em imprimir", "imprimir"),
        Exemplo("aperta o botão cancelar no paint", "cancelar", campos={"local": "paint"}),
        Exemplo("dá play", "play"),
        Exemplo("pausa a música no spotify", "pausar", campos={"local": "spotify"}),
        Exemplo("pula pra próxima", "próxima"),
        Exemplo("salva o arquivo", "salvar"),
        Exemplo("pode clicar em enviar", "enviar"),
        Exemplo("seleciona a opção não salvar", "não salvar"),
        Exemplo("confirma no whatsapp", "confirmar", campos={"local": "whatsapp"}),
        Exemplo("volta pra página anterior no chrome", "voltar", campos={"local": "chrome"}),
        Exemplo("o que acontece se eu clicar em formatar", "formatar", intencao="conversar"),
        Exemplo("vale a pena salvar em pdf", "pdf", intencao="conversar"),
    ),
    regra=regra,
    mexe_no_computador=True,
    criar_acao=criar_acao,
)
