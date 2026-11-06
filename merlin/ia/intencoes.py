"""Descobre o que a pessoa quer. O modelo escreve primeiro o alvo da frase, e as regras daqui têm a palavra final."""
import json
import re
from dataclasses import dataclass, field, replace
from enum import Enum

from merlin.ia.prompts import PROMPT_INTENCAO
from merlin.personalidades import NOMES_DO_ASSISTENTE
from merlin.texto import normalizar

ALVO_MERLIN = "merlin"  # o prompt pede este alvo quando a frase é dirigida ao próprio assistente
ALVOS_JANELA_DO_MERLIN = {"janela", "essajanela", "estajanela", "ajanela"}

# Travas contra a ação oposta: o modelo às vezes confunde "abre" com "cria" e "liga" com "fecha".
# Elas não decidem a intenção, só vetam o resultado quando a frase começa com o verbo contrário.
_INICIO_DA_FRASE = (r"^(?:por favor,?\s+|agora\s+|e\s+|(?:voc[eê]\s+)?pode\s+|"
                    r"(?:eu\s+)?(?:quero|preciso)\s+que\s+(?:voc[eê]\s+)?)*")
VERBO_ABRIR = re.compile(_INICIO_DA_FRASE + r"(?:abr[ea]|abrir|inici[ae]|iniciar|lig[au]e?|ligar|execut[ae]|executar)\b", re.IGNORECASE)
# Clicar exige uma ordem: a frase precisa começar pelo verbo, e não por uma pergunta.
# Além de "clica" e "aperta", valem os verbos que já dizem qual botão é ("dá play", "salva", "pula").
VERBO_CLICAR = re.compile(
    _INICIO_DA_FRASE + r"(?:clic[ae]|clique|clicar|apert[ae]|apertar|pression[ae]|pressionar|"
    r"d[aá] um clique|toc[ae]|toque|tocar|selecion[ae]|selecionar|marc[ae]|marcar|aciona|acione|acionar|"
    r"d[aá]\s+(?:um\s+)?(?:play|pause|pausa|ok|enter)|play|pause|paus[ae]|pausar|"
    r"salv[ae]|salvar|confirm[ae]|confirmar|cancel[ae]|cancelar|envi[ae]|enviar|"
    r"avan[cç][ae]|avan[cç]ar|pul[ae]|pular|volt[ae]|voltar|aceit[ae]|aceitar|continu[ae]|continuar|"
    r"escolh[ae]|escolher)\b",
    re.IGNORECASE,
)


# Abrir as configurações do assistente também exige uma ordem, e não pode ser de outra coisa
PERGUNTA = re.compile(
    _INICIO_DA_FRASE + r"(?:como|onde|qual|quais|o que|oque|por ?que|cad[eê]|ser[aá] que|d[aá] pra|tem como)\b",
    re.IGNORECASE,
)
CONFIGURACOES_DE_OUTRO = re.compile(
    r"(?:configura\w*|ajustes?|op[cç][oõ]es|prefer[eê]ncias)\s+d[oae]s?\s+(?!seu\b|sua\b|voc)(\w+)", re.IGNORECASE
)
DONOS_DO_SISTEMA = {"windows", "pc", "computador", "sistema", "notebook"}


class TipoIntencao(str, Enum):
    DISPENSAR = "dispensar"
    ENCERRAR = "encerrar"
    FECHAR_PROGRAMA = "fechar_programa"
    ABRIR_PROGRAMA = "abrir_programa"
    PESQUISAR_WEB = "pesquisar_web"
    VER_BOTOES = "ver_botoes"
    CLICAR_BOTAO = "clicar_botao"
    ABRIR_CONFIGURACOES = "abrir_configuracoes"
    CONVERSAR = "conversar"


# Pedidos que fazem algo no computador. Conversa, despedida e encerramento não entram aqui.
ACOES_NO_COMPUTADOR = frozenset({
    TipoIntencao.FECHAR_PROGRAMA, TipoIntencao.ABRIR_PROGRAMA, TipoIntencao.PESQUISAR_WEB,
    TipoIntencao.VER_BOTOES, TipoIntencao.CLICAR_BOTAO,
})


@dataclass(frozen=True)
class Intencao:
    tipo: TipoIntencao
    alvo: str  # em PESQUISAR_WEB, é o termo a pesquisar
    comando: str  # a frase original, já sem o nome do Merlin
    local: str = ""  # em CLICAR_BOTAO, o programa onde clicar; vazio = a janela em uso
    # Para a janela de raciocínio: o que o modelo respondeu e, se uma regra do código mudou a decisão, por quê
    resposta_modelo: dict = field(default_factory=dict, compare=False)
    motivo_regra: str = field(default="", compare=False)


