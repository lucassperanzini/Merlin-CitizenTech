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
    encerramento: ConjuntoFrases
    vozes_proprias: tuple[VozPropria, ...] = ()
