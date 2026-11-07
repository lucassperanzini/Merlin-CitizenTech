"""Criação de vozes clonadas pela janela de configurações: grava ou abre a amostra, transcreve com o Whisper,
deixa a pessoa conferir o texto e salva. Nada aqui conhece a página: só recebe e devolve dados simples."""
import logging
import threading

import speech_recognition as sr

from merlin.config import DURACAO_GRAVACAO_AMOSTRA, PASTA_VOZES_CLONADAS
from merlin.voz import amostra
from merlin.voz.clonagem import apagar_voz_clonada, buscar_voz_clonada, clonagem_instalada, salvar_voz_clonada

logger = logging.getLogger(__name__)

TEXTO_PARA_LER = ("Olá! Esta é a minha voz. Estou gravando esta frase com calma, em um lugar silencioso, "
                  "para que o assistente aprenda a falar do meu jeito. Um, dois, três: pronto.")


class ServicoClonagem:
    def __init__(self, ouvinte, transcritor, preferencias, locutor, sintetizador, canal, pasta=PASTA_VOZES_CLONADAS):
        self._pasta = pasta
        self._ouvinte = ouvinte
        self._transcritor = transcritor
        self._preferencias = preferencias
        self._locutor = locutor
        self._sintetizador = sintetizador
        self._canal = canal
        self._pendente = None  # (áudio, taxa) aguardando a pessoa conferir o texto e salvar

    def estado(self) -> dict:
        voz_atual = buscar_voz_clonada(self._preferencias.voz, self._pasta)
        return {
            "instalada": clonagem_instalada(),
            "texto_para_ler": TEXTO_PARA_LER,
            "duracao_gravacao": DURACAO_GRAVACAO_AMOSTRA,
            "voz_atual_clonada": voz_atual.nome if voz_atual else "",
        }

    def gravar(self) -> dict:
        try:
            dados = self._ouvinte.gravar(DURACAO_GRAVACAO_AMOSTRA)
            return self._receber(*amostra.de_bytes_16bits(dados, 16000))
        except Exception as erro:
            return self._erro(erro)

    def usar_arquivo(self, caminho: str) -> dict:
        try:
            return self._receber(*amostra.carregar_arquivo(caminho))
        except Exception as erro:
            return self._erro(erro)

    def salvar(self, nome: str, texto: str) -> dict:
        """Salva a amostra pendente e passa a usar a voz nova na personalidade atual."""
        if self._pendente is None:
            return {"erro": "Grave ou escolha uma amostra primeiro."}
        if not nome.strip():
            return {"erro": "Dê um nome à voz."}
        audio, taxa = self._pendente
        voz = salvar_voz_clonada(nome, audio, taxa, texto, self._pasta)
        self._pendente = None
        self._sintetizador.esquecer_voz_clonada(voz.id)  # se regravou com o mesmo nome
        self._preferencias.voz = voz.id
        self._canal.personalidade()
        threading.Thread(target=self._locutor.falar, args=("Olá, esta é a minha nova voz.",), daemon=True).start()
        return {"voz": voz.rotulo}

    def apagar_voz_atual(self) -> dict:
        voz = buscar_voz_clonada(self._preferencias.voz, self._pasta)
        if voz is None:
            return {"erro": "A voz escolhida não é uma voz clonada."}
        apagar_voz_clonada(voz)
        self._sintetizador.esquecer_voz_clonada(voz.id)
        self._preferencias.voz = self._preferencias.personalidade.voz_padrao
        self._canal.personalidade()
        return {}

    def _receber(self, audio, taxa) -> dict:
        audio, taxa = amostra.preparar(audio, taxa)
        texto = self._transcritor.transcrever(sr.AudioData(amostra.para_16bits(audio, taxa), 16000, 2))
        self._pendente = (audio, taxa)
        return {"texto": texto, "duracao": round(len(audio) / taxa, 1)}

    @staticmethod
    def _erro(erro) -> dict:
        if isinstance(erro, amostra.AmostraInvalida):
            return {"erro": str(erro)}
        logger.warning("[VOZ] Falha ao preparar a amostra: %s", erro)
        return {"erro": "Não consegui preparar a amostra. Tente de novo."}
