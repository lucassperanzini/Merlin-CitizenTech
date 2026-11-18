"""Responde pelos protocolos da Defesa Civil, com o modelo especialista. Nunca cai para a conversa livre: se a
resposta não está nos documentos, é isso que o assistente diz (um modelo geral inventaria um procedimento)."""
from merlin.nucleo.resposta import Resultado


class ConsultarProtocolo:
    def __init__(self, especialista):
        self._especialista = especialista

    def __call__(self, intencao) -> Resultado:
        r = self._especialista.responder(intencao.comando)
        fontes = "; ".join(f"{f.documento} {f.para_falar()}" for f in r.fontes)
        registro = f"Protocolos: {fontes}" if fontes else "Protocolos: a resposta não está nos documentos"
        return Resultado(r.para_falar(), registro=registro, frase_completa=True, fontes=r.fontes)
