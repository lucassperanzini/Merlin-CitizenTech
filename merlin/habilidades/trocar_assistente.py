"""Trocar de assistente: passa a usar outra personalidade, que se apresenta com a própria voz."""
from merlin.habilidades import grupos
from merlin.habilidades.base import Correcao, Exemplo, Habilidade
from merlin.habilidades.frases import PERGUNTA


def regra(leitura):
    """Perguntas sobre os assistentes ("quais assistentes você tem?") são conversa, não troca."""
    if PERGUNTA.match(leitura.comando):
        return Correcao("conversar", "a frase é uma pergunta, não um pedido de troca")
    return None


def criar_acao(recursos):
    from merlin.acoes.assistentes import TrocarAssistente
    return TrocarAssistente(recursos.preferencias, recursos.memoria, recursos.canal)


HABILIDADE = Habilidade(
    nome="trocar_assistente",
    titulo="Trocar de assistente",
    resumo="Passa para outro assistente, como Merlin ou Jarvis.",
    icone="🔄",
    regras_resumo=('Perguntas (“quais assistentes você tem?”) viram conversa.',),
    grupo=grupos.ASSISTENTE,
    ordem=13,
    descricao="a pessoa pede para trocar de assistente, mudar para outro assistente ou chamar outro assistente "
              "no lugar deste. O alvo é só o nome do assistente pedido.",
    exemplos=(
        Exemplo("troca para o jarvis", "jarvis"),
        Exemplo("quero falar com o merlin", "merlin"),
        Exemplo("muda o assistente pro jarvis", "jarvis"),
    ),
    regra=regra,
    criar_acao=criar_acao,
)
