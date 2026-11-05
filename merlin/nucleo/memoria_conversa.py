"""Memória de curto prazo: as últimas trocas da conversa atual. Some quando o Merlin volta à espera."""
import threading
from dataclasses import dataclass

from merlin.config import MAX_TROCAS_LEMBRADAS

TAMANHO_MAXIMO_TEXTO = 500  # respostas longas não podem inchar o que vai para a IA a cada pergunta


@dataclass(frozen=True)
class Troca:
    pessoa: str
    merlin: str


class MemoriaConversa:
    def __init__(self, limite: int = MAX_TROCAS_LEMBRADAS):
        self._limite = limite
        self._trocas: list[Troca] = []
        self._trava = threading.Lock()  # a janela e a fila de comandos usam a memória em threads diferentes

    def registrar(self, pessoa: str, merlin: str) -> None:
        if not pessoa.strip() or not merlin.strip():
            return
        with self._trava:
            self._trocas.append(Troca(pessoa[:TAMANHO_MAXIMO_TEXTO], merlin[:TAMANHO_MAXIMO_TEXTO]))
            # Cuidado: lista[-0:] seria a lista inteira, e um limite 0 precisa significar "não lembrar nada"
            self._trocas = self._trocas[-self._limite:] if self._limite > 0 else []

    def limpar(self) -> None:
        with self._trava:
            self._trocas.clear()

    def como_mensagens(self) -> list[dict]:
        """No formato de conversa que a IA entende, da troca mais antiga para a mais nova."""
        with self._trava:
            trocas = list(self._trocas)
        mensagens = []
        for troca in trocas:
            mensagens.append({"role": "user", "content": troca.pessoa})
            mensagens.append({"role": "assistant", "content": troca.merlin})
        return mensagens
