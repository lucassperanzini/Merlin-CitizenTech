"""Baixa os modelos do Merlin para a pasta modelos/.

Uso:  .venv\\Scripts\\python.exe ferramentas\\baixar_modelos.py

- large-v3-turbo (~1,6 GB): reconhecimento de voz na placa de vídeo NVIDIA.
- small (~0,5 GB): plano B no processador, se a placa de vídeo falhar ou não existir.
- Modelo especialista da Defesa Civil (~7 GB, em modelos/huggingface/): o Qwen2.5-3B, o modelo de busca e o
  adaptador LoRA do pacote defesacivil_llm.
- Exemplos da aba Visão (~30 MB, em modelos/exemplos_visao/): 3 vídeos e 2 imagens de incêndio do repositório
  do FireWatch AI, para testar a detecção de fogo com um clique.
Depois de baixados, o Merlin funciona sem internet.
"""
import hashlib
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

os.environ["HF_HUB_OFFLINE"] = "0"  # o Merlin roda offline; só este download usa a internet
os.environ["HF_HUB_DISABLE_XET"] = "1"  # o download pelo Xet chegou a travar no Windows; o HTTP comum não

from faster_whisper import download_model  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402

from merlin.config import MODELO_WHISPER_CPU, MODELO_WHISPER_GPU, PASTA_EXEMPLOS_VISAO, PASTA_MODELOS  # noqa: E402
from merlin.ia.especialista import MODELOS_HF  # noqa: E402
from merlin.interface.painel_visao import EXEMPLOS, ORIGEM_EXEMPLOS  # noqa: E402

CACHE_HF = PASTA_MODELOS / "huggingface" / "hub"  # onde o Merlin procura (HF_HOME em merlin/__init__.py)
# O pacote só lê os pesos .safetensors: as cópias em outros formatos (PyTorch .bin, TensorFlow, Flax, ONNX,
# OpenVINO) ocupariam GBs à toa
PESOS_NAO_USADOS = ["*.bin", "*.h5", "*.msgpack", "*.ot", "*.onnx", "onnx/*", "openvino/*"]


def main():
    for nome in (MODELO_WHISPER_GPU, MODELO_WHISPER_CPU):
        destino = PASTA_MODELOS / nome
        if (destino / "model.bin").is_file():
            print(f"{nome}: já baixado em {destino}")
            continue
        print(f"{nome}: baixando para {destino}...", flush=True)
        download_model(nome, output_dir=str(destino))
        tamanho = sum(a.stat().st_size for a in destino.rglob("*") if a.is_file()) / 1e9
        print(f"{nome}: pronto ({tamanho:.1f} GB)")
    for repositorio in MODELOS_HF:
        print(f"{repositorio}: conferindo em {CACHE_HF}...", flush=True)
        snapshot_download(repositorio, cache_dir=str(CACHE_HF), ignore_patterns=PESOS_NAO_USADOS)
        print(f"{repositorio}: pronto")
    PASTA_EXEMPLOS_VISAO.mkdir(parents=True, exist_ok=True)
    for exemplo in EXEMPLOS:
        baixar_exemplo(exemplo)


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def baixar_exemplo(exemplo) -> None:
    destino = PASTA_EXEMPLOS_VISAO / exemplo.arquivo
    if destino.is_file() and sha256(destino) == exemplo.sha256:
        print(f"exemplo {exemplo.arquivo}: já baixado")
        return
    print(f"exemplo {exemplo.arquivo}: baixando...", flush=True)
    parcial = destino.with_name(destino.name + ".parcial")
    urllib.request.urlretrieve(ORIGEM_EXEMPLOS + urllib.parse.quote(exemplo.arquivo), parcial)
    if sha256(parcial) != exemplo.sha256:  # o arquivo no repositório não é o que foi conferido
        parcial.unlink()
        raise RuntimeError(f"exemplo {exemplo.arquivo}: o arquivo baixado não confere (sha256); nada foi salvo")
    parcial.replace(destino)
    print(f"exemplo {exemplo.arquivo}: pronto ({destino.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
