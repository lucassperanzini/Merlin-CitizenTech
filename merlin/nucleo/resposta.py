"""O resultado de cada ação e a montagem de uma única resposta falada para todas as tarefas da frase."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Resultado:
    fala: str  # trecho da resposta, como "abri o chrome"
    registro: str = ""  # detalhe técnico para o terminal
    frase_completa: bool = False  # respostas da IA e perguntas não se juntam com "e" às demais
    depois: Callable[[], None] | None = None  # roda depois de falar, como esconder a janela
    finaliza: bool = False  # as tarefas seguintes da frase não devem ser executadas


def montar_resposta(resultados: list[Resultado]) -> str:
    """Junta ações seguidas: "Abri o chrome e fechei o telegram." Frases completas ficam como estão."""
    partes, trechos = [], []
    for resultado in resultados:
        if resultado.frase_completa:
            if trechos:
                partes.append(_juntar_trechos(trechos))
                trechos = []
            partes.append(resultado.fala)
        else:
            trechos.append(resultado.fala)
    if trechos:
        partes.append(_juntar_trechos(trechos))
    return " ".join(partes)


def _juntar_trechos(trechos: list[str]) -> str:
    primeiro, *resto = [t.strip().rstrip(".") for t in trechos]
    resto = [t[0].lower() + t[1:] for t in resto]
    texto = primeiro[0].upper() + primeiro[1:]
    if len(resto) > 1:
        texto += ", " + ", ".join(resto[:-1])
    if resto:
        texto += " e " + resto[-1]
    return texto + "."
