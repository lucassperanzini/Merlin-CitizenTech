"""As habilidades do assistente, uma por arquivo nesta pasta.

Para ensinar algo novo, crie um arquivo aqui com uma HABILIDADE (veja base.py e qualquer arquivo vizinho como
modelo) e a ação em merlin/acoes/. Ela é encontrada sozinha: entra no prompt da IA, no esquema de resposta,
nas ações executadas e na avaliação. Nenhum outro arquivo precisa mudar.
"""
import importlib
import pkgutil

from merlin.habilidades.base import Habilidade

__all__ = ["HABILIDADES", "por_nome", "grupos_em_uso", "NOME_CONVERSAR"]

NAO_SAO_HABILIDADES = {"base", "grupos", "frases"}
NOME_CONVERSAR = "conversar"  # o caso geral: precisa existir, é para onde vai tudo o que não é ação


def _descobrir() -> tuple[Habilidade, ...]:
    encontradas = []
    for info in pkgutil.iter_modules(__path__):
        if info.name in NAO_SAO_HABILIDADES:
            continue
        modulo = importlib.import_module(f"{__name__}.{info.name}")
        if isinstance(getattr(modulo, "HABILIDADE", None), Habilidade):
            encontradas.append(modulo.HABILIDADE)
    encontradas.sort(key=lambda h: (h.ordem, h.nome))
    validar(encontradas)
    return tuple(encontradas)


def validar(habilidades) -> None:
    """Erros de montagem aparecem ao abrir o programa, com uma mensagem clara, e não no meio de um pedido."""
    nomes = [h.nome for h in habilidades]
    repetidos = {n for n in nomes if nomes.count(n) > 1}
    if repetidos:
        raise ValueError(f"Habilidades com o mesmo nome: {sorted(repetidos)}")
    if NOME_CONVERSAR not in nomes:
        raise ValueError(f"A habilidade '{NOME_CONVERSAR}' é obrigatória: é o caso geral")
    for h in habilidades:
        if not h.nome.isidentifier() or h.nome != h.nome.lower():
            raise ValueError(f"Nome inválido de habilidade: '{h.nome}' (use minúsculas e _, como abrir_programa)")
        for exemplo in h.exemplos:
            if exemplo.intencao is not None and exemplo.intencao not in nomes:
                raise ValueError(f"Exemplo de '{h.nome}' aponta para a habilidade inexistente '{exemplo.intencao}'")
            desconhecidos = set(exemplo.campos) - {c.nome for c in h.campos}
            if exemplo.intencao is None and desconhecidos:
                raise ValueError(f"Exemplo de '{h.nome}' usa campos que ela não declara: {sorted(desconhecidos)}")


HABILIDADES = _descobrir()
_POR_NOME = {h.nome: h for h in HABILIDADES}


def por_nome(nome: str) -> Habilidade:
    return _POR_NOME[nome]


def grupos_em_uso(habilidades=HABILIDADES):
    """Os grupos que têm ao menos uma habilidade, na ordem definida."""
    return sorted({h.grupo for h in habilidades}, key=lambda g: (g.ordem, g.nome))
