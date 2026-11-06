"""Decide o que fazer com cada frase: ativar, resolver uma confirmação ou executar as tarefas pedidas.
Cada etapa fica anotada no raciocínio, que a janela de raciocínio mostra."""
import logging
import time
from typing import Callable, Mapping

from merlin.ia.confirmacao import RespostaConfirmacao
from merlin.ia.intencoes import ACOES_NO_COMPUTADOR, Intencao, TipoIntencao
from merlin.interface.eventos import EstadoVisual
from merlin.nucleo.raciocinio import Raciocinio, TipoPasso
from merlin.nucleo.resposta import Resultado, montar_resposta
from merlin.personalidades import PERSONALIDADE_PADRAO
from merlin.texto import remover_palavra_ativacao, tem_palavra_ativacao

logger = logging.getLogger(__name__)

Acao = Callable[[Intencao], Resultado]

AVISO_SEM_IA = "Não consegui falar com o meu cérebro. Verifique se o Ollama está rodando."


def formatar_legenda(frase: str) -> str:
    """O Whisper devolve tudo em minúsculas; a primeira letra maiúscula deixa a leitura mais natural."""
    frase = frase.strip()
    return frase[:1].upper() + frase[1:]


def duracao(inicio: float) -> float | None:
    """Segundos desde o início; None quando foi instantâneo (a IA nem foi chamada), para não poluir o raciocínio."""
    segundos = time.perf_counter() - inicio
    return segundos if segundos >= 0.01 else None


