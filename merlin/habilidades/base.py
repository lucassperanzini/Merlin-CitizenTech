"""O formato de uma habilidade: o que cada arquivo desta pasta precisa preencher.

Uma habilidade junta, num lugar só, tudo o que o assistente precisa para saber fazer algo:
- o nome e a descrição que a IA lê para reconhecer o pedido;
- exemplos de frases (e de frases parecidas que NÃO são esse pedido);
- regras fixas que corrigem a IA quando ela erra de um jeito previsível;
- como criar a ação que executa o pedido.
"""
from dataclasses import dataclass, field
from typing import Callable

ALVO_ASSISTENTE = "merlin"  # o prompt pede este alvo quando a frase é dirigida ao próprio assistente


@dataclass(frozen=True)
class Grupo:
    """Uma família de habilidades. Na classificação em duas etapas, a IA escolhe primeiro o grupo."""

    nome: str
    descricao: str
    ordem: int = 50


@dataclass(frozen=True)
class Campo:
    """Um dado a mais que a IA preenche só para esta habilidade (ex.: "busca" na pesquisa)."""

    nome: str
    descricao: str


@dataclass(frozen=True)
class Exemplo:
    """Uma frase e o que a IA deve responder. Com outra intenção, é um contraexemplo: parece, mas não é."""

    frase: str
    alvo: str
    intencao: str | None = None  # None = a própria habilidade
    campos: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Leitura:
    """O que a IA respondeu, já organizado, para as regras conferirem."""

    intencao: str
    alvo: str
    campos: dict[str, str]
    comando: str  # a frase da pessoa, sem o nome do assistente


@dataclass(frozen=True)
class Correcao:
    """Devolvida por uma regra que muda a decisão da IA. O motivo aparece na janela de raciocínio."""

    intencao: str
    motivo: str = ""
    alvo: str | None = None  # None = mantém o alvo
    campos: dict[str, str] = field(default_factory=dict)


@dataclass
class Recursos:
    """O que as ações podem usar. Montado uma vez no main.py e entregue a cada habilidade."""

    estado: object
    sessao: object
    canal: object
    cliente_ia: object
    memoria: object
    preferencias: object
    raciocinio: object
    compartilhados: dict = field(default_factory=dict)  # objetos usados por mais de uma ação

    def compartilhado(self, nome: str, criar: Callable[[], object]) -> object:
        """Cria o objeto na primeira vez e devolve o mesmo nas próximas."""
        if nome not in self.compartilhados:
            self.compartilhados[nome] = criar()
        return self.compartilhados[nome]


@dataclass(frozen=True)
class Habilidade:
    nome: str  # o identificador que a IA escreve, ex.: "abrir_programa"
    grupo: Grupo
    descricao: str  # uma ou duas frases para a IA: quando a frase é este pedido, e o que vai no alvo
    criar_acao: Callable[[Recursos], Callable]  # recebe os recursos e devolve a ação (Intencao -> Resultado)
    exemplos: tuple[Exemplo, ...] = ()
    campos: tuple[Campo, ...] = ()
    regra: Callable[[Leitura], Correcao | None] | None = None
    mexe_no_computador: bool = False  # True: numa frase com várias tarefas, justifica separar as partes
    ordem: int = 50  # posição no prompt; a conversa (o caso geral) fica por último
