"""Cria pastas e arquivos nas pastas pessoais. Nunca substitui o que já existe."""
from pathlib import Path

from merlin.acoes.locais import LocalNaoPermitido, NomeInvalido, validar_nome
from merlin.nucleo.resposta import Resultado

EXTENSAO_PADRAO = ".txt"
EXTENSOES_BLOQUEADAS = {
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msi", ".scr", ".pif", ".lnk", ".reg", ".hta", ".dll", ".cpl", ".url",
}


class CriarPasta:
    def __init__(self, locais):
        self._locais = locais

    def __call__(self, intencao) -> Resultado:
        try:
            nome = validar_nome(intencao.alvo)
            pasta = self._locais.garantir_permitido(self._locais.resolver(intencao.local) / nome)
            local = self._locais.descrever(pasta.parent)
            pasta.mkdir(parents=True)
        except FileExistsError:
            return Resultado(f"a pasta {intencao.alvo} já existe", registro=f"Já existe: {intencao.alvo}")
        except (LocalNaoPermitido, NomeInvalido, OSError) as erro:
            return _falha(f"a pasta {intencao.alvo}", erro)
        return Resultado(f"criei a pasta {nome} em {local}", registro=f"Pasta criada: {pasta}")


class CriarArquivo:
    def __init__(self, locais):
        self._locais = locais

    def __call__(self, intencao) -> Resultado:
        try:
            nome = self._nome_com_extensao(validar_nome(intencao.alvo))
            if Path(nome).suffix.lower() in EXTENSOES_BLOQUEADAS:
                return Resultado(f"por segurança, não criei {nome}, porque não crio arquivos do tipo {Path(nome).suffix}",
                                 registro=f"Extensão bloqueada: {nome}")
            arquivo = self._locais.garantir_permitido(self._locais.resolver(intencao.local) / nome)
            local = self._locais.descrever(arquivo.parent)
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            with open(arquivo, "x", encoding="utf-8") as saida:  # "x" falha se o arquivo já existir
                saida.write(intencao.conteudo)
        except FileExistsError:
            return Resultado(f"o arquivo {intencao.alvo} já existe, então não mexi nele", registro=f"Já existe: {intencao.alvo}")
        except (LocalNaoPermitido, NomeInvalido, OSError) as erro:
            return _falha(f"o arquivo {intencao.alvo}", erro)
        return Resultado(f"criei o arquivo {nome} em {local}", registro=f"Arquivo criado: {arquivo}")

    @staticmethod
    def _nome_com_extensao(nome: str) -> str:
        return nome if Path(nome).suffix else nome + EXTENSAO_PADRAO


def _falha(alvo, erro) -> Resultado:
    if isinstance(erro, LocalNaoPermitido):
        fala = f"não criei {alvo}, porque só posso criar coisas dentro das suas pastas pessoais"
    elif isinstance(erro, NomeInvalido):
        fala = f"não criei {alvo}, porque o nome não é válido"
    else:
        fala = f"não consegui criar {alvo}"
    return Resultado(fala, registro=f"Falha ao criar {alvo}: {erro}")
