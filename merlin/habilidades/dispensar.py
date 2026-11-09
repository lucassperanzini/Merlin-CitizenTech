"""Dispensar: o assistente se despede e volta a esperar ser chamado."""
from merlin.habilidades import grupos
from merlin.habilidades.base import ALVO_ASSISTENTE, Correcao, Exemplo, Habilidade
from merlin.personalidades import NOMES_DO_ASSISTENTE


def so_sobre_o_assistente(leitura):
    """Sair só vale quando o alvo é o próprio assistente: "encerra o discord" não é desligar o assistente."""
    if leitura.alvo.lower() not in NOMES_DO_ASSISTENTE:
        return Correcao("conversar", f"sair só vale quando o alvo é o assistente, e o alvo era '{leitura.alvo}'")
    return None


def criar_acao(recursos):
    from merlin.acoes.sessao import Dispensar
    from merlin.ia.frases import GeradorFrases
    return Dispensar(recursos.sessao, GeradorFrases(recursos.cliente_ia, lambda: recursos.preferencias.personalidade.despedida))


HABILIDADE = Habilidade(
    nome="dispensar",
    titulo='Dispensar o assistente',
    resumo="Manda o assistente de volta para a bolinha.",
    icone="👋",
    regras_resumo=(
        'Só vale se a frase for para o próprio assistente: “encerra o discord” vira conversa.',
    ),
    grupo=grupos.ASSISTENTE,
    ordem=10,
    descricao="a pessoa se despede do Merlin, agradece encerrando a conversa, diz que já terminou ou que não precisa "
              "mais dele, ou manda ele sair, descansar ou desligar, mesmo com gíria ou de forma rude.",
    exemplos=(
        Exemplo("obrigado, pode ir", ALVO_ASSISTENTE),
        Exemplo("terminamos aqui", ALVO_ASSISTENTE),
        Exemplo("vai lá, depois te chamo", ALVO_ASSISTENTE),
        Exemplo("boa noite", ALVO_ASSISTENTE),
        Exemplo("cai fora", ALVO_ASSISTENTE),
        Exemplo("fecha a janela", ALVO_ASSISTENTE),
        Exemplo("pode fechar esta janela", ALVO_ASSISTENTE),
        Exemplo("diga adeus para a maria", "maria", intencao="conversar"),
    ),
    regra=so_sobre_o_assistente,
    criar_acao=criar_acao,
)
