"""Grava o raciocínio em arquivos de texto, um por dia (registros/2026-11-05.txt), e apaga os mais antigos.
Os arquivos ficam só neste computador: têm o que a pessoa falou e o que o assistente viu na tela."""
import logging
import time
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

LARGURA_ROTULO = 10
ROTULOS = {
    "ouvi": "OUVI", "confirmacao": "RESPOSTA", "tarefas": "TAREFAS", "intencao": "INTENÇÃO", "regra": "REGRA",
    "janela": "JANELA", "botoes": "BOTÕES", "escolha": "ESCOLHA", "acao": "FIZ", "fala": "FALEI", "erro": "ERRO",
}


def formatar_passo(passo) -> str:
    """Um passo em texto: hora, rótulo e texto na primeira linha; os detalhes alinhados embaixo."""
    rotulo = ROTULOS.get(passo.tipo.value, passo.tipo.value.upper())
    linhas = [f"[{passo.hora}] {rotulo:<{LARGURA_ROTULO}} {passo.texto}"]
    recuo = " " * (len(passo.hora) + 3 + LARGURA_ROTULO + 1)
    linhas += [f"{recuo}{nome}: {valor}" for nome, valor in passo.detalhes]
    separador = "\n" if passo.tipo.value == "ouvi" else ""  # cada pedido começa com uma linha em branco
    return separador + "\n".join(linhas) + "\n"


class GravadorRaciocinio:
    def __init__(self, pasta: Path, dias_guardados: int, hoje=date.today):
        self._pasta = pasta
        self._dias = dias_guardados
        self._hoje = hoje

    @property
    def pasta(self) -> Path:
        return self._pasta

    def gravar(self, passo) -> None:
        """Nunca derruba o assistente: se o disco falhar, só avisa no log."""
        try:
            self._pasta.mkdir(parents=True, exist_ok=True)
            with open(self.arquivo_de(self._hoje()), "a", encoding="utf-8") as arquivo:
                arquivo.write(formatar_passo(passo))
        except OSError as erro:
            logger.warning("[RACIOCÍNIO] Não consegui gravar o registro: %s", erro)

    def arquivo_de(self, dia: date) -> Path:
        return self._pasta / f"{dia.isoformat()}.txt"

    def apagar_antigos(self) -> int:
        """Apaga os registros de mais de dias_guardados dias. Só mexe em arquivos com nome de data."""
        limite = self._hoje() - timedelta(days=self._dias)
        apagados = 0
        for arquivo in self._pasta.glob("????-??-??.txt"):
            try:
                if date.fromisoformat(arquivo.stem) < limite:
                    arquivo.unlink()
                    apagados += 1
            except (ValueError, OSError):
                continue  # nome que parece data mas não é, ou arquivo em uso
        return apagados
