"""Monta o prompt e o esquema de resposta do classificador a partir das habilidades registradas.

Ninguém edita o prompt de intenções à mão: descrição e exemplos de cada pedido ficam no arquivo da habilidade.
"""
import json

from merlin.habilidades import NOME_CONVERSAR, grupos_em_uso

CABECALHO = """Analise a frase dita a um assistente de voz chamado Merlin. Preencha nesta ordem:

alvo: a coisa de que a frase fala ou que ela manda fechar, desligar, abrir ou deixar (um programa, site, aparelho, pessoa, música ou assunto), em uma ou duas palavras. Escreva "merlin" somente se a frase não citar nada disso, porque nesse caso ela é dirigida ao próprio assistente."""

CABECALHO_GRUPO = """Uma pessoa falou uma frase a um assistente de voz chamado Merlin. Diga de que tipo é o pedido:"""

EXEMPLOS_POR_HABILIDADE_NOS_GRUPOS = 6  # a etapa dos grupos só precisa de uma amostra de cada habilidade


def campos_de(habilidades) -> list:
    vistos, campos = set(), []
    for h in habilidades:
        for campo in h.campos:
            if campo.nome not in vistos:
                vistos.add(campo.nome)
                campos.append(campo)
    return campos


def montar_prompt(habilidades) -> str:
    """O prompt de uma etapa só (todas as habilidades) ou o da segunda etapa (as de um grupo, mais conversar)."""
    campos = campos_de(habilidades)
    partes = [CABECALHO, "intencao:\n" + "\n".join(f"- {h.nome}: {h.descricao}" for h in habilidades)]
    for campo in campos:
        donos = " e ".join(h.nome for h in habilidades if campo in h.campos)
        partes.append(f"{campo.nome}: somente em {donos}, {campo.descricao}. Nos outros casos, deixe vazio.")
    linhas = [_exemplo(e.frase, e.alvo, e.intencao or h.nome, e.campos, campos)
              for h in habilidades for e in h.exemplos]
    partes.append("Exemplos:\n" + "\n".join(linhas))
    return "\n\n".join(partes)


def montar_esquema(habilidades) -> dict:
    campos = [c.nome for c in campos_de(habilidades)]
    return {
        "type": "object",
        "properties": {
            "alvo": {"type": "string"},
            "intencao": {"type": "string", "enum": [h.nome for h in habilidades]},
            **{nome: {"type": "string"} for nome in campos},
        },
        "required": ["alvo", "intencao", *campos],
    }


def montar_prompt_grupos(habilidades) -> str:
    """Primeira etapa: só o tipo do pedido. Uma amostra dos exemplos de cada habilidade basta."""
    grupos = grupos_em_uso(habilidades)
    grupo_de = {h.nome: h.grupo.nome for h in habilidades}
    linhas = []
    for h in habilidades:
        positivos = [e for e in h.exemplos if e.intencao is None][:EXEMPLOS_POR_HABILIDADE_NOS_GRUPOS]
        contraexemplos = [e for e in h.exemplos if e.intencao is not None]
        for e in positivos + contraexemplos:
            linhas.append(f'"{e.frase}" -> ' + json.dumps({"grupo": grupo_de[e.intencao or h.nome]}, ensure_ascii=False))
    lista = "\n".join(f"- {g.nome}: {g.descricao}" for g in grupos)
    return f"{CABECALHO_GRUPO}\n{lista}\n\nExemplos:\n" + "\n".join(linhas)


def montar_esquema_grupos(habilidades) -> dict:
    return {
        "type": "object",
        "properties": {"grupo": {"type": "string", "enum": [g.nome for g in grupos_em_uso(habilidades)]}},
        "required": ["grupo"],
    }


def habilidades_do_grupo(habilidades, grupo: str) -> list:
    """As do grupo, sempre com conversar no fim: a segunda etapa ainda pode concluir que não é uma ação."""
    escolhidas = [h for h in habilidades if h.grupo.nome == grupo and h.nome != NOME_CONVERSAR]
    return escolhidas + [h for h in habilidades if h.nome == NOME_CONVERSAR]


def _exemplo(frase, alvo, intencao, valores, campos) -> str:
    resposta = {"alvo": alvo, "intencao": intencao, **{c.nome: valores.get(c.nome, "") for c in campos}}
    return f'"{frase}" -> ' + json.dumps(resposta, ensure_ascii=False)
