"""Rodar script: executa, depois da confirmação, um script aprovado na aba Automações, chamado pelo nome."""
import re

from merlin.habilidades import grupos
from merlin.habilidades.base import Correcao, Exemplo, Habilidade

PEDE_PARA_RODAR = re.compile(r"\b(?:rod[aeo]\w*|execut\w*)\b", re.IGNORECASE)


def regra(leitura):
    if not PEDE_PARA_RODAR.search(leitura.comando):
        return Correcao("conversar", "a frase não pede para rodar nada")
    return None


def criar_acao(recursos):
    from merlin.acoes.rodar_script import criar
    return criar(recursos)


HABILIDADE = Habilidade(
    nome="rodar_script",
    titulo="Rodar script aprovado",
    resumo="Roda pelo nome um script que você testou e aprovou, sempre com o mesmo código.",
    icone="▶️",
    regras_resumo=(
        'Só roda scripts aprovados na aba Automações.',
        'Sempre mostra o nome e a pasta e espera você confirmar.',
        'Se o código mudar, a aprovação cai.',
    ),
    grupo=grupos.SCRIPTS,
    ordem=28,
    descricao="a pessoa manda rodar ou executar um script já existente, chamando-o pelo nome. O alvo é o nome do script, "
              "sem a palavra script. Pedir para criar ou escrever um script não é este pedido.",
    exemplos=(
        Exemplo("roda o maior arquivo", "maior arquivo"),
        Exemplo("executa o script limpar lista", "limpar lista"),
        Exemplo("roda o script de converter imagens", "converter imagens"),
        Exemplo("cria um script que roda um relatório", "relatório", intencao="gerar_script"),
        Exemplo("como rodar um script em python", "script", intencao="conversar"),
    ),
    regra=regra,
    mexe_no_computador=True,
    frase_inteira=True,
    criar_acao=criar_acao,
)
