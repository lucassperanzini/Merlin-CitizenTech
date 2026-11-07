"""Encerrar: o assistente se despede e fecha o programa de vez (para de escutar)."""
from merlin.habilidades import grupos
from merlin.habilidades.base import ALVO_ASSISTENTE, Exemplo, Habilidade
from merlin.habilidades.dispensar import so_sobre_o_assistente


def criar_acao(recursos):
    from merlin.acoes.sessao import Encerrar
    from merlin.ia.frases import GeradorFrases
    return Encerrar(recursos.estado,
                    GeradorFrases(recursos.cliente_ia, lambda: recursos.preferencias.personalidade.encerramento))


HABILIDADE = Habilidade(
    nome="encerrar",
    titulo='Desligar o assistente',
    regras_resumo=(
        'Só vale se a frase for para o próprio assistente: “desliga a TV” vira conversa.',
    ),
    grupo=grupos.ASSISTENTE,
    ordem=11,
    descricao="a pessoa pede claramente para fechar o programa do assistente por completo ou desligá-lo de vez, "
              "para ele parar de escutar.",
    exemplos=(
        Exemplo("finaliza o programa", ALVO_ASSISTENTE),
        Exemplo("fecha o programa", ALVO_ASSISTENTE),
        Exemplo("quero você desligado de vez", ALVO_ASSISTENTE),
    ),
    regra=so_sobre_o_assistente,
    criar_acao=criar_acao,
)
