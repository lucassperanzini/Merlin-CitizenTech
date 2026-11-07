"""Ajustes da Central: assistente (personalidade), voz, modelo de IA e clonagem. As mudanças valem na hora."""
import logging
import threading

import webview

from merlin.acoes.assistentes import trocar_personalidade
from merlin.ia.cliente import listar_modelos
from merlin.personalidades import PERSONALIDADES
from merlin.voz.catalogo import todas_as_vozes
from merlin.voz.clonagem import clonagem_instalada

logger = logging.getLogger(__name__)

# Sem cor escolhida no configurador, vale a cor padrão do visual (a mesma da janela principal)
COR_PADRAO = {"olho": "#d9ac5a", "esfera": "#35d6ff"}


class ServicoConfiguracoes:
    """Aplica as escolhas. Não conhece janelas: avisa a janela principal pelo canal."""

    def __init__(self, preferencias, locutor, canal, memoria, cliente_ia, estado=None, transcritor=None):
        self._estado = estado
        self._transcritor = transcritor
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
        personalidade = self._preferencias.personalidade
        return {
            "nome": personalidade.nome,
            "cor": personalidade.cor or COR_PADRAO.get(personalidade.visual, COR_PADRAO["esfera"]),
            "sistema": self.sistema(ollama=not erro_modelos),
            "personalidades": [{"id": p.id, "nome": p.nome} for p in PERSONALIDADES.values()],
            "personalidade": self._preferencias.personalidade.id,
            "vozes": list(vozes),
            "voz": next((r for r, v in vozes.items() if v == self._preferencias.voz), list(vozes)[0]),
            "modelos": modelos,
            "modelo": atual,
            "erro_modelos": erro_modelos,
        }

    def sistema(self, ollama: bool | None = None) -> dict:
        """O que a barra de status mostra. Cada item: "ok", "desligado" ou "erro", e um texto curto."""
        if ollama is None:
            try:
                listar_modelos()
                ollama = True
            except Exception:
                ollama = False
        dispositivo = getattr(self._transcritor, "dispositivo", "")
        mudo = self._estado is not None and self._estado.microfone_desligado.is_set()
        return {
            "ollama": ("ok", "online") if ollama else ("erro", "offline"),
            "modelo": ("ok" if ollama else "desligado", self._preferencias.modelo_ia),
            "reconhecimento": {"gpu": ("ok", "placa de vídeo"), "cpu": ("desligado", "processador")}.get(
                dispositivo, ("desligado", "carregando")),
            "microfone": ("desligado", "mudo") if mudo else ("ok", "ativo"),
            "clonagem": ("ok", "instalada") if clonagem_instalada() else ("desligado", "não instalada"),
        }

    def trocar_personalidade(self, identificador: str) -> dict:
        # A mesma troca do pedido por voz ("troca para o Jarvis"): merlin/acoes/assistentes.py
        if trocar_personalidade(self._preferencias, self._memoria, self._canal, identificador):
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

    def __init__(self, servico, clonagem=None):
        self._servico = servico
        self._clonagem = clonagem
        self._janela = None

    def _usar_janela(self, janela):
        """Chamado pela JanelaAuxiliar: a caixa de escolher arquivo precisa da janela."""
        self._janela = janela

    # Clonagem de voz (só funciona com a instalação opcional)
    def clonagem_estado(self):
        return self._clonagem.estado() if self._clonagem else {"instalada": False}

    def clonagem_gravar(self):
        return self._clonagem.gravar()

    def clonagem_escolher_arquivo(self):
        tipos = ("Áudio (*.wav;*.mp3;*.m4a;*.ogg;*.flac)",)
        escolhidos = self._janela.create_file_dialog(webview.FileDialog.OPEN, file_types=tipos) if self._janela else None
        if not escolhidos:
            return {"cancelado": True}
        return self._clonagem.usar_arquivo(escolhidos[0])

    def clonagem_salvar(self, nome, texto):
        return self._clonagem.salvar(nome, texto)

    def clonagem_apagar(self):
        return self._clonagem.apagar_voz_atual()

    def carregar(self):
        return self._servico.estado_atual()

    def sistema(self):
        return self._servico.sistema()

    def trocar_personalidade(self, identificador):
        return self._servico.trocar_personalidade(identificador)

    def trocar_voz(self, rotulo):
        self._servico.trocar_voz(rotulo)

    def trocar_modelo(self, modelo):
        return self._servico.trocar_modelo(modelo)

