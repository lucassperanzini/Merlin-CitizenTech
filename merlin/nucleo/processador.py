"""Decide o que fazer com cada frase: ativar, resolver uma confirmação ou executar as tarefas pedidas.
Cada etapa fica anotada no raciocínio, que a janela de raciocínio mostra."""
import logging
import re
import time
from dataclasses import replace
from typing import Callable, Mapping

from merlin import habilidades
from merlin.ia.confirmacao import RespostaConfirmacao
from merlin.ia.intencoes import ACOES_NO_COMPUTADOR, PEDIDOS_DE_FRASE_INTEIRA, Intencao, TipoIntencao
from merlin.interface.eventos import EstadoVisual
from merlin.nucleo.raciocinio import Raciocinio, TipoPasso
from merlin.nucleo.resposta import Resultado, montar_resposta
from merlin.personalidades import NOMES_DO_ASSISTENTE, personalidade_padrao
from merlin.texto import remover_palavra_ativacao, tem_palavra_ativacao

logger = logging.getLogger(__name__)

Acao = Callable[[Intencao], Resultado]

AVISO_SEM_IA = "Não consegui falar com o meu cérebro. Verifique se o Ollama está rodando."
# "Quais as suas capacidades?" é sobre o assistente, não sobre os manuais, mas a busca dá nota alta a ela
# (0,837 para um limite de 0,836): quem fala com o assistente não é desviado para os protocolos
FALA_COM_O_ASSISTENTE = re.compile(r"\b(?:voc[eê]s?|vc|te|tu|contigo|seus?|suas?)\b", re.IGNORECASE)
LIMITE_DO_BALAO = 90  # modo discreto: respostas até este tamanho cabem no balão ao lado da bolinha


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
                 acoes: Mapping[TipoIntencao, Acao], memoria=None, preferencias=None, raciocinio=None,
                 especialista=None, so_especialista=False):
        """especialista: o modelo da Defesa Civil. Confere as frases que a IA entendeu como conversa: se forem
        perguntas dos protocolos, vão para consultar_protocolo. so_especialista: toda pergunta vai direto a ele,
        sem dividir a frase nem procurar uma skill (config.MODO_ESPECIALISTA)."""
        self._especialista = especialista
        self._so_especialista = so_especialista and especialista is not None
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
        self._intencoes: list[Intencao] = []  # as do último pedido, para decidir se cabe no balão

    def processar(self, frase: str) -> None:
        palavras = self._palavras_ativacao()
        ativou_agora = not self._estado.ativo.is_set()
        if ativou_agora and not tem_palavra_ativacao(frase, palavras):
            return
        comando = remover_palavra_ativacao(frase, palavras)
        legenda = formatar_legenda(frase)
        # Modo discreto: chamou já com um pedido ("Merlin, abre o chrome"). Ele é resolvido sem abrir o cartão;
        # se a resposta não couber num balão ao lado da bolinha (uma conversa, uma pergunta, um erro), o cartão abre.
        discreto = ativou_agora and bool(comando)
        if ativou_agora:
            self._sessao.ativar(mostrar=not discreto)

        # A janela mostra o que a pessoa disse, como foi entendido: assim ela vê na hora se o Whisper errou
        if not discreto:
            self._canal.legenda(legenda)
        self._canal.estado(EstadoVisual.PENSANDO)
        self._raciocinio.registrar(TipoPasso.OUVI, formatar_legenda(frase),
                                   ativou_agora="sim" if ativou_agora else "", comando=comando if comando != frase else "",
                                   modelo=self._nome_do_modelo())

        # Qualquer frase depois da pergunta encerra a espera: só um "sim" claro executa a ação
        pendencia = self._sessao.pegar_pendencia()

        if not comando:
            resposta = self._saudacao.gerar() if ativou_agora else "Pois não?"
            self._raciocinio.registrar(TipoPasso.FALA, resposta, motivo="só chamou pelo nome")
            self._locutor.falar(resposta)
            return

        if self._so_especialista:
            if discreto:  # a resposta é longa demais para o balão: abre o cartão
                self._abrir_cartao(legenda)
            self._consultar_especialista(comando)
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
            if discreto:
                self._abrir_cartao(legenda)
            self._locutor.falar(AVISO_SEM_IA)
            return
        resultados = self._executar_tarefas(comando, tarefas)
        if discreto and self._cabe_no_balao(resultados):
            self._responder_no_balao(resultados)
            return
        if discreto:
            self._abrir_cartao(legenda)
        self._responder(resultados, comando)

    def _nome_do_modelo(self) -> str:
        if self._so_especialista:
            return self._especialista.nome
        return self._preferencias.modelo_ia if self._preferencias else ""

    def _consultar_especialista(self, comando: str) -> None:
        inicio = time.perf_counter()
        try:
            r = self._especialista.responder(comando)
        except Exception as erro:
            logger.error("[ESPECIALISTA] Erro: %s", erro)
            self._raciocinio.registrar(TipoPasso.ERRO, "O modelo da Defesa Civil falhou", erro=erro)
            self._locutor.falar("Tive um problema ao consultar os protocolos. Tente de novo.")
            return
        self._raciocinio.registrar(
            TipoPasso.ACAO, "Consultei os protocolos da Defesa Civil" if r.encontrou else "Não está nos protocolos",
            fontes=[f"{f.documento} · {f.para_falar()}" for f in r.fontes] or "",
            avisos=list(r.avisos) or "", confianca=f"{r.confianca:.3f}" if r.confianca is not None else "",
            tempo=duracao(inicio))
        resposta = r.para_falar()
        if self._memoria:
            self._memoria.registrar(comando, resposta)
        self._raciocinio.registrar(TipoPasso.FALA, resposta)
        self._locutor.falar(resposta)

    def _abrir_cartao(self, legenda: str) -> None:
        """O pedido discreto precisou do cartão: ele abre já mostrando o que a pessoa disse."""
        self._sessao.ativar()
        self._canal.legenda(legenda)
        self._canal.estado(EstadoVisual.PENSANDO)

    def _cabe_no_balao(self, resultados: list[Resultado]) -> bool:
        """Só ações rápidas no computador, com resposta curta e sem pergunta pendente, ficam no balão."""
        return (bool(self._intencoes) and all(i.tipo in ACOES_NO_COMPUTADOR for i in self._intencoes)
                and not any(r.frase_completa for r in resultados) and not self._sessao.tem_pendencia()
                and len(montar_resposta(resultados)) <= LIMITE_DO_BALAO)

    def _responder_no_balao(self, resultados: list[Resultado]) -> None:
        """Fala a resposta num balão ao lado da bolinha e volta a esperar: o próximo pedido precisa do nome de
        novo (sem o cartão aberto, a pessoa não saberia que ele continua ouvindo)."""
        resposta = montar_resposta(resultados)
        self._raciocinio.registrar(TipoPasso.FALA, resposta, motivo="resposta curta: no balão, sem abrir o cartão")
        self._canal.aviso(resposta)
        self._locutor.falar(resposta)
        for resultado in resultados:
            if resultado.depois:
                resultado.depois()
        if self._estado.ativo.is_set():
            self._sessao.desativar()

    def _palavras_ativacao(self):
        personalidade = self._preferencias.personalidade if self._preferencias else personalidade_padrao()
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
        self._intencoes = []
        try:
            intencoes = self._entender(comando, tarefas)
            self._intencoes = intencoes
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
        if any(i.tipo in PEDIDOS_DE_FRASE_INTEIRA for i in intencoes):
            self._raciocinio.registrar(TipoPasso.REGRA, "O resto da frase faz parte do pedido: ela volta a ser uma só",
                                       motivo="o que vem depois de \"dizendo que\" é conteúdo, não outra tarefa")
            return [self._classificar(comando)]
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
        return self._confirmar_protocolo(intencao)

    def _confirmar_protocolo(self, intencao: Intencao) -> Intencao:
        """A IA de conversa pode não reconhecer uma pergunta dos protocolos ("e se o vento virar?"). A busca nos
        documentos confere: se ela acha um trecho parecido o bastante, quem responde é o especialista, que cita a
        fonte, e não a conversa livre, que poderia inventar um procedimento."""
        protocolo = getattr(TipoIntencao, "CONSULTAR_PROTOCOLO", None)
        if (intencao.tipo is not TipoIntencao.CONVERSAR or protocolo is None or not self._especialista
                or not habilidades.esta_ligada(protocolo.value)):
            return intencao
        if FALA_COM_O_ASSISTENTE.search(intencao.comando) or intencao.alvo.lower() in NOMES_DO_ASSISTENTE:
            return intencao  # pergunta sobre o próprio assistente: a conversa sabe o que ele faz
        try:
            achou = self._especialista.parece_protocolo(intencao.comando)
        except Exception as erro:  # sem a busca, a conversa segue normalmente
            logger.warning("[ESPECIALISTA] Não consegui conferir nos protocolos: %s", erro)
            return intencao
        if not achou:
            return intencao
        motivo = "a busca encontrou um trecho dos protocolos parecido com a pergunta"
        self._raciocinio.registrar(TipoPasso.REGRA, f"O código mudou a decisão do modelo para {protocolo.value}",
                                   motivo=motivo)
        return replace(intencao, tipo=protocolo, motivo_regra=motivo)

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
