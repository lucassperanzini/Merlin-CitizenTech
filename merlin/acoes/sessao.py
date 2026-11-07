"""Ações sobre o próprio assistente: dispensar (volta para a espera) e abrir as configurações."""
from merlin.nucleo.resposta import Resultado


class Dispensar:
    def __init__(self, sessao, despedida):
        self._sessao = sessao
        self._despedida = despedida

    def __call__(self, _intencao) -> Resultado:
        return Resultado(self._despedida.gerar(), frase_completa=True, depois=self._sessao.desativar, finaliza=True)


class AbrirConfiguracoes:
    def __init__(self, canal):
        self._canal = canal

    def __call__(self, _intencao) -> Resultado:
        self._canal.abrir_configuracoes()
        return Resultado("abri as configurações", registro="Configurações abertas")
