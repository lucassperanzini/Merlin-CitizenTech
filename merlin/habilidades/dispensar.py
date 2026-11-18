"""Dispensar: o assistente se despede e volta a esperar ser chamado."""
import re

from merlin.habilidades import grupos
from merlin.habilidades.base import ALVO_ASSISTENTE, Correcao, Exemplo, Habilidade
from merlin.personalidades import NOMES_DO_ASSISTENTE

# "Tudo bem com você?" puxa conversa: modelos pequenos confundem com despedida ("tudo bem, pode ir")
PUXA_CONVERSA = re.compile(r"^(?:e\s+)?(?:tudo\s+(?:bem|bom|certo|tranquilo|em\s+paz)|como\s+(?:vai|voc[eê]\s+est[aá]|est[aá])|"
                           r"beleza|suave|fala\s+a[ií])\b", re.IGNORECASE)
DESPEDIDA = re.compile(r"\b(?:tchau|valeu|obrigad[oa]|brigad[oa]|at[eé]\s+(?:mais|logo|depois)|adeus|pode\s+(?:ir|sair|"
                       r"descansar|desligar)|boa\s+noite|terminamos|terminei|j[aá]\s+(?:resolvi|deu)|desliga|some|cai\s+fora)\b",
                       re.IGNORECASE)


def so_sobre_o_assistente(leitura):
    """Sair só vale quando o alvo é o próprio assistente: "encerra o discord" não é desligar o assistente."""
    if PUXA_CONVERSA.match(leitura.comando) and not DESPEDIDA.search(leitura.comando):
        return Correcao("conversar", "a frase puxa conversa (“tudo bem?”), sem nenhuma despedida")
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
        '“Tudo bem com você?” sem nenhuma despedida vira conversa.',
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
