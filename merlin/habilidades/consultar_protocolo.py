"""Consultar protocolo: responde pelos documentos da Defesa Civil, com o modelo especialista (merlin/ia/especialista.py).

Quando a IA de conversa não reconhece a pergunta, a busca nos documentos ainda confere: se acha um trecho parecido
o bastante, a pergunta vem para cá (ProcessadorComandos._confirmar_protocolo).
"""
from merlin.habilidades import grupos
from merlin.habilidades.base import Exemplo, Habilidade


def criar_acao(recursos):
    from merlin.acoes.consultar_protocolo import ConsultarProtocolo
    return ConsultarProtocolo(recursos.especialista)


HABILIDADE = Habilidade(
    nome="consultar_protocolo",
    titulo="Consultar os protocolos",
    resumo="Responde pelos manuais e normas da Defesa Civil, citando a fonte.",
    icone="🚒",
    regras_resumo=(
        "Se a IA achar que é conversa, mas a busca encontrar um trecho dos protocolos parecido, a pergunta vem para cá.",
        "Se a resposta não estiver nos documentos, ele diz isso: nunca inventa um procedimento.",
    ),
    grupo=grupos.DEFESA_CIVIL,
    ordem=30,
    descricao="a pessoa pergunta sobre protocolos, procedimentos ou conceitos da Defesa Civil e do combate a "
              "incêndios: incêndio florestal ou em edificação, brigada e brigadista, equipamentos de proteção, aceiro, "
              "queima controlada, manejo do fogo, Sistema de Comando de Incidentes (SCI) ou plano de emergência. "
              "O alvo é o assunto da pergunta.",
    exemplos=(
        Exemplo("o que é o sistema de comando de incidentes", "sistema de comando de incidentes"),
        Exemplo("como se faz um aceiro", "aceiro"),
        Exemplo("o que o brigadista leva para o combate", "equipamentos do brigadista"),
        Exemplo("qual a função do comandante do incidente", "comandante do incidente"),
        Exemplo("me conta uma piada sobre bombeiros", "piada", intencao="conversar"),
        Exemplo("qual a previsão do tempo para amanhã", "previsão do tempo", intencao="conversar"),
    ),
    criar_acao=criar_acao,
)
