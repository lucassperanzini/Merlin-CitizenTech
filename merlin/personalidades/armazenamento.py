"""Assistentes criados ou ajustados no configurador: cada um é um arquivo .json em assistentes/.

Um arquivo com o id de um assistente original (merlin, jarvis, em recursos/assistentes_padrao/) é um ajuste dele:
vale no lugar do original, e apagar o arquivo restaura o padrão. Um id novo é um assistente novo.
Os originais usam este mesmo formato.
Os dados são conferidos ao salvar e ao carregar: um arquivo com problema é ignorado (com aviso no log),
para nunca impedir o assistente de abrir.
"""
import json
import logging
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

from merlin.config import PASTA_ASSISTENTES, PASTA_RAIZ
from merlin.personalidades.base import ConjuntoFrases, Personalidade, VozPropria
from merlin.voz.efeitos import EfeitoVoz

logger = logging.getLogger(__name__)

SONS = {  # rótulo mostrado -> arquivo em recursos/
    "Mágico": "ativacao.wav",
    "Digital": "ativacao_jarvis.wav",
}
VISUAIS = ("olho", "esfera")
MINIMO_RESERVAS = 4  # o gerador de frases guarda as 3 últimas e precisa de mais uma de reserva para escolher
TAMANHO_MINIMO_PALAVRA = 3  # "ana" acharia "banana": palavras de chamada curtas demais disparam por engano
COR = re.compile(r"^#[0-9a-fA-F]{6}$")


class DadosInvalidos(ValueError):
    """A mensagem é mostrada à pessoa no configurador."""


