"""Registro do que o assistente entendeu e decidiu em cada pedido, para mostrar na janela de raciocínio.
Na memória ficam os passos mais recentes; com um gravador, cada passo também vai para o arquivo do dia."""
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

MAX_PASSOS = 500


class TipoPasso(str, Enum):
    OUVI = "ouvi"  # começa um pedido novo
    CONFIRMACAO = "confirmacao"
    TAREFAS = "tarefas"
    INTENCAO = "intencao"
    REGRA = "regra"  # uma regra do código mudou o que o modelo decidiu
    JANELA = "janela"
    BOTOES = "botoes"
    ESCOLHA = "escolha"
    ACAO = "acao"
    FALA = "fala"
    ERRO = "erro"


@dataclass(frozen=True)
class Passo:
    numero: int
    hora: str
    tipo: TipoPasso
    texto: str
    detalhes: tuple[tuple[str, str], ...] = ()

    def como_dict(self) -> dict:
        return {"numero": self.numero, "hora": self.hora, "tipo": self.tipo.value, "texto": self.texto,
                "detalhes": [list(d) for d in self.detalhes]}


class Raciocinio:
    def __init__(self, limite: int = MAX_PASSOS, gravador=None):
        self._passos = deque(maxlen=limite)
        self._contador = 0
        self._trava = threading.Lock()
        self._gravador = gravador  # opcional: guarda também em arquivo

    def registrar(self, tipo: TipoPasso, texto: str, **detalhes) -> None:
        """Os detalhes viram pares "nome: valor"; valores vazios ficam de fora."""
        pares = tuple((nome.replace("_", " "), formatar(valor)) for nome, valor in detalhes.items()
                      if valor not in (None, "", [], ()))
        with self._trava:  # a gravação também fica dentro: o arquivo sai na mesma ordem da tela
            self._contador += 1
            passo = Passo(self._contador, time.strftime("%H:%M:%S"), tipo, texto, pares)
            self._passos.append(passo)
            if self._gravador:
                self._gravador.gravar(passo)

    def desde(self, numero: int) -> list[Passo]:
        """Passos registrados depois do número dado (0 = todos os que ainda estão guardados)."""
        with self._trava:
            return [p for p in self._passos if p.numero > numero]

    def limpar(self) -> None:
        with self._trava:
            self._passos.clear()


def formatar(valor) -> str:
    if isinstance(valor, float):  # durações
        return f"{valor:.2f} s".replace(".", ",")
    if isinstance(valor, (list, tuple)):
        return ", ".join(str(v) for v in valor)
    if isinstance(valor, Enum):
        return str(valor.value)
    return str(valor)
