"""Canal de mensagens para a janela. O resto do programa usa isto e nunca precisa conhecer a janela em si."""
import queue
from enum import Enum


class EstadoVisual(str, Enum):
    """Os valores são os nomes usados pela página da janela."""

    ESPERA = "espera"
    OUVINDO = "ouvindo"
    PENSANDO = "pensando"
    FALANDO = "falando"


class TipoEvento(Enum):
    MOSTRAR = "mostrar"
    ESCONDER = "esconder"
    ESTADO = "estado"
    LEGENDA = "legenda"  # o que a pessoa disse
    RESPOSTA = "resposta"  # o assistente vai começar a falar: a janela prepara o espaço da resposta
    TRECHO_FALADO = "trecho_falado"  # um pedaço da resposta começou a tocar: o texto aparece junto com a voz
    FALA_INTERROMPIDA = "fala_interrompida"  # a pessoa falou por cima: o texto para onde a voz parou
    ENVELOPE_FALA = "envelope_fala"
    PERSONALIDADE = "personalidade"
    ABRIR_CONFIGURACOES = "abrir_configuracoes"
    RASCUNHO = "rascunho"  # um texto escrito pela IA, no cartão, com os botões Colar, Copiar e Descartar
    SCRIPT = "script"  # o script foi criado: o cartão mostra a explicação e os botões Ver script e Descartar
    ABRIR_SCRIPT = "abrir_script"  # abre a aba Automações já no script indicado
    CONFIRMAR_SCRIPT = "confirmar_script"  # nome e pasta de um script aprovado, com os botões Confirmar e Cancelar
    RESULTADO_SCRIPT = "resultado_script"  # o que o script mostrou, no cartão
    AVISO = "aviso"  # modo discreto: uma resposta curta num balão ao lado da bolinha, sem abrir o cartão


class CanalInterface:
    def __init__(self):
        self._fila = queue.Queue()

    def mostrar(self) -> None:
        self._fila.put((TipoEvento.MOSTRAR, None))

    def esconder(self) -> None:
        self._fila.put((TipoEvento.ESCONDER, None))

    def estado(self, estado: EstadoVisual) -> None:
        self._fila.put((TipoEvento.ESTADO, estado))

    def legenda(self, texto: str) -> None:
        """O que a pessoa disse (uma pergunta nova apaga a resposta anterior da tela)."""
        self._fila.put((TipoEvento.LEGENDA, texto))

    def resposta(self) -> None:
        """O assistente vai começar a falar: a resposta aparece abaixo do que a pessoa disse."""
        self._fila.put((TipoEvento.RESPOSTA, None))

    def trecho_falado(self, texto: str, duracao: float) -> None:
        """Um pedaço da resposta começou a tocar. As palavras aparecem ao longo da duração (0 = de uma vez)."""
        self._fila.put((TipoEvento.TRECHO_FALADO, {"texto": texto, "duracao": duracao}))

    def fala_interrompida(self) -> None:
        self._fila.put((TipoEvento.FALA_INTERROMPIDA, None))

    def envelope_fala(self, volumes: list[float], passo: float) -> None:
        """Volume da fala que vai começar, para a aparência acompanhar a voz."""
        self._fila.put((TipoEvento.ENVELOPE_FALA, {"volumes": volumes, "passo": passo}))

    def personalidade(self) -> None:
        self._fila.put((TipoEvento.PERSONALIDADE, None))

    def rascunho(self, texto: str) -> None:
        self._fila.put((TipoEvento.RASCUNHO, texto))

    def script(self, texto: str) -> None:
        self._fila.put((TipoEvento.SCRIPT, texto))

    def confirmar_script(self, texto: str) -> None:
        self._fila.put((TipoEvento.CONFIRMAR_SCRIPT, texto))

    def resultado_script(self, texto: str) -> None:
        self._fila.put((TipoEvento.RESULTADO_SCRIPT, texto))

    def abrir_script(self, id_script: str) -> None:
        self._fila.put((TipoEvento.ABRIR_SCRIPT, id_script))

    def aviso(self, texto: str) -> None:
        self._fila.put((TipoEvento.AVISO, texto))

    def abrir_configuracoes(self) -> None:
        self._fila.put((TipoEvento.ABRIR_CONFIGURACOES, None))

    def proximo(self, tempo_limite: float):
        """Retorna (tipo, dado), ou (None, None) se nada chegar dentro do tempo limite."""
        try:
            return self._fila.get(timeout=tempo_limite)
        except queue.Empty:
            return None, None
