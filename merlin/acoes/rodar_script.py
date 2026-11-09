"""Roda por voz um script aprovado, sempre com o mesmo código: a IA não escreve nada aqui."""
import logging
import threading
import time

from merlin.automacao.scripts import ArmazemDeScripts, ScriptInvalido
from merlin.nucleo.resposta import Resultado
from merlin.nucleo.sessao import Pendencia

logger = logging.getLogger(__name__)

PRAZO_PARA_DECIDIR = 180
MAX_CARACTERES_NO_CARTAO = 3000


def _em_outra_linha(tarefa) -> None:
    threading.Thread(target=tarefa, daemon=True).start()


def _descrever_resultado(r: dict) -> str:
    titulo = "Parou: passou do tempo limite." if r["tempo_esgotado"] else "Terminou sem erro." if r["ok"] else "O script deu erro."
    corpo = "\n".join(t for t in (r["saida"], r["erros"]) if t).strip() or "O script não mostrou nenhuma mensagem."
    return f"{titulo}\n\n{corpo[-MAX_CARACTERES_NO_CARTAO:]}"


class RodarScript:
    def __init__(self, armazem, sessao, canal, em_segundo_plano=_em_outra_linha):
        self._armazem = armazem
        self._sessao = sessao
        self._canal = canal
        self._em_segundo_plano = em_segundo_plano
        self._ocupado = threading.Lock()  # um script por vez

    def __call__(self, intencao) -> Resultado:
        script = self._armazem.encontrar_aprovado(intencao.alvo, intencao.comando)
        if script is None:
            return Resultado("não tenho um script aprovado com esse nome", registro=f"Sem script aprovado: {intencao.alvo}",
                             frase_completa=True)
        nome, pasta = script["aprovado"], script["pasta"]
        self._sessao.aguardar_confirmacao(Pendencia(
            pergunta="Posso rodar o script?",
            ao_confirmar=lambda: self._iniciar(script["id"], pasta),
            resposta_recusa="Tudo bem, não rodei.",
            expira_em=time.time() + PRAZO_PARA_DECIDIR,
        ))
        cartao = f"Rodar “{nome}”\nem {pasta}" if pasta else f"Rodar “{nome}”"

        def mostrar():
            self._sessao.ativar()
            self._canal.confirmar_script(cartao)
        return Resultado("Confere no cartão. Posso rodar?", registro=f"Aguardando para rodar: {nome}", frase_completa=True,
                         finaliza=True, depois=mostrar)

    def _iniciar(self, id_script: str, pasta: str) -> Resultado:
        """Em segundo plano: um script demorado não pode deixar o assistente surdo."""
        if not self._ocupado.acquire(blocking=False):
            return Resultado("já tem um script rodando", registro="Script já em andamento")
        self._em_segundo_plano(lambda: self._rodar(id_script, pasta))
        return Resultado("rodando. O resultado aparece no cartão", registro=f"Rodando: {id_script}")

    def _rodar(self, id_script: str, pasta: str) -> None:
        try:
            texto = _descrever_resultado(self._armazem.executar_aprovado(id_script, pasta))
        except ScriptInvalido as erro:
            texto = str(erro)
        except Exception as erro:
            logger.error("[SCRIPT] Não consegui rodar: %s", erro)
            texto = "Não consegui rodar o script."
        finally:
            self._ocupado.release()
        self._sessao.ativar()
        self._canal.resultado_script(texto)


def criar(recursos) -> RodarScript:
    return RodarScript(ArmazemDeScripts(), recursos.sessao, recursos.canal)
