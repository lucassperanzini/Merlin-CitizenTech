"""O modelo especialista da Defesa Civil (pacote defesacivil_llm): RAG + LoRA sobre os protocolos de incêndio.

Responde só com base nos documentos da base. A carga leva alguns segundos e ocupa ~3,7 GB da placa de vídeo em
4 bits (~7,8 GB em 16 bits), então ela é feita em segundo plano: o Merlin abre e ouve enquanto o modelo carrega.
"""
import logging
import threading
from dataclasses import dataclass
from typing import Callable

from merlin.config import ESPECIALISTA_4_BITS, PASTA_MODELOS, PASTA_PROTOCOLOS

logger = logging.getLogger(__name__)

NOME = "Especialista Defesa Civil (Qwen2.5-3B + LoRA)"
AVISO_CARREGANDO = "Ainda estou carregando os protocolos da Defesa Civil. Pergunte de novo em alguns segundos."
AVISO_FALHOU = "Não consegui carregar o modelo da Defesa Civil. Veja o terminal para saber o motivo."
AVISO_CURTA = "Não entendi a pergunta. Pode repetir com mais detalhes?"
AVISO_FORMATO = "Não consegui montar uma resposta confiável. Tente perguntar de outro jeito."
CACHE_EMBEDDINGS = PASTA_MODELOS / "defesacivil"  # os vetores dos trechos, calculados na primeira carga
# O que o pacote baixa da Hugging Face (ferramentas/baixar_modelos.py): modelo base, busca e adaptador LoRA
MODELOS_HF = ("Qwen/Qwen2.5-3B-Instruct", "intfloat/multilingual-e5-base", "JPSV/jarvis-rescue-lora")

# Os PDFs da base de conhecimento do especialista, do repositório do autor (Base_Conhecimento/), fixados no commit
# instalado. Ficam em modelos/protocolos/DOC00x.pdf (ferramentas/baixar_modelos.py), para a fonte citada abrir na
# página certa. As páginas dos trechos do RAG são as físicas do PDF (a 1ª folha é a página 1).
ORIGEM_PROTOCOLOS = ("https://raw.githubusercontent.com/JBVJoaoV/GS2-GENIA/"
                     "20b521c104512c6fd2e3209906c39f72eb91b77c/Base_Conhecimento/")
DOCUMENTOS = {  # código: (caminho no repositório, sha256)
    "DOC001": ("01_prevencao_manejo/20250428_roteiro_metodologico.pdf",
               "2417e5faf878edd677d96532caf0b4ea87315211c067661d61a18d5dd2e0e2b5"),
    "DOC002": ("01_prevencao_manejo/GUIA-PRATICO-PMIF.pdf",
               "418ac8967f82c6b11438d03d166b135d5ce5d07339f27de87d09f99c2801831a"),
    "DOC003": ("01_prevencao_manejo/cartilhaPNMIF.pdf",
               "33c07373093d3f8a9a0781720f6190ee85095c868fac35b0e9502d8e56e1d74a"),
    "DOC004": ("01_prevencao_manejo/E-possivel-controlar-fogo-vs-site.pdf",
               "b99114c7db8947bd497cd0cbe774a6a3a5a2864f5ca58af5cad4a48273123ca0"),
    "DOC005": ("02_brigadistas_seguranca/2010_ICMBIO_ApostilaBrigadistaPrevencaoIncendios_MMA_DE3os.pdf",
               "11b13ee7dd581ef61302b97fa0f569da01b227ae6627b7f62b64c5adebcf9984"),
    "DOC006": ("03_comando_incidentes/20250311_Manual_22661453_Manual_SCI_100_Introducao_ao_Sistema_de_Comando_de_"
               "Incidente_marco2025.pdf", "b2885af7174dd408d3e59edd641358f3e144fc0a5ff829bf203b3d5784a670c7"),
    "DOC007": ("03_comando_incidentes/20250311_Manual_22661456_Manual_SCI_200_Basico_do_Sistema_de_Comando_de_"
               "Incidentes_para_Resposta_Inicial_marco2025.pdf",
               "04f82cf222f99c2b7a02c79f34b712ee355241d9872786488a16c86e957331b0"),
    "DOC008": ("03_comando_incidentes/20250311_Manual_22661458_Manual_do_Curso_Intermediario_SCI_300_para_incidentes_"
               "em_expansao_marco2025.pdf", "1a2cc61d02dac8fd48a8121acc9ed79ee6f9bdc866c947865e34a4979d3eade1"),
    "DOC009": ("04_incendios_edificacoes/instrucao_tecnica_16_2015_plano_de_emergencia_contra_incendio.pdf",
               "f382e82529d4ee5a6b28b0e709b7fa3c09f225f36bd343548077e27c7603e056"),
}


def pdf_do_documento(documento: str):
    """O PDF baixado de um documento da base, ou None (código desconhecido ou ainda não baixado)."""
    if documento not in DOCUMENTOS:
        return None
    caminho = PASTA_PROTOCOLOS / f"{documento}.pdf"
    return caminho if caminho.is_file() else None


@dataclass(frozen=True)
class Fonte:
    documento: str
    titulo: str
    paginas: tuple[int, int]

    def para_falar(self) -> str:
        ini, fim = self.paginas
        return f"{self.titulo}, página {ini}" if ini == fim else f"{self.titulo}, páginas {ini} a {fim}"

    def para_cartao(self) -> dict:
        """O botão da fonte, embaixo da resposta: abre o PDF na primeira página do trecho citado."""
        ini, fim = self.paginas
        return {"documento": self.documento, "titulo": self.titulo, "pagina": ini,
                "paginas": f"p. {ini}" if ini == fim else f"pp. {ini}-{fim}",
                "disponivel": pdf_do_documento(self.documento) is not None}


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
