"""Quando uma busca de focos traz alerta: a bolinha fica vermelha, o Merlin é ativado e fala quantos focos chegaram.

Conta só os focos NOVOS do nível de alerta para cima (ALERT_MIN_LEVEL do .env): os mesmos que o robô avisou.
Uma busca que repete focos já conhecidos não fala de novo; no modo teste, os mesmos focos voltam como novos,
então dá para ouvir o aviso a cada busca.
"""
import logging

logger = logging.getLogger(__name__)

# O nível como ele soa na frase: (singular, plural)
_NIVEIS = {"Crítico": ("crítico", "críticos"), "Alto": ("alto", "altos"), "Médio": ("médio", "médios"),
           "Baixo": ("baixo", "baixos")}


def contar_alertas(resultado: dict) -> list[tuple[str, int]]:
    """[(nível, quantidade)] dos focos novos em alerta, do nível mais grave para o mais leve."""
    contagem, grau = {}, {}
    for foco in resultado.get("focos") or []:
        if foco.get("novo") and foco.get("alerta"):
            contagem[foco["nivel"]] = contagem.get(foco["nivel"], 0) + 1
            grau[foco["nivel"]] = foco.get("grau", 0)
    return sorted(contagem.items(), key=lambda par: -grau[par[0]])


def frase_do_alerta(contagem: list[tuple[str, int]]) -> str:
    """'Alerta de 3 focos de incêndio críticos e 5 altos.' ('' se não há nada a avisar)."""
    partes = []
    for i, (nivel, quantidade) in enumerate(contagem):
        singular, plural = _NIVEIS.get(nivel, (nivel.lower(), nivel.lower() + "s"))
        palavra = singular if quantidade == 1 else plural
        if i == 0:
            partes.append(f"{quantidade} {'foco' if quantidade == 1 else 'focos'} de incêndio {palavra}")
        else:
            partes.append(f"{quantidade} {palavra}")
    if not partes:
        return ""
    lista = partes[0] if len(partes) == 1 else f"{', '.join(partes[:-1])} e {partes[-1]}"
    return f"Alerta de {lista}."


class FalaDeAlerta:
    """Entra na fila de comandos, como uma frase: assim o aviso espera a resposta em andamento terminar."""

    def __init__(self, sessao, locutor, canal, texto, alarme=None):
        self._sessao, self._locutor, self._canal, self.texto = sessao, locutor, canal, texto
        self._alarme = alarme

    def __call__(self) -> None:
        if self._alarme:
            self._alarme.pausar()  # o ciclo do alarme termina antes: a fala entra limpa
        try:
            self._sessao.ativar()  # abre o cartão e toca o som de ativação, como ao chamar pelo nome
            self._canal.atalho_alertas()  # embaixo desta fala, no cartão: o atalho para a aba Alertas
            self._locutor.falar(self.texto)
        finally:
            if self._alarme:
                self._alarme.retomar()  # se ninguém viu os alertas ainda, o alarme volta a tocar


class AvisoDeAlertas:
    """Chamado pela aba Alertas depois de cada busca (manual ou automática)."""

    def __init__(self, estado, sessao, locutor, canal, alarme=None):
        self._estado, self._sessao, self._locutor, self._canal = estado, sessao, locutor, canal
        self._alarme = alarme  # merlin/voz/alarme.py: toca até os alertas serem vistos
        self._pendente = False

    @property
    def pendente(self) -> bool:
        return self._pendente

    def __call__(self, resultado: dict) -> None:
        contagem = contar_alertas(resultado)
        texto = frase_do_alerta(contagem)
        if not texto:
            return
        logger.info("[ALERTAS] %s", texto)
        self._pendente = True
        self._canal.alerta({"quantidade": sum(q for _, q in contagem), "texto": texto})  # a bolinha fica vermelha
        if self._alarme:
            self._alarme.tocar()
        self._estado.fila_comandos.put(FalaDeAlerta(self._sessao, self._locutor, self._canal, texto, self._alarme))

    def visto(self) -> None:
        """A pessoa abriu os alertas (sino, atalho do cartão ou a aba Alertas na Central): o alarme para e a
        bolinha e o cartão voltam às cores normais."""
        if self._alarme:
            self._alarme.parar()
        if not self._pendente:
            return
        self._pendente = False
        logger.info("[ALERTAS] Alertas vistos.")
        self._canal.alerta(None)