def id_para(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_") or "assistente"


def linhas(texto) -> list[str]:
    """Aceita lista ou texto com um item por linha (como vem das caixas de texto)."""
    itens = texto if isinstance(texto, list) else str(texto or "").splitlines()
    return [str(i).strip() for i in itens if str(i).strip()]


def para_dados(p: Personalidade) -> dict:
    """Uma personalidade em dados simples, prontos para o configurador e para o arquivo."""
    som = next((rotulo for rotulo, arquivo in SONS.items() if p.som_ativacao.name == arquivo), "Mágico")
    dados = {
        "id": p.id, "nome": p.nome, "descricao": p.descricao, "contexto": p.contexto, "jeito": p.jeito,
        "expressoes": list(p.expressoes),
        "frequencia_expressoes": p.frequencia_expressoes, "nao_comentar_instrucoes": p.nao_comentar_instrucoes,
        "palavras_ativacao": list(p.palavras_ativacao), "voz_padrao": p.voz_padrao,
        "visual": p.visual, "cor": p.cor, "som": som,
        "apresentacao": p.apresentacao, "dica_vocabulario": p.dica_vocabulario, "prompt_conversa": p.prompt_conversa,
        # Vozes criadas para o assistente: uma voz do Piper com efeitos (aparecem no seletor de vozes)
        "vozes_proprias": [{"rotulo": v.rotulo, "id": v.id, "efeito": {
            "modelo": v.efeito.modelo, "tom": v.efeito.tom, "lentidao": v.efeito.lentidao,
            "tremor": v.efeito.tremor, "eco": v.efeito.eco}} for v in p.vozes_proprias],
    }
    for parte in PARTES:
        c: ConjuntoFrases = getattr(p, parte)
        dados[parte] = {"prompt": c.prompt, "temas": list(c.temas), "reservas": list(c.reservas),
                        "exemplos": [e for e in c.exemplos if e], "exige_nome": c.exige_nome or "",
                        "sem_perguntas": c.sem_perguntas, "proibir_tratamentos": c.proibir_tratamentos,
                        "tamanho_maximo": c.tamanho_maximo}
    return dados


# Os conjuntos de frases de cada assistente. Um "encerramento" em arquivos antigos é ignorado.
PARTES = ("saudacao", "despedida")


def de_dados(dados: dict, base: Personalidade | None = None) -> Personalidade:
    """Monta e confere uma personalidade. base: o original do código, de onde vêm as vozes próprias."""
    nome = str(dados.get("nome", "")).strip()
    if not nome:
        raise DadosInvalidos("Dê um nome ao assistente.")
    palavras = tuple(dict.fromkeys(p.lower() for p in linhas(dados.get("palavras_ativacao"))))
    if not palavras:
        raise DadosInvalidos("Informe ao menos uma palavra de chamada.")
    curtas = [p for p in palavras if len(p) < TAMANHO_MINIMO_PALAVRA]
    if curtas:
        raise DadosInvalidos(f"Palavras de chamada muito curtas disparam por engano: {', '.join(curtas)}.")
    visual = dados.get("visual", "olho")
    if visual not in VISUAIS:
        raise DadosInvalidos("Escolha a aparência: olho ou esfera.")
    cor = str(dados.get("cor") or "").strip()
    if cor and not COR.match(cor):
        raise DadosInvalidos("A cor precisa estar no formato #RRGGBB.")
    som = SONS.get(dados.get("som"), SONS["Mágico"])
    # Sem pontuação solta no fim ("mano," vira "mano"): ela atrapalha a IA a encaixar a expressão na frase
    expressoes = tuple(dict.fromkeys(e.rstrip(",;. ") for e in linhas(dados.get("expressoes"))
                                     if "{" not in e and "}" not in e and e.rstrip(",;. ")))
    try:
        frequencia = float(dados.get("frequencia_expressoes", 0.5))
    except (TypeError, ValueError) as erro:
        raise DadosInvalidos("A frequência das expressões precisa ser um número de 0 a 1.") from erro
    if not 0 <= frequencia <= 1:
        raise DadosInvalidos("A frequência das expressões precisa ser de 0 a 1.")
    conjuntos = {parte: _conjunto(dados.get(parte) or {}, parte, expressoes, frequencia)
                 for parte in PARTES}
    if not str(dados.get("prompt_conversa", "")).strip():
        raise DadosInvalidos("Descreva como o assistente conversa.")
    return Personalidade(
        id=str(dados.get("id") or id_para(nome)),
        nome=nome,
        palavras_ativacao=palavras,
        voz_padrao=str(dados.get("voz_padrao") or (base.voz_padrao if base else "pt_BR-faber-medium")),
        visual=visual,
        som_ativacao=PASTA_RAIZ / "recursos" / som,
        apresentacao=str(dados.get("apresentacao") or f"{nome} às suas ordens.").strip(),
        dica_vocabulario=str(dados.get("dica_vocabulario") or f"{nome}, abra o navegador. {nome}, pesquise na internet."),
        prompt_conversa=str(dados["prompt_conversa"]).strip(),
        vozes_proprias=_vozes_proprias(dados.get("vozes_proprias")) or (base.vozes_proprias if base else ()),
        cor=cor,
        descricao=str(dados.get("descricao", "")).strip(),
        contexto=str(dados.get("contexto", "")).strip(),
        jeito=str(dados.get("jeito", "")).strip(),
        expressoes=expressoes,
        frequencia_expressoes=frequencia,
        nao_comentar_instrucoes=bool(dados.get("nao_comentar_instrucoes", True)),
        **conjuntos,
    )


NOMES_PARTES = {"saudacao": "saudações", "despedida": "despedidas"}


def _vozes_proprias(itens) -> tuple[VozPropria, ...]:
    try:
        return tuple(VozPropria(str(v["rotulo"]), str(v["id"]), EfeitoVoz(
            modelo=str(v["efeito"]["modelo"]), tom=float(v["efeito"]["tom"]), lentidao=float(v["efeito"]["lentidao"]),
            tremor=float(v["efeito"]["tremor"]), eco=float(v["efeito"]["eco"]))) for v in itens or ())
    except (KeyError, TypeError, ValueError) as erro:
        raise DadosInvalidos(f"Uma voz própria está incompleta ({erro}).") from erro


def ajustar_frase(frase: str) -> str:
    """Corrige o óbvio em vez de recusar: aspas em volta e falta de pontuação no fim."""
    frase = " ".join(frase.split()).strip("\"'“”‘’ ")
    return frase if not frase or frase[-1] in ".?!" else frase.rstrip(",;:") + "."


def _conjunto(dados: dict, parte: str, expressoes: tuple = (), frequencia: float = 0.5) -> ConjuntoFrases:
    reservas = tuple(dict.fromkeys(ajustar_frase(f) for f in linhas(dados.get("reservas"))))
    if len(reservas) < MINIMO_RESERVAS:
        raise DadosInvalidos(f"Escreva ao menos {MINIMO_RESERVAS} {NOMES_PARTES[parte]} prontas (uma por linha).")
    temas = tuple(linhas(dados.get("temas"))) or ("o dia",)
    prompt = str(dados.get("prompt", "")).strip()
    try:
        prompt.format(tema="x", evitar="x", exemplo="x")  # as chaves { } do texto precisam ser só estas três
    except (KeyError, IndexError, ValueError) as erro:
        raise DadosInvalidos(f"O texto avançado das {NOMES_PARTES[parte]} tem chaves {{ }} inválidas ({erro}). "
                             "Use só {tema}, {exemplo} e {evitar}.") from erro
    if not prompt:
        raise DadosInvalidos(f"Falta o texto avançado das {NOMES_PARTES[parte]}.")
    exemplos = tuple(linhas(dados.get("exemplos"))) or ("",)
    return ConjuntoFrases(prompt, temas, reservas, exemplos,
                          exige_nome=str(dados.get("exige_nome") or "").strip().lower() or None,
                          sem_perguntas=bool(dados.get("sem_perguntas", parte != "saudacao")),
                          proibir_tratamentos=bool(dados.get("proibir_tratamentos", False)),
                          tamanho_maximo=int(dados.get("tamanho_maximo", 170 if parte == "saudacao" else 120)),
                          expressoes=expressoes, frequencia_expressoes=frequencia)


def carregar(pasta: Path = PASTA_ASSISTENTES, embutidas: dict | None = None) -> list[Personalidade]:
    """Os assistentes da pasta. Um arquivo com problema é ignorado, para o assistente sempre abrir."""
    encontrados = []
    for arquivo in sorted(pasta.glob("*.json")) if pasta.is_dir() else []:
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            dados["id"] = arquivo.stem  # o nome do arquivo manda: evita dois arquivos com o mesmo id
            encontrados.append(de_dados(dados, (embutidas or {}).get(arquivo.stem)))
        except (OSError, ValueError, TypeError, KeyError) as erro:
            logger.warning("[ASSISTENTES] Ignorei %s: %s", arquivo.name, erro)
    return encontrados


def salvar(p: Personalidade, pasta: Path = PASTA_ASSISTENTES) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{p.id}.json"
    arquivo.write_text(json.dumps(para_dados(p), ensure_ascii=False, indent=2), encoding="utf-8")
    return arquivo


def apagar(identificador: str, pasta: Path = PASTA_ASSISTENTES) -> None:
    (pasta / f"{identificador}.json").unlink(missing_ok=True)


def com_id(p: Personalidade, identificador: str) -> Personalidade:
    return replace(p, id=identificador)
