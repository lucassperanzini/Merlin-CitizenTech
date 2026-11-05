"""Descobre o que a pessoa quer. O modelo escreve primeiro o alvo da frase, e as regras daqui têm a palavra final."""
import json
from dataclasses import dataclass
from enum import Enum

from merlin.ia.prompts import PROMPT_INTENCAO
from merlin.texto import normalizar

ALVO_MERLIN = "merlin"
ALVOS_JANELA_DO_MERLIN = {"janela", "essajanela", "estajanela", "ajanela"}


class TipoIntencao(str, Enum):
    DISPENSAR = "dispensar"
    ENCERRAR = "encerrar"
    FECHAR_PROGRAMA = "fechar_programa"
    ABRIR_PROGRAMA = "abrir_programa"
    PESQUISAR_WEB = "pesquisar_web"
    CONVERSAR = "conversar"


@dataclass(frozen=True)
class Intencao:
    tipo: TipoIntencao
    alvo: str  # em PESQUISAR_WEB, é o termo a pesquisar
    comando: str  # a frase original, já sem o nome do Merlin


ESQUEMA_INTENCAO = {
    "type": "object",
    "properties": {
        "alvo": {"type": "string"},
        "intencao": {"type": "string", "enum": [tipo.value for tipo in TipoIntencao]},
        "busca": {"type": "string"},
    },
    "required": ["alvo", "intencao", "busca"],
}


class ClassificadorIntencao:
    def __init__(self, cliente):
        self._cliente = cliente

    def classificar(self, comando: str) -> Intencao:
        """Resposta inválida do modelo vira CONVERSAR, para nunca executar uma ação por engano."""
        resposta = self._cliente.perguntar(
            [{"role": "system", "content": PROMPT_INTENCAO}, {"role": "user", "content": comando}],
            formato=ESQUEMA_INTENCAO,
            opcoes={"temperature": 0},
        )
        try:
            dados = json.loads(resposta)
            tipo = TipoIntencao(dados.get("intencao", TipoIntencao.CONVERSAR))
            alvo = str(dados.get("alvo", "")).strip()
            busca = str(dados.get("busca", "")).strip()
        except (ValueError, AttributeError):
            return Intencao(TipoIntencao.CONVERSAR, "", comando)
        return self._aplicar_regras(tipo, alvo, busca, comando)

    @staticmethod
    def _aplicar_regras(tipo, alvo, busca, comando) -> Intencao:
        sobre_merlin = alvo.lower() == ALVO_MERLIN
        if tipo is TipoIntencao.FECHAR_PROGRAMA and normalizar(alvo) in ALVOS_JANELA_DO_MERLIN:
            # "fecha essa janela" sem citar nada: é a janela dele
            return Intencao(TipoIntencao.DISPENSAR, ALVO_MERLIN, comando)
        if tipo in (TipoIntencao.DISPENSAR, TipoIntencao.ENCERRAR) and not sobre_merlin:
            return Intencao(TipoIntencao.CONVERSAR, alvo, comando)
        if tipo is TipoIntencao.FECHAR_PROGRAMA and sobre_merlin:
            return Intencao(TipoIntencao.DISPENSAR, alvo, comando)
        if tipo is TipoIntencao.ABRIR_PROGRAMA and (sobre_merlin or not alvo):
            return Intencao(TipoIntencao.CONVERSAR, alvo, comando)
        if tipo is TipoIntencao.PESQUISAR_WEB:
            return Intencao(tipo, busca or comando, comando)
        return Intencao(tipo, alvo, comando)
