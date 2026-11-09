"""Conversar: o caso geral. Responde perguntas e conversa, sem mexer no computador.

Os exemplos daqui são contraexemplos gerais: pedidos que parecem ações, mas que o assistente não faz.
"""
from merlin.habilidades import grupos
from merlin.habilidades.base import Correcao, Exemplo, Habilidade
from merlin.habilidades.texto_selecionado import e_pedido_claro

NOME = "conversar"  # a intenção usada quando nenhuma outra serve


def regra(leitura):
    if e_pedido_claro(leitura.comando):
        return Correcao("texto_selecionado", "a frase manda editar um texto que está na tela", alvo="texto")
    return None


def criar_acao(recursos):
    from merlin.acoes.conversar import Conversar
    from merlin.ia.conversa import Conversa
    return Conversar(Conversa(recursos.cliente_ia, recursos.memoria, recursos.preferencias))


HABILIDADE = Habilidade(
    nome=NOME,
    titulo='Conversar',
    resumo="Responde perguntas e conversa com você.",
    icone="💬",
    regras_resumo=(
        'É o caso geral: tudo o que não é outra habilidade. Nunca executa ações.',
        '“Responde essa mensagem…” ou “corrige o texto selecionado” vão para o texto selecionado.',
    ),
    grupo=grupos.CONVERSA,
    ordem=99,
    descricao="qualquer outra coisa, inclusive perguntas de conhecimento geral, perguntas sobre como fazer algo, "
              "aparelhos fora do computador, pedidos sobre despedidas e pedidos para escrever um texto sem citar "
              "um arquivo.",
    exemplos=(
        Exemplo("apaga a pasta fotos", "fotos"),
        Exemplo("exclui o arquivo tarefas", "tarefas"),
        Exemplo("escreve um poema sobre o mar", "poema"),
        Exemplo("como criar uma pasta no windows", "pasta"),
        Exemplo("apaga a luz", "luz"),
        Exemplo("qual o sentido de acordar cedo", "acordar cedo"),
        Exemplo("qual a capital do chile", "capital do chile"),
        Exemplo("que horas fecha o mercado", "mercado"),
    ),
    regra=regra,
    criar_acao=criar_acao,
)
