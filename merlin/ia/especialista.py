"""O modelo especialista da Defesa Civil (pacote defesacivil_llm): RAG + LoRA sobre os protocolos de incêndio.

Responde só com base nos documentos da base. A carga leva alguns segundos e ocupa ~8 GB da placa de vídeo, então
ela é feita em segundo plano: o Merlin abre e ouve normalmente enquanto o modelo carrega.
"""
import logging
import threading
from dataclasses import dataclass
from typing import Callable

from merlin.config import PASTA_MODELOS

logger = logging.getLogger(__name__)

NOME = "Especialista Defesa Civil (Qwen2.5-3B + LoRA)"
AVISO_CARREGANDO = "Ainda estou carregando os protocolos da Defesa Civil. Pergunte de novo em alguns segundos."
AVISO_FALHOU = "Não consegui carregar o modelo da Defesa Civil. Veja o terminal para saber o motivo."
AVISO_CURTA = "Não entendi a pergunta. Pode repetir com mais detalhes?"
AVISO_FORMATO = "Não consegui montar uma resposta confiável. Tente perguntar de outro jeito."
CACHE_EMBEDDINGS = PASTA_MODELOS / "defesacivil"  # os vetores dos trechos, calculados na primeira carga
# O que o pacote baixa da Hugging Face (ferramentas/baixar_modelos.py): modelo base, busca e adaptador LoRA
MODELOS_HF = ("Qwen/Qwen2.5-3B-Instruct", "intfloat/multilingual-e5-base", "JPSV/jarvis-rescue-lora")


@dataclass(frozen=True)
class Fonte:
    documento: str
    titulo: str
    paginas: tuple[int, int]

    def para_falar(self) -> str:
        ini, fim = self.paginas
        return f"{self.titulo}, página {ini}" if ini == fim else f"{self.titulo}, páginas {ini} a {fim}"


@dataclass(frozen=True)
class RespostaEspecialista:
    texto: str
    encontrou: bool  # False: a resposta não está nos documentos (ou o modelo ainda não está pronto)
    fontes: tuple[Fonte, ...] = ()
    avisos: tuple[str, ...] = ()
    confianca: float | None = None  # similaridade do melhor trecho encontrado

    def para_falar(self) -> str:
        """A resposta e, quando há, a primeira fonte e os avisos do documento (vigência a verificar etc.)."""
        partes = [self.texto]
        if self.fontes:
            partes.append(f"Fonte: {self.fontes[0].para_falar()}.")
        partes += [aviso.split(": ", 1)[-1] for aviso in self.avisos]
        return " ".join(partes)


def _carregar_modelo():
    from defesacivil_llm import DefesaCivilLLM  # importa o torch: só quando o modo especialista é usado
    return DefesaCivilLLM(cache_dir=CACHE_EMBEDDINGS)


class EspecialistaDefesaCivil:
    def __init__(self, carregar: Callable[[], object] = _carregar_modelo):
        self._carregar = carregar
        self._modelo = None
        self._erro: Exception | None = None
        self._pronto = threading.Event()
        self._trava = threading.Lock()  # o modelo atende uma pergunta por vez

    @property
    def nome(self) -> str:
        return NOME

    def iniciar_carga(self) -> None:
        threading.Thread(target=self._carregar_agora, name="carregar-especialista", daemon=True).start()

    def _carregar_agora(self) -> None:
        try:
            logger.info("[ESPECIALISTA] Carregando o modelo da Defesa Civil...")
            self._modelo = self._carregar()
            logger.info("[ESPECIALISTA] Pronto.")
        except Exception as erro:
            logger.error("[ESPECIALISTA] Não consegui carregar: %s", erro)
            self._erro = erro
        finally:
            self._pronto.set()

    def disponivel(self) -> bool:
        """Para o anel da bolinha: só fica "fora" se a carga falhou. Carregando ainda conta como disponível."""
        return self._erro is None

    def responder(self, pergunta: str) -> RespostaEspecialista:
        if not self._pronto.is_set():
            return RespostaEspecialista(AVISO_CARREGANDO, encontrou=False)
        if self._modelo is None:
            return RespostaEspecialista(AVISO_FALHOU, encontrou=False)
        try:
            with self._trava:
                r = self._modelo.perguntar(pergunta)
        except ValueError:  # pergunta curta demais ("oi")
            return RespostaEspecialista(AVISO_CURTA, encontrou=False)
        if r["status"] == "erro_formato":
            return RespostaEspecialista(AVISO_FORMATO, encontrou=False, confianca=r.get("confianca_busca"))
        fontes = tuple(Fonte(c["doc_id"], c["titulo"], tuple(c["paginas"])) for c in r.get("citacoes", []))
        return RespostaEspecialista(r["resposta"], encontrou=r["status"] == "ok", fontes=fontes,
                                    avisos=tuple(r.get("avisos", [])), confianca=r.get("confianca_busca"))
