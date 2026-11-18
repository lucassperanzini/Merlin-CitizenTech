"""O modelo especialista da Defesa Civil (pacote defesacivil_llm): RAG + LoRA sobre os protocolos de incêndio.

Responde só com base nos documentos da base. A carga leva alguns segundos e ocupa ~3,7 GB da placa de vídeo em
4 bits (~7,8 GB em 16 bits), então ela é feita em segundo plano: o Merlin abre e ouve enquanto o modelo carrega.
"""
import logging
import threading
from dataclasses import dataclass
from typing import Callable

from merlin.config import ESPECIALISTA_4_BITS, PASTA_MODELOS

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


class Gerador4Bits:
    """O mesmo gerador do pacote (rag.Generator), com o modelo base quantizado em 4 bits pelo bitsandbytes.
    O pacote só carrega em 16 bits; ele aceita um gerador pronto, então a troca fica do lado do Merlin."""

    def __init__(self):
        import torch
        from defesacivil_llm import config
        from defesacivil_llm.llm import ADAPTER_PADRAO
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        quantizacao = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                                         bnb_4bit_compute_dtype=torch.float16)
        self._torch = torch
        self._max_tokens = config.MAX_NEW_TOKENS
        self.tok = AutoTokenizer.from_pretrained(config.MODEL_NAME)
        base = AutoModelForCausalLM.from_pretrained(config.MODEL_NAME, quantization_config=quantizacao,
                                                    device_map="cuda:0")
        self.model = PeftModel.from_pretrained(base, ADAPTER_PADRAO).eval()
        self.adapter_path = ADAPTER_PADRAO

    def generate(self, messages, max_new_tokens=None):
        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        entrada = self.tok(prompt, return_tensors="pt").to(self.model.device)
        with self._torch.no_grad():
            saida = self.model.generate(**entrada, max_new_tokens=max_new_tokens or self._max_tokens, do_sample=False,
                                        temperature=None, top_p=None, top_k=None, pad_token_id=self.tok.eos_token_id)
        return self.tok.decode(saida[0][entrada["input_ids"].shape[1]:], skip_special_tokens=True)


def _carregar_modelo():
    from defesacivil_llm import DefesaCivilLLM  # importa o torch: só quando o especialista é carregado
    return DefesaCivilLLM(cache_dir=CACHE_EMBEDDINGS, gerador=Gerador4Bits() if ESPECIALISTA_4_BITS else None)


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

    def parece_protocolo(self, pergunta: str) -> bool:
        """A busca acha um trecho dos protocolos parecido o bastante para responder? Só a busca, sem gerar texto
        (milissegundos): confirma a escolha da IA de conversa. Falso enquanto o modelo não está pronto."""
        if self._modelo is None:
            return False
        with self._trava:
            melhor = self._modelo._buscador.search(pergunta, k=1)[0]["score"]
        return melhor >= self._modelo.limiar

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
