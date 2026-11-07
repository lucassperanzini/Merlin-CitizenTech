"""Vozes clonadas (opcional): fala com a voz de uma amostra curta, usando o XTTS-v2 na placa de vídeo.

Cada voz clonada é uma pasta em vozes/clonadas/ com:
  referencia.wav - a amostra (5 a 15 s de fala)
  voz.json       - o nome mostrado e o texto dito na amostra (guardado para conferência; o XTTS só usa o áudio)

O XTTS-v2 foi escolhido depois de medir: gera a fala mais rápido do que ela dura (o Qwen3-TTS, testado antes,
levava 3,5 vezes a duração da fala no Windows).

O motor só é carregado quando uma voz clonada é usada. Sem a instalação opcional
(ferramentas/instalar_clonagem.py), as vozes clonadas não aparecem e o resto do Merlin funciona igual.
"""
import importlib.util
import json
import logging
import re
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from merlin.config import PASTA_MODELO_CLONAGEM, PASTA_VOZES_CLONADAS
from merlin.voz.efeitos import encurtar_pausas

logger = logging.getLogger(__name__)

PREFIXO = "clonada:"  # o id de uma voz clonada é "clonada:<pasta>"
ARQUIVO_AUDIO = "referencia.wav"
ARQUIVO_DADOS = "voz.json"
IDIOMA = "pt"
LIMITE_TRECHO = 180  # caracteres por trecho; o XTTS avisa e piora acima de ~200 em português
LIMITE_PRIMEIRO_TRECHO = 70  # o primeiro trecho é curto para a fala começar logo (~1 s)
PAUSA_ENTRE_TRECHOS = 0.15  # segundos de silêncio entre as frases geradas separadamente
ARQUIVOS_DO_MODELO = ("config.json", "vocab.json", "model.pth", "dvae.pth", "mel_stats.pth", "speakers_xtts.pth")


@dataclass(frozen=True)
class VozClonada:
    id: str
    nome: str
    pasta: Path
    texto: str  # o que é dito na amostra

    @property
    def rotulo(self) -> str:
        return f"{self.nome} (clonada)"

    @property
    def audio(self) -> Path:
        return self.pasta / ARQUIVO_AUDIO


def e_clonada(voz: str) -> bool:
    return voz.startswith(PREFIXO)


def clonagem_instalada() -> bool:
    """O PyTorch, o pacote do XTTS (coqui-tts) e os arquivos do modelo estão instalados."""
    pacotes = all(importlib.util.find_spec(nome) is not None for nome in ("torch", "TTS"))
    return pacotes and all((PASTA_MODELO_CLONAGEM / arquivo).is_file() for arquivo in ARQUIVOS_DO_MODELO)


def listar_vozes_clonadas(pasta: Path = PASTA_VOZES_CLONADAS) -> list[VozClonada]:
    vozes = []
    for subpasta in sorted(p for p in pasta.glob("*") if p.is_dir()) if pasta.is_dir() else []:
        try:
            dados = json.loads((subpasta / ARQUIVO_DADOS).read_text(encoding="utf-8"))
            if (subpasta / ARQUIVO_AUDIO).is_file():
                vozes.append(VozClonada(PREFIXO + subpasta.name, dados.get("nome") or subpasta.name, subpasta,
                                        dados.get("texto", "")))
        except (OSError, ValueError):
            logger.warning("[VOZ] Voz clonada incompleta ignorada: %s", subpasta.name)
    return vozes


def buscar_voz_clonada(voz: str, pasta: Path = PASTA_VOZES_CLONADAS) -> VozClonada | None:
    return next((v for v in listar_vozes_clonadas(pasta) if v.id == voz), None)


