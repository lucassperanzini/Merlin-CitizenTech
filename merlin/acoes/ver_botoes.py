"""Responde quais botões existem em um programa aberto. Só informa: não clica em nada."""
import logging

from merlin.acoes import controles, janelas as sistema_janelas
from merlin.nucleo.raciocinio import Raciocinio, TipoPasso
from merlin.nucleo.resposta import Resultado
from merlin.texto import com_artigo, normalizar

logger = logging.getLogger(__name__)

MAX_NOMES_FALADOS = 8  # mais que isso fica cansativo de ouvir; o terminal mostra a lista inteira
ALVOS_GENERICOS = {"", "merlin", "aqui", "botoes", "botao", "tela", "janela", "essajanela", "estatela", "programa", "app", "aplicativo"}
PROGRAMAS_SEM_NOME_UTIL = {"ApplicationFrameHost"}  # apps da Microsoft Store: o nome está no título


def citou_programa(alvo: str) -> bool:
    return normalizar(alvo) not in ALVOS_GENERICOS


def nome_para_falar(janela) -> str:
    if janela.programa in PROGRAMAS_SEM_NOME_UTIL:
        return com_artigo(janela.titulo)
    return com_artigo(janela.programa)


def contrair_em(com_artigo_: str) -> str:
    """"o chrome" vira "no chrome", "a Calculadora" vira "na Calculadora"."""
    artigo, _, nome = com_artigo_.partition(" ")
    return f"n{artigo} {nome}"


def descrever_leitura(onde: str, leitura) -> str:
    em_onde = contrair_em(onde)
    total = len(leitura.nomes)
    if not total:
        if leitura.sem_nome:
            return f"Encontrei {leitura.sem_nome} botões {em_onde}, mas eles não têm nome. Podem ser só ícones."
        return f"Não consegui ver botões {em_onde}. Esse programa pode não informar seus botões ao Windows."
    citados = ", ".join(leitura.nomes[:MAX_NOMES_FALADOS])
    inicio = em_onde[0].upper() + em_onde[1:]
    if total == 1:
        return f"{inicio}, vejo um botão: {citados}."
    fim = f", e mais {total - MAX_NOMES_FALADOS}" if total > MAX_NOMES_FALADOS else ""
    aviso = " Pode haver outros, pois não consegui ler a janela inteira." if leitura.incompleta else ""
    return f"{inicio}, vejo {total} botões: {citados}{fim}.{aviso}"


class VerBotoes:
    def __init__(self, raciocinio=None):
        self._raciocinio = raciocinio or Raciocinio()

    def __call__(self, intencao) -> Resultado:
        janela = self._escolher(intencao.alvo)
        if not janela:
            return Resultado(f"Não encontrei {intencao.alvo} aberto." if citou_programa(intencao.alvo)
                             else "Não encontrei nenhuma janela aberta.", frase_completa=True)
        self._raciocinio.registrar(
            TipoPasso.JANELA, f"Janela: {janela.programa}", titulo=janela.titulo,
            como_escolhi="o programa citado" if citou_programa(intencao.alvo) else "a janela em uso, atrás do assistente")
        leitura = controles.ler_botoes(janela.hwnd, janela.titulo)
        logger.info("[BOTÕES] %s: %s (sem nome: %d, incompleta: %s)",
                    janela.programa, leitura.nomes, leitura.sem_nome, leitura.incompleta)
        self._raciocinio.registrar(TipoPasso.BOTOES, f"{len(leitura.nomes)} botões com nome", nomes=leitura.nomes,
                                   sem_nome=leitura.sem_nome or "",
                                   leitura_incompleta="sim, o tempo acabou" if leitura.incompleta else "")
        return Resultado(descrever_leitura(nome_para_falar(janela), leitura), frase_completa=True)

    def _escolher(self, alvo):
        if not citou_programa(alvo):
            return sistema_janelas.janela_em_uso()
        achadas, _ = sistema_janelas.escolher_janelas(alvo, sistema_janelas.listar_janelas())
        return achadas[0] if achadas else None

