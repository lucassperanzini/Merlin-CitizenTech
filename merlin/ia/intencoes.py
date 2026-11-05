"""Descobre o que a pessoa quer. O modelo escreve primeiro o alvo da frase, e as regras daqui têm a palavra final."""
import json
import re
from dataclasses import dataclass
from enum import Enum

from merlin.ia.prompts import PROMPT_INTENCAO
from merlin.texto import normalizar

ALVO_MERLIN = "merlin"
ALVOS_JANELA_DO_MERLIN = {"janela", "essajanela", "estajanela", "ajanela"}

# Travas contra a ação oposta: o modelo às vezes confunde "abre" com "cria" e "liga" com "fecha".
# Elas não decidem a intenção, só vetam o resultado quando a frase começa com o verbo contrário.
_INICIO_DA_FRASE = r"^(?:por favor,?\s+|agora\s+|e\s+)*"
VERBO_ABRIR = re.compile(_INICIO_DA_FRASE + r"(?:abr[ea]|abrir|inici[ae]|iniciar|lig[au]e?|ligar|execut[ae]|executar)\b", re.IGNORECASE)
VERBO_APAGAR = re.compile(_INICIO_DA_FRASE + r"(?:apag[au]e?|apagar|exclu[ai]|excluir|delet[ae]|deletar|remov[ae]|remover)\b", re.IGNORECASE)


class TipoIntencao(str, Enum):
    DISPENSAR = "dispensar"
    ENCERRAR = "encerrar"
    FECHAR_PROGRAMA = "fechar_programa"
    ABRIR_PROGRAMA = "abrir_programa"
    PESQUISAR_WEB = "pesquisar_web"
    CRIAR_PASTA = "criar_pasta"
    CRIAR_ARQUIVO = "criar_arquivo"
    CONVERSAR = "conversar"


@dataclass(frozen=True)
class Intencao:
    tipo: TipoIntencao
    alvo: str  # em PESQUISAR_WEB, é o termo a pesquisar
    comando: str  # a frase original, já sem o nome do Merlin
    local: str = ""  # onde criar a pasta ou o arquivo; vazio = pasta padrão
    conteudo: str = ""  # o que escrever no arquivo


ESQUEMA_INTENCAO = {
    "type": "object",
    "properties": {
        "alvo": {"type": "string"},
        "intencao": {"type": "string", "enum": [tipo.value for tipo in TipoIntencao]},
        "busca": {"type": "string"},
        "local": {"type": "string"},
        "conteudo": {"type": "string"},
    },
    "required": ["alvo", "intencao", "busca", "local", "conteudo"],
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
            local = str(dados.get("local", "")).strip()
            conteudo = str(dados.get("conteudo", "")).strip()
        except (ValueError, AttributeError):
            return Intencao(TipoIntencao.CONVERSAR, "", comando)
        if tipo in (TipoIntencao.CRIAR_PASTA, TipoIntencao.CRIAR_ARQUIVO):
            return self._regras_de_criacao(tipo, alvo, comando, local, conteudo)
        return self._aplicar_regras(tipo, alvo, busca, comando)

    @staticmethod
    def _regras_de_criacao(tipo, alvo, comando, local, conteudo) -> Intencao:
        vetado = VERBO_ABRIR.match(comando) or VERBO_APAGAR.match(comando)
        if vetado or not alvo or alvo.lower() == ALVO_MERLIN:
            return Intencao(TipoIntencao.CONVERSAR, alvo, comando)
        return Intencao(tipo, alvo, comando, local, conteudo)

    @staticmethod
    def _aplicar_regras(tipo, alvo, busca, comando) -> Intencao:
        sobre_merlin = alvo.lower() == ALVO_MERLIN
        if tipo is TipoIntencao.FECHAR_PROGRAMA and VERBO_ABRIR.match(comando):
            tipo = TipoIntencao.ABRIR_PROGRAMA
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
