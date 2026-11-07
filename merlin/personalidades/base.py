"""O formato de uma personalidade: o que cada arquivo desta pasta precisa preencher."""
from dataclasses import dataclass
from pathlib import Path

from merlin.voz.efeitos import EfeitoVoz


@dataclass(frozen=True)
class ConjuntoFrases:
    """O que a IA precisa para criar uma fala curta (saudação, despedida), e as regras para aceitá-la."""

    prompt: str  # recebe {tema}, {evitar} e {exemplo}
    temas: tuple[str, ...]
    reservas: tuple[str, ...]  # usadas quando a IA falha; precisam ser mais que as frases recentes guardadas
    exemplos: tuple[str, ...] = ("",)
    exige_nome: str | None = None  # a frase precisa conter este nome
    sem_perguntas: bool = False
    proibir_tratamentos: bool = False  # o Merlin não chama ninguém de "senhor"; o Jarvis chama
    tamanho_maximo: int = 170
    expressoes: tuple[str, ...] = ()  # gírias e bordões do assistente: duas são oferecidas em parte das frases
    frequencia_expressoes: float = 0.5  # em que fração das frases as expressões são oferecidas (0 a 1)


@dataclass(frozen=True)
class VozPropria:
    """Uma voz criada para a personalidade, com efeitos sobre uma voz do Piper. Aparece no seletor de vozes."""

    rotulo: str  # nome mostrado nas configurações
    id: str
    efeito: EfeitoVoz


@dataclass(frozen=True)
class Personalidade:
    id: str
    nome: str
    palavras_ativacao: tuple[str, ...]  # inclui as variações que o Whisper costuma ouvir
    voz_padrao: str  # id de uma voz do Piper (config.VOZES_PIPER) ou de uma das vozes_proprias
    visual: str  # "olho" ou "esfera"
    som_ativacao: Path
    apresentacao: str  # dita ao trocar para esta personalidade
    dica_vocabulario: str  # ajuda o Whisper a reconhecer o nome
    prompt_conversa: str
    saudacao: ConjuntoFrases
    despedida: ConjuntoFrases
    vozes_proprias: tuple[VozPropria, ...] = ()
    cor: str = ""  # cor de destaque na janela (ex.: "#d9ac5a"); vazio = a cor padrão do visual
    descricao: str = ""  # como a pessoa descreveu o assistente no configurador (antes de existir o contexto)
    # Quem ele é: história, profissão, relação com a pessoa. Pano de fundo da conversa, sem ser recitado.
    # O jeito de falar fica em prompt_conversa ("Como ele fala", no configurador).
    contexto: str = ""
    jeito: str = ""  # como ele é e trata a pessoa: base das instruções montadas pelo configurador
    expressoes: tuple[str, ...] = ()  # gírias e bordões que ele usa (sem comentar que usa)
    frequencia_expressoes: float = 0.5  # em que fração das respostas as expressões são oferecidas (0 a 1)
    nao_comentar_instrucoes: bool = True  # não recitar as instruções nem descrever o próprio jeito de falar