class ProcessadorComandos:
    def __init__(self, estado, sessao, canal, locutor, divisor, classificador, confirmador, saudacao,
                 acoes: Mapping[TipoIntencao, Acao], memoria=None, preferencias=None, raciocinio=None):
        self._raciocinio = raciocinio or Raciocinio()
        self._preferencias = preferencias
        self._memoria = memoria
        self._estado = estado
        self._sessao = sessao
        self._canal = canal
        self._locutor = locutor
        self._divisor = divisor
        self._classificador = classificador
        self._confirmador = confirmador
        self._saudacao = saudacao
        self._acoes = acoes

    def processar(self, frase: str) -> None:
        palavras = self._palavras_ativacao()
        ativou_agora = not self._estado.ativo.is_set()
        if ativou_agora:
            if not tem_palavra_ativacao(frase, palavras):
                return
            self._sessao.ativar()

        comando = remover_palavra_ativacao(frase, palavras)
        # A janela mostra o que a pessoa disse, como foi entendido: assim ela vê na hora se o Whisper errou
        self._canal.legenda(formatar_legenda(frase))
        self._canal.estado(EstadoVisual.PENSANDO)
        self._raciocinio.registrar(TipoPasso.OUVI, formatar_legenda(frase),
                                   ativou_agora="sim" if ativou_agora else "", comando=comando if comando != frase else "",
                                   modelo=self._preferencias.modelo_ia if self._preferencias else "")

        # Qualquer frase depois da pergunta encerra a espera: só um "sim" claro executa a ação
        pendencia = self._sessao.pegar_pendencia()

        if not comando:
            resposta = self._saudacao.gerar() if ativou_agora else "Pois não?"
            self._raciocinio.registrar(TipoPasso.FALA, resposta, motivo="só chamou pelo nome")
            self._locutor.falar(resposta)
            return

        try:
            if pendencia and self._resolver_pendencia(pendencia, comando):
                return
            inicio = time.perf_counter()
            tarefas = self._divisor.dividir(comando)
            self._raciocinio.registrar(TipoPasso.TAREFAS, f"{len(tarefas)} tarefa(s)" if len(tarefas) > 1 else "Uma tarefa só",
                                       partes=[f"“{t}”" for t in tarefas] if len(tarefas) > 1 else "",
                                       tempo=duracao(inicio))
        except Exception as erro:
            logger.error("[IA] Erro: %s", erro)
            self._raciocinio.registrar(TipoPasso.ERRO, "Não consegui falar com a IA", erro=erro)
            self._locutor.falar(AVISO_SEM_IA)
            return
        self._responder(self._executar_tarefas(comando, tarefas), comando)

    def _palavras_ativacao(self):
        personalidade = self._preferencias.personalidade if self._preferencias else PERSONALIDADE_PADRAO
        return personalidade.palavras_ativacao

    def _resolver_pendencia(self, pendencia, comando) -> bool:
        """Retorna True se a frase respondeu à pergunta; caso contrário, ela segue como um comando normal."""
        resposta = self._confirmador.classificar(pendencia.pergunta, comando)
        logger.info("[CONFIRMAÇÃO]: %s", resposta.value)
        self._raciocinio.registrar(TipoPasso.CONFIRMACAO, f"Resposta à pergunta: {resposta.value}",
                                   pergunta=pendencia.pergunta)
        if resposta is RespostaConfirmacao.SIM:
            self._responder([self._registrar_acao(pendencia.ao_confirmar())], comando)
            return True
        if resposta is RespostaConfirmacao.NAO:
            self._raciocinio.registrar(TipoPasso.FALA, pendencia.resposta_recusa)
            self._locutor.falar(pendencia.resposta_recusa)
            return True
        return False

    def _executar_tarefas(self, comando: str, tarefas: list[str]) -> list[Resultado]:
        resultados = []
        try:
            intencoes = self._entender(comando, tarefas)
        except Exception as erro:
            logger.error("[IA] Erro: %s", erro)
            self._raciocinio.registrar(TipoPasso.ERRO, "Não consegui falar com a IA", erro=erro)
            return [Resultado(AVISO_SEM_IA, frase_completa=True)]

        for intencao in intencoes:
            try:
                resultado = self._executar_intencao(intencao)
            except Exception as erro:
                # O que já foi feito continua na resposta
                logger.error("[IA] Erro: %s", erro)
                self._raciocinio.registrar(TipoPasso.ERRO, f"Falhou ao executar {intencao.tipo.value}", erro=erro)
                resultados.append(Resultado(AVISO_SEM_IA, frase_completa=True))
                break
            resultados.append(resultado)
            if resultado.finaliza:
                break
        return resultados

    def _entender(self, comando: str, tarefas: list[str]) -> list[Intencao]:
        """Só vale separar a frase se alguma parte mexer no computador. "Fala aí, tudo bem?" é uma conversa só:
        separada, o "tudo bem" sozinho chegou a ser entendido como despedida."""
        intencoes = [self._classificar(tarefa) for tarefa in tarefas]
        if len(intencoes) == 1:
            return intencoes
        logger.info("[TAREFAS]: %s", tarefas)
        if any(i.tipo in ACOES_NO_COMPUTADOR for i in intencoes):
            return intencoes
        logger.info("[TAREFAS]: nenhuma parte é uma ação; a frase segue inteira")
        self._raciocinio.registrar(TipoPasso.REGRA, "Nenhuma parte mexe no computador: a frase volta a ser uma só",
                                   motivo="separar uma conversa faz partes soltas serem mal entendidas")
        return [self._classificar(comando)]

    def _classificar(self, comando: str) -> Intencao:
        inicio = time.perf_counter()
        intencao = self._classificador.classificar(comando)
        logger.info("[INTENÇÃO]: %s (alvo: %s, local: %s)", intencao.tipo.value, intencao.alvo, intencao.local)
        modelo = intencao.resposta_modelo
        self._raciocinio.registrar(
            TipoPasso.INTENCAO, f"“{comando}” → {intencao.tipo.value}",
            alvo=intencao.alvo, programa=intencao.local, tempo=duracao(inicio),
            resposta_do_modelo=", ".join(f"{k}: {v}" for k, v in modelo.items() if v) if modelo else "")
        if intencao.motivo_regra:
            self._raciocinio.registrar(TipoPasso.REGRA, f"O código mudou a decisão do modelo para {intencao.tipo.value}",
                                       motivo=intencao.motivo_regra)
        return intencao

    def _executar_intencao(self, intencao: Intencao) -> Resultado:
        return self._registrar_acao(self._acoes[intencao.tipo](intencao))

    def _registrar_acao(self, resultado: Resultado) -> Resultado:
        if resultado.registro:  # sem registro (uma conversa, por exemplo), a resposta já aparece em "Falei"
            logger.info("[LOG]: %s", resultado.registro)
            self._raciocinio.registrar(TipoPasso.ACAO, resultado.registro)
        return resultado

    def _responder(self, resultados: list[Resultado], comando: str) -> None:
        resposta = montar_resposta(resultados)
        if self._memoria:
            self._memoria.registrar(comando, resposta)
        self._raciocinio.registrar(TipoPasso.FALA, resposta)
        self._locutor.falar(resposta)
        for resultado in resultados:
            if resultado.depois:
                resultado.depois()