def nome_de_pasta(nome: str) -> str:
    """ "Minha Voz!" -> "minha_voz": sem acentos, espaços ou símbolos."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_") or "voz"


def salvar_voz_clonada(nome: str, audio: np.ndarray, taxa: int, texto: str,
                       pasta: Path = PASTA_VOZES_CLONADAS) -> VozClonada:
    """Grava a amostra e os dados. Se o nome já existir, a voz antiga é substituída."""
    import soundfile as sf  # vem junto da instalação opcional

    destino = pasta / nome_de_pasta(nome)
    destino.mkdir(parents=True, exist_ok=True)
    sf.write(destino / ARQUIVO_AUDIO, audio, taxa)
    (destino / ARQUIVO_DADOS).write_text(json.dumps({"nome": nome.strip(), "texto": texto.strip()},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    return VozClonada(PREFIXO + destino.name, nome.strip(), destino, texto.strip())


def apagar_voz_clonada(voz: VozClonada) -> None:
    for arquivo in (voz.audio, voz.pasta / ARQUIVO_DADOS):
        arquivo.unlink(missing_ok=True)
    try:
        voz.pasta.rmdir()
    except OSError:
        pass  # sobrou algo que não é nosso: a pasta fica


SEPARADORES = (r"(?<=[,;:])\s+", r"\s+")  # primeiro nas vírgulas; se não der, nos espaços


def dividir_texto(texto: str, limite: int = LIMITE_TRECHO, limite_primeiro: int | None = None) -> list[str]:
    """Divide em frases e, se uma frase passar do limite do XTTS, também nas vírgulas e depois nos espaços.
    (A divisão do próprio XTTS exige a biblioteca spaCy, de centenas de MB.)

    limite_primeiro: para falar enquanto gera. Só o primeiro trecho é cortado curto (na vírgula), para a fala
    começar logo; o resto daquela frase vai inteiro. Cada pedaço é gerado separado e termina com entonação de fim
    de frase: cortar todas as frases nas vírgulas deixava a fala picotada e robótica."""
    trechos = []
    for frase in re.split(r"(?<=[.!?…])\s+", texto.strip()):
        trechos += _quebrar(frase, limite, SEPARADORES)
    trechos = [t for t in trechos if t.strip()] or [texto.strip() or "."]
    if limite_primeiro and len(trechos[0]) > limite_primeiro:
        partes = _quebrar(trechos[0], limite_primeiro, SEPARADORES)
        resto = " ".join(partes[1:])
        trechos = [partes[0], *_quebrar(resto, limite, SEPARADORES), *trechos[1:]]
    return trechos


def _quebrar(texto, limite, separadores):
    if len(texto) <= limite or not separadores:
        return [texto]
    partes, atual = [], ""
    for pedaco in re.split(separadores[0], texto):
        if atual and len(atual) + 1 + len(pedaco) > limite:
            partes.append(atual)
            atual = pedaco
        else:
            atual = f"{atual} {pedaco}".strip()
    partes.append(atual)
    return [menor for parte in partes for menor in _quebrar(parte, limite, separadores[1:])]


class MotorClonagem:
    """Carrega o XTTS-v2 uma vez e guarda a "impressão" de cada voz, para não reprocessar a amostra a cada fala."""

    def __init__(self, pasta_modelo: Path = PASTA_MODELO_CLONAGEM):
        self._pasta = pasta_modelo
        self._modelo = None
        self._impressoes = {}
        self._trava = threading.Lock()

    def precarregar(self) -> None:
        with self._trava:
            self._carregar()

    def gerar(self, texto: str, voz: VozClonada) -> tuple[np.ndarray, int]:
        """Devolve o áudio (float, -1 a 1) e a taxa de amostragem."""
        with self._trava:
            modelo = self._carregar()
            impressao = self._impressoes.get(voz.id)
            if impressao is None:
                impressao = self._impressao_da_voz(modelo, voz)
                self._impressoes[voz.id] = impressao
            latente, falante = impressao
            taxa = modelo.config.audio.output_sample_rate
            pausa = np.zeros(int(PAUSA_ENTRE_TRECHOS * taxa), dtype=np.float32)
            audio = []
            for trecho in dividir_texto(texto):
                # Gerar em pedaços e juntar é mais rápido que a geração de uma vez (medido: 1,3 s contra 2,8 s)
                audio += [p.cpu().numpy() for p in modelo.inference_stream(trecho, IDIOMA, latente, falante)]
                audio.append(pausa)
        # O modelo às vezes faz pausas longas no meio da fala, o que soa robótico
        return encurtar_pausas(np.concatenate(audio[:-1]).astype(np.float32), taxa), taxa

    @staticmethod
    def _impressao_da_voz(modelo, voz):
        """A amostra com as pausas longas encurtadas: o modelo copia o jeito de falar da amostra, inclusive as
        hesitações ("é… tipo…"). É feito numa cópia temporária; o arquivo da voz não muda."""
        import soundfile as sf

        amostra, taxa = sf.read(str(voz.audio), dtype="float32", always_2d=False)
        if amostra.ndim > 1:
            amostra = amostra.mean(axis=1)
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "amostra.wav"
            sf.write(arquivo, encurtar_pausas(amostra, taxa), taxa)
            return modelo.get_conditioning_latents(audio_path=[str(arquivo)])

    def esquecer(self, voz_id: str) -> None:
        """Depois de regravar uma voz, a impressão antiga não vale mais."""
        self._impressoes.pop(voz_id, None)

    def _carregar(self):
        if self._modelo is None:
            import torch
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts

            logger.info("[VOZ] Carregando o modelo de clonagem de voz...")
            config = XttsConfig()
            config.load_json(str(self._pasta / "config.json"))
            modelo = Xtts(config)
            # O coqui-tts carrega os pesos (.pth) no modo seguro do PyTorch (weights_only): código embutido é recusado
            modelo.load_checkpoint(config, checkpoint_dir=str(self._pasta), use_deepspeed=False)
            self._modelo = modelo.cuda() if torch.cuda.is_available() else modelo
        return self._modelo
