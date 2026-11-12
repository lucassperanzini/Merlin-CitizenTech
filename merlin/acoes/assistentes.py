"""Trocar de assistente (personalidade): por voz ("troca para a Ana") ou pela lista no nome da bolinha."""
import re

from merlin.nucleo.resposta import Resultado
from merlin.personalidades import PERSONALIDADES
from merlin.texto import normalizar

# Palavras que acompanham o nome no pedido e não fazem parte dele: "para a ana", "pro merlin", "com a ana"
LIGACOES = {"o", "a", "os", "as", "pro", "pra", "para", "com", "assistente", "de", "do", "da"}


def encontrar_assistente(texto: str):
    """O assistente citado no texto, pelo nome, identificador ou uma das palavras de chamada. None se nenhum."""
    palavras = [normalizar(p) for p in re.findall(r"\w+", texto.lower()) if p not in LIGACOES]
    candidatos = {normalizar(texto), "".join(palavras), *palavras} - {""}
    for personalidade in PERSONALIDADES.values():
        nomes = {normalizar(personalidade.nome), normalizar(personalidade.id),
                 *(normalizar(p) for p in personalidade.palavras_ativacao)}
        if candidatos & nomes:
            return personalidade
    return None


def trocar_personalidade(preferencias, memoria, canal, identificador: str) -> bool:
    """Passa a usar outra personalidade. Retorna False se ela não existe ou já é a atual."""
    if identificador not in PERSONALIDADES or identificador == preferencias.personalidade.id:
        return False
    preferencias.personalidade = identificador
    memoria.limpar()  # a conversa anterior era com a outra personalidade
    canal.personalidade()  # a janela troca o visual, a cor e o nome
    return True


def lista_falada() -> str:
    nomes = [p.nome for p in PERSONALIDADES.values()]
    return nomes[0] if len(nomes) == 1 else f"{', '.join(nomes[:-1])} e {nomes[-1]}"


class TrocarAssistente:
    def __init__(self, preferencias, memoria, canal):
        self._preferencias = preferencias
        self._memoria = memoria
        self._canal = canal

    def __call__(self, intencao) -> Resultado:
        alvo = (intencao.alvo or "").strip()
        escolhido = encontrar_assistente(alvo) if alvo else None
        if escolhido is None:
            inicio = f"não conheço nenhum assistente chamado {alvo}" if alvo else "para qual assistente você quer trocar"
            return Resultado(f"{inicio.capitalize()}. Tenho {lista_falada()}.", frase_completa=True,
                             registro=f"Assistente não encontrado: {alvo!r}")
        if escolhido.id == self._preferencias.personalidade.id:
            return Resultado(f"Você já está falando comigo, {escolhido.nome}.", frase_completa=True,
                             registro="Já era o assistente atual")
        # Troca antes de falar: a apresentação já sai com a voz e o jeito do novo assistente
        trocar_personalidade(self._preferencias, self._memoria, self._canal, escolhido.id)
        return Resultado(escolhido.apresentacao, frase_completa=True, finaliza=True,
                         registro=f"Assistente trocado para {escolhido.nome}")
