"""Ajustes das skills feitos na Central: título, descrição e exemplos, um arquivo .json por skill em skills/.

O que está em cada arquivo vale no lugar do texto do código; apagar o arquivo restaura o original.
As regras e a ação continuam no código: um texto não consegue mudar como a skill age.
Um arquivo com problema é ignorado (com aviso no log), para nunca impedir o assistente de abrir.
"""
import json
import logging
from dataclasses import replace
from pathlib import Path

from merlin.habilidades.base import Exemplo, Habilidade

logger = logging.getLogger(__name__)

ARQUIVO_DESLIGADAS = "_desligadas.json"  # o "_" evita confundir com o arquivo de uma skill
MAXIMO_EXEMPLOS = 30  # cada exemplo vai em toda pergunta à IA: exemplos demais deixam tudo mais lento


class AjusteInvalido(ValueError):
    """A mensagem é mostrada à pessoa na aba Skills."""


def conferir(habilidade: Habilidade, dados: dict, nomes: set[str]) -> dict:
    """Devolve os dados limpos, ou recusa com o motivo."""
    titulo, descricao = str(dados.get("titulo", "")).strip(), " ".join(str(dados.get("descricao", "")).split())
    if not titulo:
        raise AjusteInvalido("Dê um título à skill.")
    if not descricao:
        raise AjusteInvalido("Escreva quando a skill deve ser usada: é o que a IA lê para reconhecer o pedido.")
    declarados = {c.nome for c in habilidade.campos}
    exemplos, vistas = [], set()
    for item in dados.get("exemplos") or []:
        frase, alvo = str(item.get("frase", "")).strip(), str(item.get("alvo", "")).strip()
        if not frase and not alvo:
            continue  # linha deixada em branco
        if not frase or not alvo:
            raise AjusteInvalido(f"Preencha a frase e o alvo do exemplo “{frase or alvo}”.")
        if frase.lower() in vistas:
            raise AjusteInvalido(f"O exemplo “{frase}” aparece duas vezes.")
        vistas.add(frase.lower())
        intencao = str(item.get("intencao") or "").strip() or None
        if intencao == habilidade.nome:
            intencao = None
        if intencao is not None and intencao not in nomes:
            raise AjusteInvalido(f"O exemplo “{frase}” aponta para uma skill que não existe.")
        campos = {k: str(v).strip() for k, v in (item.get("campos") or {}).items() if k in declarados and str(v).strip()}
        exemplos.append({"frase": frase, "alvo": alvo, "intencao": intencao, "campos": campos if not intencao else {}})
    if not any(e["intencao"] is None for e in exemplos):
        raise AjusteInvalido("Deixe ao menos um exemplo que ativa esta skill.")
    if len(exemplos) > MAXIMO_EXEMPLOS:
        raise AjusteInvalido(f"Use no máximo {MAXIMO_EXEMPLOS} exemplos: cada um deixa as respostas mais lentas.")
    return {"titulo": titulo, "descricao": descricao, "exemplos": exemplos}


def aplicar(habilidade: Habilidade, dados: dict) -> Habilidade:
    return replace(habilidade, titulo=dados["titulo"], descricao=dados["descricao"], exemplos=tuple(
        Exemplo(e["frase"], e["alvo"], e.get("intencao"), dict(e.get("campos") or {})) for e in dados["exemplos"]))


def aplicar_da_pasta(habilidades, pasta: Path) -> tuple[Habilidade, ...]:
    nomes = {h.nome for h in habilidades}
    resultado = []
    for habilidade in habilidades:
        arquivo = pasta / f"{habilidade.nome}.json"
        if arquivo.is_file():
            try:
                dados = conferir(habilidade, json.loads(arquivo.read_text(encoding="utf-8")), nomes)
                habilidade = aplicar(habilidade, dados)
            except (OSError, ValueError, TypeError, AttributeError) as erro:
                logger.warning("[SKILLS] Ignorei %s: %s", arquivo.name, erro)
        resultado.append(habilidade)
    return tuple(resultado)


def desligadas(pasta: Path) -> set[str]:
    """As skills desligadas na aba Skills. Arquivo com problema: todas ficam ligadas."""
    try:
        return {str(n) for n in json.loads((pasta / ARQUIVO_DESLIGADAS).read_text(encoding="utf-8"))}
    except (OSError, ValueError, TypeError):
        return set()


def salvar_desligadas(nomes: set[str], pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / ARQUIVO_DESLIGADAS).write_text(json.dumps(sorted(nomes), ensure_ascii=False, indent=2), encoding="utf-8")


def salvar(nome: str, dados: dict, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{nome}.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def apagar(nome: str, pasta: Path) -> None:
    (pasta / f"{nome}.json").unlink(missing_ok=True)
