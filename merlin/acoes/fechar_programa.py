"""Fecha programas abertos, da mesma forma que o botão X."""
import time

from merlin.acoes import janelas as sistema_janelas
from merlin.nucleo.resposta import Resultado
from merlin.texto import com_artigo

TEMPO_MAXIMO_PARA_FECHAR = 2.5  # depois disso, considera que o programa não fechou
INTERVALO_VERIFICACAO = 0.1
TAMANHO_TITULO = 60


def descrever_alvo(janelas, pelo_titulo: bool) -> str:
    if pelo_titulo and len(janelas) == 1:
        return f"a janela {janelas[0].titulo[:TAMANHO_TITULO]}"
    if len(janelas) > 1:
        return f"as {len(janelas)} janelas de {janelas[0].programa}"
    return com_artigo(janelas[0].programa)


class FecharPrograma:
    def __call__(self, intencao) -> Resultado:
        nome = intencao.alvo
        janelas, pelo_titulo = sistema_janelas.escolher_janelas(nome, sistema_janelas.listar_janelas())
        if not janelas:
            return Resultado(f"não encontrei {nome} aberto", registro=f"Nada encontrado para '{nome}'.")

        programas = sorted({j.programa for j in janelas})
        if len(programas) > 1:
            return Resultado(f"Encontrei mais de um: {', '.join(programas)}. Qual deles você quer fechar?",
                             registro=f"Ambíguo: {programas}", frase_completa=True)

        descricao = descrever_alvo(janelas, pelo_titulo)
        if self._fechar(janelas):
            return Resultado(f"fechei {descricao}", registro=f"Fechado: {descricao}")
        return Resultado(f"pedi para fechar {descricao}, mas continua aberto, talvez esteja perguntando se você quer salvar",
                         registro=f"Continua aberto: {descricao}")

    @staticmethod
    def _fechar(janelas) -> bool:
        pedidos_ok = all([sistema_janelas.pedir_fechamento(j) for j in janelas])
        limite = time.time() + TEMPO_MAXIMO_PARA_FECHAR
        while any(sistema_janelas.ainda_aberta(j) for j in janelas):
            if time.time() > limite:
                return False
            time.sleep(INTERVALO_VERIFICACAO)
        return pedidos_ok
