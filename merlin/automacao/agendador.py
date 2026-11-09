"""Roda os scripts agendados no horário, enquanto o Merlin estiver aberto. Horário perdido não é compensado depois."""
import logging
import threading
from datetime import datetime, timedelta

from merlin.automacao.scripts import ScriptInvalido

logger = logging.getLogger(__name__)

PASSOS_ENTRE_DIARIOS = 20  # o agendador acorda a cada segundo; os horários diários só precisam de uma olhada a cada 20
ATRASO_MAXIMO_UMA_VEZ = 60  # segundos: ao reabrir o Merlin bem depois da hora, o script não roda de surpresa
JANELA = timedelta(minutes=5)  # passou disso (computador dormindo, Merlin fechado), espera o dia seguinte
MAX_NOME_NO_AVISO = 40
MAX_RESUMO_NO_CARTAO = 3000


def _resumo(resultado: dict) -> str:
    if resultado["tempo_esgotado"]:
        return "Parou: passou do tempo limite."
    return "\n".join(t for t in (resultado["saida"], resultado["erros"]) if t).strip() or "O script não mostrou nenhuma mensagem."


class Agendador:
    def __init__(self, armazem, avisar=None):
        """avisar(fala, texto_do_cartao): chamado ao fim de cada execução."""
        self._armazem = armazem
        self._avisar = avisar
        self._parar = threading.Event()

    def iniciar(self) -> None:
        threading.Thread(target=self._repetir, daemon=True).start()

    def parar(self) -> None:
        self._parar.set()

    def _repetir(self) -> None:
        passos = 0
        while not self._parar.wait(1):
            agora = datetime.now()
            try:
                self.verificar_unicos(agora)
                if passos % PASSOS_ENTRE_DIARIOS == 0:
                    self.verificar(agora)
            except Exception as erro:  # um problema num script não pode acabar com os agendamentos dos outros dias
                logger.error("[AGENDADOR] Erro: %s", erro)
            passos += 1

    def verificar(self, agora: datetime) -> None:
        for script in self._armazem.listar():
            agenda = script["agenda"]
            if agenda and agenda.get("ativa") and self._chegou_a_hora(agenda, agora):
                self._armazem.marcar_dia_da_agenda(script["id"], agora.date().isoformat())
                self._rodar(script, agenda, agora)

    def verificar_unicos(self, agora: datetime) -> None:
        for id_script, unica in self._armazem.unicos_vencidos(agora.timestamp()):
            self._armazem.cancelar_unico(id_script)  # antes de rodar: nunca dispara duas vezes
            if agora.timestamp() - unica["em"] > ATRASO_MAXIMO_UMA_VEZ:
                self._armazem.registrar_execucao(id_script, agora.strftime("%d/%m às %H:%M"), False,
                                                 "Não rodou: o Merlin estava fechado na hora marcada.")
                continue
            self._rodar(self._armazem.descrever(id_script), unica, agora)

    @staticmethod
    def _chegou_a_hora(agenda: dict, agora: datetime) -> bool:
        if agenda.get("ultimo_dia") == agora.date().isoformat():
            return False
        hora, minuto = map(int, agenda["hora"].split(":"))
        marcado = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        return marcado <= agora < marcado + JANELA

    def _rodar(self, script: dict, agenda: dict, agora: datetime) -> None:
        id_script = script["id"]
        try:
            resultado = self._armazem.executar_aprovado(id_script, agenda.get("pasta") or "")
            ok, resumo = resultado["ok"], _resumo(resultado)
        except ScriptInvalido as erro:
            ok, resumo = False, str(erro)
        except OSError as erro:
            logger.error("[AGENDADOR] Não consegui rodar %s: %s", id_script, erro)
            ok, resumo = False, "Não consegui rodar o script."
        self._armazem.registrar_execucao(id_script, agora.strftime("%d/%m às %H:%M"), ok, resumo)
        if self._avisar:
            nome = script["aprovado"] or script["pedido"][:MAX_NOME_NO_AVISO]
            situacao = "terminou sem erro" if ok else "não funcionou"
            self._avisar(f"O script agendado {nome} {situacao}. O resultado está no cartão.",
                         f"Script agendado: {nome}\n{'Terminou sem erro' if ok else 'Não funcionou'}\n\n{resumo[-MAX_RESUMO_NO_CARTAO:]}")
