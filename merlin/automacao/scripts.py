"""Guarda os scripts escritos pela IA: o .py e, ao lado, um .json com a explicação, os avisos e a pasta.

Um script só roda quando a pessoa clica em Executar, e não fica isolado: a conferência dele não substitui ler o código.
"""
import ast
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from merlin.automacao.analise_script import analisar
from merlin.config import PASTA_PYTHON_SCRIPTS, PASTA_SCRIPTS
from merlin.texto import normalizar

CABECALHO = "# Escrito por IA e não testado. Confira antes de rodar.\n\n"
AVISO_FIXO = "A IA pode errar. Este script ainda não foi testado."
TAMANHO_MAXIMO_DO_NOME = 40
PYTHON_DOS_SCRIPTS = PASTA_PYTHON_SCRIPTS / "Scripts" / "python.exe"
AVISO_ANTIGO_DE_BIBLIOTECA = "Precisa instalar antes"  # hoje a tela calcula o que falta na hora
TEMPO_LIMITE = 300  # segundos: um script travado não pode prender a aba para sempre
MAX_CARACTERES_DA_SAIDA = 20000
MAX_NOME_APROVADO = 40
MIN_NOME_APROVADO = 3  # em letras e números: nomes curtos demais apareceriam dentro de qualquer frase
MAX_SEGUNDOS_UMA_VEZ = 86400
MAX_HISTORICO = 10 # execuções agendadas guardadas por script
MAX_RESUMO_NO_HISTORICO = 1000
_TRAVA_DOS_DADOS = threading.RLock()
PALAVRAS_DE_LIGACAO = ("o", "a", "os", "as", "de", "do", "da", "script", "automacao")
_ID_VALIDO = re.compile(r"^[a-z0-9_]+$")
_CONSTANTE = "PASTA"


class ScriptInvalido(Exception):
    """A mensagem pode ser mostrada à pessoa."""


def _linhas_da_pasta(codigo: str) -> tuple[int, int] | None:
    """Primeira e última linha (a partir de 1) da única constante PASTA do script, se ela ocupar as linhas sozinha."""
    try:
        corpo = ast.parse(codigo).body
    except (SyntaxError, ValueError):
        return None
    achadas = [n for n in corpo if isinstance(n, ast.Assign) and len(n.targets) == 1
               and isinstance(n.targets[0], ast.Name) and n.targets[0].id == _CONSTANTE]
    if len(achadas) != 1:
        return None
    no = achadas[0]
    if any(o is not no and o.lineno <= no.end_lineno and o.end_lineno >= no.lineno for o in corpo):
        return None
    return no.lineno, no.end_lineno


def trocar_pasta(codigo: str, caminho: str) -> str | None:
    """O código com a pasta escolhida no lugar da inventada pela IA, ou None se não der para trocar com segurança."""
    linhas_da_pasta = _linhas_da_pasta(codigo)
    if linhas_da_pasta is None:
        return None
    inicio, fim = linhas_da_pasta
    linhas = codigo.split("\n")
    linhas[inicio - 1:fim] = [f"{_CONSTANTE} = {caminho!r}"]
    return "\n".join(linhas)


def _conferir(codigo: str):
    """A mesma conferência dos scripts gerados vale para o código colado e na hora de executar."""
    analise = analisar(codigo)
    if not analise.valido:
        raise ScriptInvalido("O código tem um erro de escrita e não pode ser usado.")
    if analise.bloqueios:
        raise ScriptInvalido(f"Recusado: este código {' e '.join(analise.bloqueios)}.")
    return analise


def _impressao(codigo: str) -> str:
    """Identifica o código sem contar a pasta: testar numa pasta e depois trocar de pasta não invalida a aprovação."""
    return hashlib.sha256((trocar_pasta(codigo, "") or codigo).encode("utf-8")).hexdigest()


def _chave(nome: str) -> str:
    return "".join(normalizar(p) for p in nome.split() if normalizar(p) not in PALAVRAS_DE_LIGACAO)


def _hora_valida(hora) -> str:
    achado = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", str(hora or "").strip())
    if not achado:
        raise ScriptInvalido("Escolha um horário válido.")
    return achado.group(0)


def _dia_ja_passado(hora: str, agora: datetime | None) -> str:
    """Se o horário de hoje já passou, a primeira execução fica para amanhã, e não para este instante."""
    agora = agora or datetime.now()
    return agora.date().isoformat() if agora.strftime("%H:%M") >= hora else ""


def _final(texto: str | bytes | None) -> str:
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8", "replace")
    texto = texto or ""
    return texto[-MAX_CARACTERES_DA_SAIDA:]


