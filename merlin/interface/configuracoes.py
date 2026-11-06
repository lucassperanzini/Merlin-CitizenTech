"""Janela de configurações: assistente (personalidade), voz e modelo de IA. As mudanças valem na hora."""
import logging
import threading

from merlin.config import ARQ_CONFIGURACOES
from merlin.ia.cliente import listar_modelos
from merlin.interface.janela_auxiliar import JanelaAuxiliar
from merlin.personalidades import PERSONALIDADES
from merlin.voz.catalogo import todas_as_vozes

logger = logging.getLogger(__name__)

LARGURA, ALTURA = 460, 680


class ServicoConfiguracoes:
    """Aplica as escolhas. Não conhece janelas: avisa a janela principal pelo canal."""

    def __init__(self, preferencias, locutor, canal, memoria, cliente_ia):
        self._preferencias = preferencias
        self._locutor = locutor
        self._canal = canal
        self._memoria = memoria
        self._cliente_ia = cliente_ia

    def estado_atual(self) -> dict:
        try:
            modelos = [{"nome": m.nome, "detalhe": " · ".join(x for x in (m.parametros, f"{m.tamanho_gb} GB") if x)}
                       for m in listar_modelos()]
            erro_modelos = ""
        except Exception as erro:
            logger.warning("[CONFIG] Não consegui listar os modelos do Ollama: %s", erro)
            modelos, erro_modelos = [], "Não consegui falar com o Ollama. Verifique se ele está aberto."
        atual = self._preferencias.modelo_ia
        vozes = todas_as_vozes()
        if atual not in [m["nome"] for m in modelos]:
            modelos.insert(0, {"nome": atual, "detalhe": "não encontrado no Ollama"})
        return {
            "personalidades": [{"id": p.id, "nome": p.nome} for p in PERSONALIDADES.values()],
            "personalidade": self._preferencias.personalidade.id,
            "vozes": list(vozes),
            "voz": next((r for r, v in vozes.items() if v == self._preferencias.voz), list(vozes)[0]),
            "modelos": modelos,
            "modelo": atual,
            "erro_modelos": erro_modelos,
        }

    def trocar_personalidade(self, identificador: str) -> dict:
        if identificador in PERSONALIDADES and identificador != self._preferencias.personalidade.id:
            self._preferencias.personalidade = identificador
            self._memoria.limpar()  # a conversa anterior era com a outra personalidade
            self._canal.personalidade()
            self._falar(self._preferencias.personalidade.apresentacao)
        return self.estado_atual()  # a voz mostrada muda junto: cada personalidade tem a sua

    def trocar_voz(self, rotulo: str) -> None:
        vozes = todas_as_vozes()
        if rotulo in vozes:
            self._preferencias.voz = vozes[rotulo]
            self._canal.personalidade()
            self._falar("Olá, esta é a minha nova voz.")

    def trocar_modelo(self, modelo: str) -> str:
        """Retorna uma mensagem de erro, ou "" se deu certo."""
        try:
            instalados = [m.nome for m in listar_modelos()]
        except Exception:
            return "Não consegui falar com o Ollama. Verifique se ele está aberto."
        if modelo not in instalados:
            return f"O modelo {modelo} não está instalado no Ollama."
        self._preferencias.modelo_ia = modelo
        # Carrega o modelo novo agora, para a próxima pergunta não demorar
        threading.Thread(target=self._cliente_ia.preaquecer, daemon=True).start()
        return ""

    def _falar(self, texto):
        threading.Thread(target=self._locutor.falar, args=(texto,), daemon=True).start()


class ApiConfiguracoes:
    """Funções que a página de configurações pode chamar (atributos privados: o pywebview expõe os públicos)."""

    def __init__(self, servico, abrir_raciocinio=None):
        self._servico = servico
        self._abrir_raciocinio = abrir_raciocinio

    def abrir_raciocinio(self):
        if self._abrir_raciocinio:
            self._abrir_raciocinio()

    def carregar(self):
        return self._servico.estado_atual()

    def trocar_personalidade(self, identificador):
        return self._servico.trocar_personalidade(identificador)

    def trocar_voz(self, rotulo):
        self._servico.trocar_voz(rotulo)

    def trocar_modelo(self, modelo):
        return self._servico.trocar_modelo(modelo)


class JanelaConfiguracoes(JanelaAuxiliar):
    def __init__(self, servico, abrir_raciocinio=None):
        super().__init__("Configurações", ARQ_CONFIGURACOES, ApiConfiguracoes(servico, abrir_raciocinio), LARGURA, ALTURA)
