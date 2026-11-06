"""Lê e aciona os controles de uma janela pelo UI Automation do Windows."""
import difflib
import logging
import time
from dataclasses import dataclass
from enum import Enum

import uiautomation as uia

from merlin.texto import normalizar

logger = logging.getLogger(__name__)

TIPOS_BOTAO = {uia.ControlType.ButtonControl, uia.ControlType.SplitButtonControl}
TIPOS_CLICAVEIS = TIPOS_BOTAO | {
    uia.ControlType.HyperlinkControl, uia.ControlType.MenuItemControl, uia.ControlType.TabItemControl,
    uia.ControlType.CheckBoxControl, uia.ControlType.RadioButtonControl, uia.ControlType.ListItemControl,
}
TEMPO_MAXIMO_LEITURA = 3.0  # segundos; janelas de navegador podem ter milhares de elementos
PROFUNDIDADE_MAXIMA = 40
SEMELHANCA_MINIMA = 0.75
COMANDOS_DE_JANELA = ("minimizar", "maximizar", "restaurar", "fechar", "minimize", "maximize", "restore", "close")
# Na ordem de preferência: todos acionam o controle sem mexer no mouse da pessoa
PADROES_DE_ACAO = (
    (uia.PatternId.InvokePattern, "Invoke"),
    (uia.PatternId.TogglePattern, "Toggle"),
    (uia.PatternId.SelectionItemPattern, "Select"),
    (uia.PatternId.ExpandCollapsePattern, "Expand"),
)


class ResultadoClique(Enum):
    CLICOU = "clicou"
    AMBIGUO = "ambiguo"  # vários botões com o mesmo nome e nenhum se destaca
    SUMIU = "sumiu"  # o botão não existe mais na janela
    FALHOU = "falhou"


@dataclass(frozen=True)
class Escolha:
    nome: str | None  # o controle escolhido, ou None
    opcoes: list[str]  # quando há empate: os nomes empatados


def e_botao_da_barra_de_titulo(nome: str, titulo: str) -> bool:
    """Apps da Microsoft Store desenham a própria barra: "Fechar Calculadora". Um "Fechar" sozinho é mantido,
    porque pode ser o botão de uma caixa de diálogo."""
    partes = nome.split(maxsplit=1)
    return len(partes) == 2 and partes[0].lower() in COMANDOS_DE_JANELA and partes[1].lower() == titulo.strip().lower()


def escolher_controle(pedido: str, nomes: list[str]) -> Escolha:
    """Do mais exato para o mais solto. Empate nunca é decidido no chute: volta como opções."""
    alvo = normalizar(pedido)
    if not alvo:
        return Escolha(None, [])
    normalizados = [(nome, normalizar(nome)) for nome in nomes]
    criterios = (lambda n: n == alvo, lambda n: n.startswith(alvo), lambda n: alvo in n)
    for criterio in criterios:
        achados = [nome for nome, n in normalizados if criterio(n)]
        if achados:
            return Escolha(achados[0], []) if len(achados) == 1 else Escolha(None, achados)
    parecidos = difflib.get_close_matches(alvo, [n for _, n in normalizados], n=3, cutoff=SEMELHANCA_MINIMA)
    achados = [nome for nome, n in normalizados if n in parecidos]
    return Escolha(achados[0], []) if len(achados) == 1 else Escolha(None, achados)


def nomes_clicaveis(hwnd: int, titulo: str = "") -> list[str]:
    """Todos os nomes, com repetições: dois "Salvar" na mesma janela precisam ser percebidos."""
    with uia.UIAutomationInitializerInThread():
        controles, _ = _coletar(hwnd, titulo, TIPOS_CLICAVEIS)
    return [nome for nome, _ in controles if nome]


def desempatar(vizinhos: list[int]) -> int | None:
    """Recebe, para cada botão de mesmo nome, quantos controles clicáveis estão ao lado dele.
    Vence o que faz parte de uma barra de controles: no Spotify, o Play do player fica entre Voltar e Avançar,
    enquanto o Play de cada playlist fica sozinho no cartão. Sem um vencedor claro, devolve None."""
    if not vizinhos:
        return None
    maior = max(vizinhos)
    if maior < 2 or vizinhos.count(maior) > 1:
        return None
    return vizinhos.index(maior)


def clicar(hwnd: int, titulo: str, nome: str) -> ResultadoClique:
    """Procura de novo pelo nome exato (a janela pode ter mudado) e aciona o controle."""
    with uia.UIAutomationInitializerInThread():
        alvo, motivo = _localizar(hwnd, titulo, nome)
        if alvo is None:
            return motivo
        return ResultadoClique.CLICOU if _acionar(alvo) else ResultadoClique.FALHOU


def _localizar(hwnd, titulo, nome):
    """Devolve (controle, None) ou (None, motivo). Precisa rodar dentro do preparo de UI Automation da thread."""
    controles, _ = _coletar(hwnd, titulo, TIPOS_CLICAVEIS)
    alvos = [controle for n, controle in controles if n == nome]
    if not alvos:
        return None, ResultadoClique.SUMIU
    if len(alvos) == 1:
        return alvos[0], None
    indice = desempatar([_clicaveis_ao_lado(alvo) for alvo in alvos])
    return (alvos[indice], None) if indice is not None else (None, ResultadoClique.AMBIGUO)


def _clicaveis_ao_lado(controle) -> int:
    try:
        return sum(1 for irmao in controle.GetParentControl().GetChildren() if irmao.ControlType in TIPOS_CLICAVEIS)
    except Exception:
        return 0


def _acionar(controle) -> bool:
    for padrao, metodo in PADROES_DE_ACAO:
        try:
            acao = controle.GetPattern(padrao)
            if acao:
                getattr(acao, metodo)()
                return True
        except Exception as erro:
            logger.debug("[CLIQUE] %s falhou: %s", metodo, erro)
    try:
        controle.Click(simulateMove=False)  # último recurso: clique de verdade, que move o mouse
        return True
    except Exception as erro:
        logger.error("[CLIQUE] %s", erro)
        return False


def _coletar(hwnd, titulo, tipos):
    """Retorna ([(nome, controle)], incompleta), só com controles visíveis e habilitados."""
    limite = time.time() + TEMPO_MAXIMO_LEITURA
    encontrados, incompleta = [], False
    for controle in _percorrer(uia.ControlFromHandle(hwnd), limite):
        if controle is None:
            incompleta = True
            break
        try:
            if controle.ControlType not in tipos or controle.IsOffscreen or not controle.IsEnabled:
                continue
            nome = " ".join(controle.Name.split())
        except Exception:
            continue
        if not e_botao_da_barra_de_titulo(nome, titulo):
            encontrados.append((nome, controle))
    return encontrados, incompleta


def _percorrer(controle, limite):
    """Percorre a árvore de controles, parando quando o tempo acaba. Controles somem e dão erro: isso é normal."""
    pilha = [(controle, 0)]
    while pilha:
        if time.time() > limite:
            yield None
            return
        atual, profundidade = pilha.pop()
        try:
            if atual.ControlType == uia.ControlType.TitleBarControl:
                continue  # Minimizar, Maximizar e Fechar existem em toda janela e só poluiriam a resposta
            filhos = atual.GetChildren() if profundidade < PROFUNDIDADE_MAXIMA else []
        except Exception:
            continue
        for filho in reversed(filhos):
            pilha.append((filho, profundidade + 1))
        yield atual