ESQUEMA_INTENCAO = {
    "type": "object",
    "properties": {
        "alvo": {"type": "string"},
        "intencao": {"type": "string", "enum": [tipo.value for tipo in TipoIntencao]},
        "busca": {"type": "string"},
        "local": {"type": "string"},
    },
    "required": ["alvo", "intencao", "busca", "local"],
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
        except (ValueError, AttributeError):
            return Intencao(TipoIntencao.CONVERSAR, "", comando, motivo_regra="o modelo deu uma resposta inválida")
        if tipo is TipoIntencao.CLICAR_BOTAO:
            intencao = self._clique(alvo, local, comando)
        else:
            intencao = self._aplicar_regras(tipo, alvo, busca, comando)
        return replace(intencao, resposta_modelo=dados)

    @staticmethod
    def _clique(alvo, local, comando) -> Intencao:
        if not VERBO_CLICAR.match(comando):
            return Intencao(TipoIntencao.CONVERSAR, alvo, comando,
                            motivo_regra="a frase não começa com uma ordem de clicar: é pergunta ou comentário")
        if not alvo or alvo.lower() in NOMES_DO_ASSISTENTE:
            return Intencao(TipoIntencao.VER_BOTOES, ALVO_MERLIN, comando,
                            motivo_regra="pediu um clique sem dizer qual botão: vou listar os botões")
        return Intencao(TipoIntencao.CLICAR_BOTAO, alvo, comando, local)

    @staticmethod
    def _aplicar_regras(tipo, alvo, busca, comando) -> Intencao:
        sobre_merlin = alvo.lower() in NOMES_DO_ASSISTENTE  # "jarvis" também, se a personalidade for o Jarvis
        motivo = ""
        if tipo is TipoIntencao.FECHAR_PROGRAMA and VERBO_ABRIR.match(comando):
            tipo, motivo = TipoIntencao.ABRIR_PROGRAMA, "a frase começa com um verbo de abrir, não de fechar"
        if tipo is TipoIntencao.FECHAR_PROGRAMA and normalizar(alvo) in ALVOS_JANELA_DO_MERLIN:
            return Intencao(TipoIntencao.DISPENSAR, ALVO_MERLIN, comando,
                            motivo_regra="fechar esta janela, sem citar programa, é fechar a janela do assistente")
        if tipo in (TipoIntencao.DISPENSAR, TipoIntencao.ENCERRAR) and not sobre_merlin:
            return Intencao(TipoIntencao.CONVERSAR, alvo, comando,
                            motivo_regra=f"sair só vale quando o alvo é o assistente, e o alvo era '{alvo}'")
        if tipo is TipoIntencao.FECHAR_PROGRAMA and sobre_merlin:
            return Intencao(TipoIntencao.DISPENSAR, alvo, comando, motivo_regra="fechar o próprio assistente é dispensá-lo")
        if tipo is TipoIntencao.ABRIR_PROGRAMA and (sobre_merlin or not alvo):
            return Intencao(TipoIntencao.CONVERSAR, alvo, comando,
                            motivo_regra="abrir programa precisa de um programa, e não o próprio assistente")
        if tipo is TipoIntencao.ABRIR_CONFIGURACOES:
            return ClassificadorIntencao._configuracoes(alvo, comando)
        if tipo is TipoIntencao.PESQUISAR_WEB:
            return Intencao(tipo, busca or comando, comando,
                            motivo_regra="" if busca else "o modelo não deu o termo da busca: uso a frase inteira")
        return Intencao(tipo, alvo, comando, motivo_regra=motivo)

    @staticmethod
    def _configuracoes(alvo, comando) -> Intencao:
        if PERGUNTA.match(comando):
            return Intencao(TipoIntencao.CONVERSAR, alvo, comando,
                            motivo_regra="a frase é uma pergunta, não uma ordem")  # "como abro as configurações do celular?"
        outro = CONFIGURACOES_DE_OUTRO.search(comando)
        if outro and outro.group(1).lower() not in NOMES_DO_ASSISTENTE:
            dono = outro.group(1)
            if dono.lower() in DONOS_DO_SISTEMA:
                return Intencao(TipoIntencao.ABRIR_PROGRAMA, "configurações", comando,
                                motivo_regra=f"são as configurações do {dono}, não as do assistente")
            return Intencao(TipoIntencao.CONVERSAR, alvo, comando,
                            motivo_regra=f"são as configurações do {dono}, que eu não sei abrir")
        return Intencao(TipoIntencao.ABRIR_CONFIGURACOES, ALVO_MERLIN, comando)
