"""Ver botões: diz quais botões aparecem na janela de um programa. Só informa, não clica."""
from merlin.habilidades import grupos
from merlin.habilidades.base import Habilidade


def criar_acao(recursos):
    from merlin.acoes.ver_botoes import VerBotoes
    return VerBotoes(recursos.raciocinio)


HABILIDADE = Habilidade(
    nome="ver_botoes",
    grupo=grupos.TELA,
    ordem=40,
    descricao="a pessoa pergunta quais botões ou opções aparecem na tela ou em um programa aberto. "
              "O alvo é o programa citado, ou \"merlin\" se não citar nenhum.",
    mexe_no_computador=True,
    criar_acao=criar_acao,
)