class ArmazemDeScripts:
    def __init__(self, pasta=PASTA_SCRIPTS, tempo_limite=TEMPO_LIMITE):
        self._pasta = Path(pasta)
        self._tempo_limite = tempo_limite

    def _caminho(self, id_script: str) -> Path:
        if not isinstance(id_script, str) or not _ID_VALIDO.match(id_script):
            raise ScriptInvalido("Esse script não existe.")
        caminho = self._pasta / f"{id_script}.py"
        if not caminho.is_file():
            raise ScriptInvalido("Esse script não existe.")
        return caminho

    def _novo_id(self, pedido: str) -> str:
        palavras = "_".join(normalizar(palavra) for palavra in pedido.split()).lower()
        base = re.sub(r"[^a-z0-9]+", "_", palavras).strip("_")[:TAMANHO_MAXIMO_DO_NOME].strip("_") or "script"
        id_script, numero = base, 2
        while (self._pasta / f"{id_script}.py").exists():
            id_script, numero = f"{base}_{numero}", numero + 1
        return id_script

    def guardar(self, pedido: str, codigo: str, explicacao: str, avisos, hora_sugerida: str = "") -> str:
        self._pasta.mkdir(parents=True, exist_ok=True)
        id_script = self._novo_id(pedido)
        with open(self._pasta / f"{id_script}.py", "x", encoding="utf-8") as arquivo:  # x: nunca substitui
            arquivo.write(CABECALHO + codigo)
        self._gravar_dados(id_script, {"pedido": pedido, "explicacao": explicacao, "avisos": list(avisos), "pasta": "",
                                       "criado": time.time(), "hora_sugerida": hora_sugerida})
        return id_script

    def _gravar_dados(self, id_script: str, dados: dict) -> None:
        """Grava num arquivo à parte e troca de uma vez: quem estiver lendo nunca vê um .json pela metade."""
        destino = self._pasta / f"{id_script}.json"
        temporario = destino.with_suffix(f".{threading.get_ident()}.tmp")
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporario, destino)

    def _atualizar(self, caminho: Path, tirar=(), **campos) -> None:
        """A aba e o agendador mexem nos mesmos dados: um não pode apagar o que o outro acabou de gravar."""
        with _TRAVA_DOS_DADOS:
            dados = {**self._ler_dados(caminho), **campos}
            for campo in tirar:
                dados.pop(campo, None)
            self._gravar_dados(caminho.stem, dados)

    def _ler_dados(self, caminho: Path) -> dict:
        try:
            dados = json.loads(caminho.with_suffix(".json").read_text(encoding="utf-8"))
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):  # scripts salvos antes desta tela não têm os dados
            return {}

    @staticmethod
    def _nome_aprovado(codigo: str, dados: dict) -> str:
        """O nome da aprovação, ou "" se não há aprovação ou se o código mudou depois dela."""
        aprovacao = dados.get("aprovacao")
        if isinstance(aprovacao, dict) and aprovacao.get("impressao") == _impressao(codigo):
            return str(aprovacao.get("nome") or "")
        return ""

    def _descrever(self, caminho: Path) -> dict:
        codigo = caminho.read_text(encoding="utf-8")
        dados = self._ler_dados(caminho)
        criado = dados.get("criado") or caminho.stat().st_mtime
        return {"id": caminho.stem, "pedido": dados.get("pedido") or caminho.stem.replace("_", " "),
                "explicacao": dados.get("explicacao") or "", "externos": list(analisar(codigo).externos),
                "avisos": [a for a in dados.get("avisos") or [] if not a.startswith(AVISO_ANTIGO_DE_BIBLIOTECA)],
                "pasta": dados.get("pasta") or "", "codigo": codigo, "aceita_pasta": _linhas_da_pasta(codigo) is not None,
                "aprovado": self._nome_aprovado(codigo, dados), "agenda": dados.get("agenda"), "unica": dados.get("unica"),
                "testado": dados.get("testado") == _impressao(codigo),
                "hora_sugerida": dados.get("hora_sugerida") or "", "historico": dados.get("historico") or [],
                "ordem": criado, "quando": time.strftime("%d/%m às %H:%M", time.localtime(criado))}

    def listar(self) -> list[dict]:
        """Os mais novos primeiro."""
        if not self._pasta.is_dir():
            return []
        return sorted((self._descrever(c) for c in self._pasta.glob("*.py")), key=lambda s: s["ordem"], reverse=True)

    def codigo(self, id_script: str) -> str:
        return self._caminho(id_script).read_text(encoding="utf-8")

    def definir_pasta(self, id_script: str, pasta: str) -> None:
        caminho = self._caminho(id_script)
        destino = Path(str(pasta or ""))
        if not destino.is_absolute() or not destino.is_dir():
            raise ScriptInvalido("Essa pasta não existe.")
        if self._ler_dados(caminho).get("agenda"):
            raise ScriptInvalido("Remova o agendamento antes de trocar a pasta.")
        novo = trocar_pasta(caminho.read_text(encoding="utf-8"), str(destino))
        if novo is None:
            raise ScriptInvalido("Não consegui colocar a pasta neste script.")
        caminho.write_text(novo, encoding="utf-8")
        self._atualizar(caminho, pasta=str(destino))

    def salvar_codigo(self, id_script: str, codigo: str) -> None:
        """Troca o código por um corrigido. A pasta já escolhida continua valendo."""
        caminho = self._caminho(id_script)
        if not isinstance(codigo, str) or not codigo.strip():
            raise ScriptInvalido("O código está vazio.")
        analise = _conferir(codigo)
        dados = self._ler_dados(caminho)
        novo = trocar_pasta(codigo, dados["pasta"]) if dados.get("pasta") else None
        if novo is None:  # sem pasta escolhida, ou o código novo não tem mais onde colocá-la
            novo, dados["pasta"] = codigo, ""
        caminho.write_text(novo, encoding="utf-8")
        self._atualizar(caminho, pasta=dados["pasta"] if "pasta" in dados else "", avisos=[AVISO_FIXO, *analise.avisos])

    def executar(self, id_script: str) -> dict:
        caminho = self._caminho(id_script)
        codigo = caminho.read_text(encoding="utf-8")
        _conferir(codigo)  # o arquivo pode ter sido criado antes da conferência ou mudado à mão
        pasta = self._ler_dados(caminho).get("pasta") or ""
        if _linhas_da_pasta(codigo) is not None and not pasta:
            raise ScriptInvalido("Escolha a pasta antes de executar.")
        if pasta and not Path(pasta).is_dir():
            raise ScriptInvalido("A pasta escolhida não existe mais.")
        # O que o script gravar sem caminho fica na pasta escolhida, e não na do Merlin
        trabalho = Path(pasta) if pasta else self._pasta / "saidas"
        trabalho.mkdir(parents=True, exist_ok=True)
        if not Path(PYTHON_DOS_SCRIPTS).is_file():
            raise ScriptInvalido("O Python dos scripts ainda não está pronto. Clique em Preparar, na aba Automações.")
        inicio = time.monotonic()
        try:
            feito = subprocess.run([str(PYTHON_DOS_SCRIPTS), "-X", "utf8", str(caminho)], cwd=trabalho, capture_output=True,
                                   stdin=subprocess.DEVNULL, timeout=self._tempo_limite, encoding="utf-8", errors="replace",
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as erro:
            return {"ok": False, "tempo_esgotado": True, "saida": _final(erro.stdout), "erros": _final(erro.stderr),
                    "segundos": round(time.monotonic() - inicio)}
        if feito.returncode == 0:
            self._atualizar(caminho, testado=_impressao(codigo))
        return {"ok": feito.returncode == 0, "tempo_esgotado": False, "saida": _final(feito.stdout),
                "erros": _final(feito.stderr), "segundos": round(time.monotonic() - inicio)}

    def aprovar(self, id_script: str, nome: str) -> None:
        caminho = self._caminho(id_script)
        nome = " ".join(str(nome or "").split())
        chave = _chave(nome)
        if len(nome) > MAX_NOME_APROVADO or len(chave) < MIN_NOME_APROVADO:
            raise ScriptInvalido(f"Dê um nome com pelo menos {MIN_NOME_APROVADO} letras e até {MAX_NOME_APROVADO} caracteres.")
        codigo = caminho.read_text(encoding="utf-8")
        _conferir(codigo)
        dados = self._ler_dados(caminho)
        if dados.get("testado") != _impressao(codigo):
            raise ScriptInvalido("Execute este código sem erro antes de aprovar.")
        if any(s["id"] != id_script and s["aprovado"] and _chave(s["aprovado"]) == chave for s in self.listar()):
            raise ScriptInvalido("Já existe um script aprovado com esse nome.")
        self._atualizar(caminho, aprovacao={"nome": nome, "impressao": _impressao(codigo)})

    def desaprovar(self, id_script: str) -> None:
        self._atualizar(self._caminho(id_script), tirar=("aprovacao", "agenda"))

    def agendar(self, id_script: str, hora: str, agora: datetime | None = None) -> None:
        caminho = self._caminho(id_script)
        hora = _hora_valida(hora)
        codigo = caminho.read_text(encoding="utf-8")
        dados = self._ler_dados(caminho)
        if not self._nome_aprovado(codigo, dados):
            raise ScriptInvalido("Aprove o script antes de agendar.")
        pasta = dados.get("pasta") or ""
        if _linhas_da_pasta(codigo) is not None and not pasta:
            raise ScriptInvalido("Escolha a pasta antes de agendar.")
        self._atualizar(caminho, agenda={"hora": hora, "ativa": True, "pasta": pasta, "ultimo_dia": _dia_ja_passado(hora, agora)})

    def agendar_unico(self, id_script: str, segundos: int, agora: float | None = None) -> None:
        """Roda uma vez, daqui a tantos segundos. Fica gravado para o agendador, que roda em outra parte do programa."""
        caminho = self._caminho(id_script)
        if not isinstance(segundos, int) or not 1 <= segundos <= MAX_SEGUNDOS_UMA_VEZ:
            raise ScriptInvalido("Escolha um tempo entre 1 segundo e 24 horas.")
        codigo = caminho.read_text(encoding="utf-8")
        dados = self._ler_dados(caminho)
        if not self._nome_aprovado(codigo, dados):
            raise ScriptInvalido("Aprove o script antes de agendar.")
        pasta = dados.get("pasta") or ""
        if _linhas_da_pasta(codigo) is not None and not pasta:
            raise ScriptInvalido("Escolha a pasta antes de agendar.")
        self._atualizar(caminho, unica={"em": (time.time() if agora is None else agora) + segundos, "pasta": pasta})

    def cancelar_unico(self, id_script: str) -> None:
        self._atualizar(self._caminho(id_script), tirar=("unica",))

    def unicos_vencidos(self, agora: float) -> list[tuple[str, dict]]:
        """Olha só os .json: é chamado a cada segundo e não precisa ler o código de cada script."""
        if not self._pasta.is_dir():
            return []
        vencidos = []
        for arquivo in self._pasta.glob("*.json"):
            unica = self._ler_dados(arquivo).get("unica")
            if isinstance(unica, dict) and unica.get("em", agora + 1) <= agora and arquivo.with_suffix(".py").is_file():
                vencidos.append((arquivo.stem, unica))
        return vencidos

    def descrever(self, id_script: str) -> dict:
        return self._descrever(self._caminho(id_script))

    def pausar_agenda(self, id_script: str, pausar: bool, agora: datetime | None = None) -> None:
        caminho = self._caminho(id_script)
        agenda = self._ler_dados(caminho).get("agenda")
        if not agenda:
            raise ScriptInvalido("Este script não tem agendamento.")
        self._atualizar(caminho, agenda={**agenda, "ativa": not pausar, "ultimo_dia": _dia_ja_passado(agenda["hora"], agora)})

    def remover_agenda(self, id_script: str) -> None:
        self._atualizar(self._caminho(id_script), tirar=("agenda",))

    def marcar_dia_da_agenda(self, id_script: str, dia: str) -> None:
        """Antes de rodar: nem uma falha no meio faz o mesmo horário disparar duas vezes."""
        caminho = self._caminho(id_script)
        agenda = self._ler_dados(caminho).get("agenda")
        if agenda:
            self._atualizar(caminho, agenda={**agenda, "ultimo_dia": dia})

    def registrar_execucao(self, id_script: str, quando: str, ok: bool, resumo: str) -> None:
        caminho = self._caminho(id_script)
        entrada = {"quando": quando, "ok": ok, "resumo": resumo[-MAX_RESUMO_NO_HISTORICO:]}
        self._atualizar(caminho, historico=[entrada, *self._ler_dados(caminho).get("historico", [])][:MAX_HISTORICO])

    def encontrar_aprovado(self, alvo: str, comando: str) -> dict | None:
        """Primeiro o nome exato que a IA entendeu; senão, o nome mais longo que aparece na frase."""
        aprovados = [s for s in self.listar() if s["aprovado"]]
        chave = _chave(alvo)
        exato = next((s for s in aprovados if chave and _chave(s["aprovado"]) == chave), None)
        if exato:
            return exato
        frase = normalizar(comando)
        presentes = [s for s in aprovados if _chave(s["aprovado"]) in frase]
        return max(presentes, key=lambda s: len(_chave(s["aprovado"])), default=None)

    def executar_aprovado(self, id_script: str, pasta_confirmada: str) -> dict:
        """Só roda se o código ainda for o aprovado e a pasta for a mesma que a pessoa confirmou."""
        caminho = self._caminho(id_script)
        dados = self._ler_dados(caminho)
        if not self._nome_aprovado(caminho.read_text(encoding="utf-8"), dados):
            raise ScriptInvalido("Este script mudou e precisa ser aprovado de novo.")
        if (dados.get("pasta") or "") != pasta_confirmada:
            raise ScriptInvalido("A pasta mudou depois da confirmação. Peça de novo.")
        return self.executar(id_script)

    def apagar(self, id_script: str) -> None:
        caminho = self._caminho(id_script)
        caminho.unlink()
        caminho.with_suffix(".json").unlink(missing_ok=True)
