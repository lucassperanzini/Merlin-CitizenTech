"""Clica em botões de um programa aberto.

O código procura o nome dito entre os botões reais. Se não achar ou empatar, a IA escolhe o mais provável.
Pede confirmação antes de clicar quando o botão é perigoso ou quando foi a IA que escolheu.
"""
import logging
import re
import time

from merlin.acoes import controles, janelas as sistema_janelas
from merlin.acoes.ver_botoes import citou_programa
from merlin.config import PRAZO_CONFIRMACAO
from merlin.nucleo.resposta import Resultado
from merlin.nucleo.sessao import Pendencia
from merlin.texto import normalizar

logger = logging.getLogger(__name__)

# Ações difíceis de desfazer. A comparação é feita sem acentos e em minúsculas.
PALAVRAS_PERIGOSAS = re.compile(
    r"\b(?:exclu\w*|apag\w*|delet\w*|remov\w*|desinstal\w*|format\w*|esvazi\w*|descart\w*|"
    r"nao salvar|sem salvar|envi\w*|send|delete|remove|uninstall|discard|"
    r"compra\w*|compre\w*|comprar|paga|pagar|pague\w*|pagamento\w*|finaliz\w*|"
    r"confirm\w*|public\w*|post\w*|transfer\w*|assin\w*|buy|pay|purchase|"
    r"deslig\w*|reinici\w*|shutdown|restart|sair|logout)\b"
)


def e_perigoso(nome: str) -> bool:
    sem_acento = " ".join(normalizar(p) for p in nome.split())
    return bool(PALAVRAS_PERIGOSAS.search(sem_acento))


class ClicarBotao:
    def __init__(self, sessao, escolhedor):
        self._sessao = sessao
        self._escolhedor = escolhedor

    def __call__(self, intencao) -> Resultado:
        pedido = intencao.alvo
        janela = self._escolher_janela(intencao.local)
        if not janela:
            return Resultado("não encontrei a janela onde clicar", registro=f"Sem janela para '{pedido}'")

        nomes = controles.nomes_clicaveis(janela.hwnd, janela.titulo)
        escolha = controles.escolher_controle(pedido, nomes)
        # Vários botões com o mesmo nome (como os Play do Spotify): o clique decide qual, pela posição na janela
        repetido = escolha.opcoes[0] if escolha.opcoes and len(set(escolha.opcoes)) == 1 else None
        nome = escolha.nome or repetido
        if nome:
            if e_perigoso(nome):
                return self._pedir_confirmacao(janela, nome, f"Tem certeza de que quer que eu clique em {nome}?")
            return self._clicar(janela, nome)

        # Empate entre nomes diferentes: a IA decide só entre eles. Nada parecido: entre todos os botões.
        sugerido = self._escolhedor.escolher(pedido, escolha.opcoes or nomes)
        logger.info("[CLIQUE] IA sugeriu %r para %r", sugerido, pedido)
        if not sugerido:
            return Resultado(f"não encontrei o botão {pedido}", registro=f"Botão não encontrado: {pedido}")
        return self._pedir_confirmacao(janela, sugerido, f"Não achei {pedido}. Você quer que eu clique em {sugerido}?")

    @staticmethod
    def _escolher_janela(programa):
        if not citou_programa(programa):
            return sistema_janelas.janela_em_uso()
        achadas, _ = sistema_janelas.escolher_janelas(programa, sistema_janelas.listar_janelas())
        return achadas[0] if achadas else None

    def _pedir_confirmacao(self, janela, nome, pergunta) -> Resultado:
        self._sessao.aguardar_confirmacao(Pendencia(
            pergunta=pergunta,
            ao_confirmar=lambda: self._clicar(janela, nome),
            resposta_recusa="Tudo bem, não cliquei.",
            expira_em=time.time() + PRAZO_CONFIRMACAO,
        ))
        # finaliza: as tarefas seguintes não podem acontecer antes da resposta
        return Resultado(pergunta, registro=f"Aguardando confirmação: {nome}", frase_completa=True, finaliza=True)

    @staticmethod
    def _clicar(janela, nome) -> Resultado:
        resultado = controles.clicar(janela.hwnd, janela.titulo, nome)
        if resultado is controles.ResultadoClique.CLICOU:
            return Resultado(f"cliquei em {nome}", registro=f"Clique: {nome} ({janela.programa})")
        if resultado is controles.ResultadoClique.AMBIGUO:
            return Resultado(f"Há vários botões chamados {nome} nesta janela e não consegui saber qual deles você quer, "
                             "então não cliquei.", registro=f"Repetidos sem desempate: {nome}", frase_completa=True)
        if resultado is controles.ResultadoClique.SUMIU:
            return Resultado(f"o botão {nome} não está mais na tela", registro=f"Sumiu: {nome}")
        return Resultado(f"não consegui clicar em {nome}", registro=f"Clique falhou: {nome}")
