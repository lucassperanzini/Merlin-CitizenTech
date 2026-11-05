"""Fecha programas, sempre perguntando antes."""
import time

from merlin.acoes import janelas as sistema_janelas
from merlin.config import PRAZO_CONFIRMACAO
from merlin.nucleo.sessao import Pendencia

TEMPO_PARA_FECHAR = 2.5  # dá tempo de o programa fechar antes de anunciar o resultado
TAMANHO_TITULO = 60


def descrever_alvo(janelas, pelo_titulo: bool) -> str:
    if pelo_titulo and len(janelas) == 1:
        return f"a janela {janelas[0].titulo[:TAMANHO_TITULO]}"
    if len(janelas) > 1:
        return f"as {len(janelas)} janelas de {janelas[0].programa}"
    return janelas[0].programa


class FecharPrograma:
    def __init__(self, locutor, sessao):
        self._locutor = locutor
        self._sessao = sessao

    def __call__(self, intencao) -> str:
        """Não fecha nada: localiza as janelas e pergunta. O fechamento só acontece depois do sim."""
        nome = intencao.alvo
        janelas, pelo_titulo = sistema_janelas.escolher_janelas(nome, sistema_janelas.listar_janelas())
        if not janelas:
            self._locutor.falar(f"Não encontrei {nome} aberto.")
            return f"Nada encontrado para '{nome}'."

        programas = sorted({j.programa for j in janelas})
        if len(programas) > 1:
            self._locutor.falar(f"Encontrei mais de um: {', '.join(programas)}. Qual deles você quer fechar?")
            return f"Ambíguo: {programas}"

        descricao = descrever_alvo(janelas, pelo_titulo)
        pergunta = f"Posso fechar {descricao}?"
        self._sessao.aguardar_confirmacao(Pendencia(
            pergunta=pergunta,
            ao_confirmar=lambda: self._fechar(janelas, descricao),
            resposta_recusa="Tudo bem, não vou fechar.",
            expira_em=time.time() + PRAZO_CONFIRMACAO,
        ))
        self._locutor.falar(pergunta)
        return f"Aguardando confirmação: {descricao}"

    def _fechar(self, janelas, descricao):
        pedidos_ok = [sistema_janelas.pedir_fechamento(j) for j in janelas]
        time.sleep(TEMPO_PARA_FECHAR)
        if all(pedidos_ok) and not any(sistema_janelas.ainda_aberta(j) for j in janelas):
            self._locutor.falar(f"Pronto, fechei {descricao}.")
        else:
            self._locutor.falar(f"Pedi para fechar {descricao}, mas continua aberto. Talvez esteja perguntando se você quer salvar.")
