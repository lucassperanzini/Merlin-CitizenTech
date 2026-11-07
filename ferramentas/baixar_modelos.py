"""Baixa os modelos de reconhecimento de voz (Whisper) para a pasta modelos/.

Uso:  .venv\\Scripts\\python.exe ferramentas\\baixar_modelos.py

- large-v3-turbo (~1,6 GB): usado na placa de vídeo NVIDIA.
- small (~0,5 GB): plano B no processador, se a placa de vídeo falhar ou não existir.
Depois de baixados, o Merlin funciona sem internet.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

os.environ["HF_HUB_OFFLINE"] = "0"  # o Merlin roda offline; só este download usa a internet

from faster_whisper import download_model  # noqa: E402

from merlin.config import MODELO_WHISPER_CPU, MODELO_WHISPER_GPU, PASTA_MODELOS  # noqa: E402


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


if __name__ == "__main__":
    main()
