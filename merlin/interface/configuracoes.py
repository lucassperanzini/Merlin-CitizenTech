"""Ajustes da Central: assistente (personalidade), voz e modelo de IA. As mudanças valem na hora."""
import logging
import threading
from pathlib import Path

import webview

from merlin.acoes.assistentes import trocar_personalidade
from merlin.ia.cliente import listar_modelos
from merlin.interface.perfil import AVISO_SO_ADMINISTRADOR
from merlin.personalidades import PERSONALIDADES
from merlin.voz.catalogo import todas_as_vozes

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
        }

    # --- Pastas: apelidos da pessoa e o que o Acesso Rápido do Windows já oferece
    def pastas_estado(self) -> dict:
        from merlin.acoes.pastas import pastas_do_acesso_rapido
        return {
            "apelidos": [{**i, "existe": Path(i["caminho"]).is_dir()} for i in self._preferencias.apelidos_pastas],
            "acesso_rapido": [{"nome": n, "caminho": str(c), "fixada": f} for n, c, f in pastas_do_acesso_rapido()],
        }

    def pastas_salvar(self, itens: list) -> dict:
        """Confere tudo antes de salvar: apelido preenchido e sem repetir, e uma pasta que existe."""
        limpos, vistos = [], set()
        for item in itens or []:
            apelido, caminho = str(item.get("apelido", "")).strip(), str(item.get("caminho", "")).strip()
            if not apelido and not caminho:
                continue
            if not apelido:
                return {"erro": f"Dê um apelido para a pasta {caminho}."}
            if not caminho or not Path(caminho).is_dir():
                return {"erro": f"Escolha uma pasta que exista para o apelido “{apelido}”."}
            chave = apelido.lower()
            if chave in vistos:
                return {"erro": f"O apelido “{apelido}” aparece duas vezes."}
            vistos.add(chave)
            limpos.append({"apelido": apelido, "caminho": caminho})
        self._preferencias.apelidos_pastas = limpos
        return self.pastas_estado()

    def trocar_personalidade(self, identificador: str) -> dict:
        # A mesma troca do pedido por voz ("troca para a Ana"): merlin/acoes/assistentes.py
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
        if not self._preferencias.administrador:
            return AVISO_SO_ADMINISTRADOR
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

    def __init__(self, servico):
        self._servico = servico
        self._janela = None

    def _usar_janela(self, janela):
        """Chamado pela JanelaAuxiliar: a caixa de escolher arquivo precisa da janela."""
        self._janela = janela

    def carregar(self):
        return self._servico.estado_atual()

    def pastas_estado(self):
        return self._servico.pastas_estado()

    def pastas_salvar(self, itens):
        return self._servico.pastas_salvar(itens)

    def pastas_escolher(self):
        """Abre o seletor de pastas do Windows; devolve o caminho escolhido, ou "" se a pessoa cancelar."""
        escolhidas = self._janela.create_file_dialog(webview.FileDialog.FOLDER) if self._janela else None
        return escolhidas[0] if escolhidas else ""

    def sistema(self):
        return self._servico.sistema()

    def trocar_personalidade(self, identificador):
        return self._servico.trocar_personalidade(identificador)

    def trocar_voz(self, rotulo):
        self._servico.trocar_voz(rotulo)

    def trocar_modelo(self, modelo):
        return self._servico.trocar_modelo(modelo)

