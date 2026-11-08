"""Abrir programa: abre um programa instalado (o navegador padrão quando a pessoa diz só "navegador")."""
import re

from merlin.habilidades import grupos
from merlin.habilidades.base import Correcao, Exemplo, Habilidade
from merlin.personalidades import NOMES_DO_ASSISTENTE


def regra(leitura):
    if re.search(r"\bpastas?\b", leitura.comando, re.IGNORECASE):
        alvo = re.sub(r"\bpastas?\b", "", leitura.alvo, flags=re.IGNORECASE).strip() or leitura.alvo
        return Correcao("abrir_pasta", "a frase pede uma pasta, não um programa", alvo=alvo)
    from merlin.acoes.pastas import atalho
    if leitura.alvo and atalho(leitura.alvo, so_fixadas=True):
        return Correcao("abrir_pasta", f"“{leitura.alvo}” é um atalho de pasta, não um programa")
    if not leitura.alvo or leitura.alvo.lower() in NOMES_DO_ASSISTENTE:
        return Correcao("conversar", "abrir programa precisa de um programa, e não o próprio assistente")
    return None


def criar_acao(recursos):
    from merlin.acoes.abrir_programa import AbrirPrograma
    from merlin.acoes.web import PesquisarWeb
    return AbrirPrograma(recursos.compartilhado("pesquisa_web", PesquisarWeb))


HABILIDADE = Habilidade(
    nome="abrir_programa",
    titulo='Abrir programa',
    regras_resumo=(
        'Sem programa citado, ou citando o próprio assistente, vira conversa.',
        'Se a frase fala em “pasta”, ou o nome é um atalho de pasta (aba Pastas ou Acesso Rápido), vira abrir pasta.',
    ),
    grupo=grupos.PROGRAMAS,
    ordem=21,
    descricao="a pessoa manda abrir ou iniciar um programa instalado no computador. O alvo é o nome do programa.",
    exemplos=(
        Exemplo("abre o paint", "paint"),
        Exemplo("inicia o photoshop", "photoshop"),
        Exemplo("abre as configurações do windows", "configurações"),
        Exemplo("abre a pasta documentos", "documentos", intencao="abrir_pasta"),
    ),
    regra=regra,
    mexe_no_computador=True,
    criar_acao=criar_acao,
)
