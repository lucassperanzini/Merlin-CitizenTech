"""Instala a clonagem de voz (opcional): PyTorch com CUDA 12.8, o XTTS-v2 (pacote coqui-tts) e o modelo.

Uso:  .venv\\Scripts\\python.exe ferramentas\\instalar_clonagem.py

Tudo fica na pasta do Merlin: as bibliotecas em .venv e o modelo em modelos\\xtts_v2 (~5 GB no total).
As versões anteriores das bibliotecas ficam em .venv\\versoes_antes_da_clonagem.txt, para desfazer se preciso.
Para desinstalar: pip uninstall coqui-tts coqui-tts-trainer torch torchaudio e apague modelos\\xtts_v2.

Escolhas feitas depois de testar nesta máquina (Windows, Python 3.13, RTX 5060 Ti):
- PyTorch 2.8: suporta as placas RTX série 50. A partir do 2.9, o coqui-tts exige o torchcodec, que depende do
  FFmpeg instalado no sistema; o 2.8 dispensa os dois.
- six: o coqui-tts usa, mas não declara como dependência.
- Os pesos do XTTS só existem em .pth. O coqui-tts os carrega no modo seguro do PyTorch (weights_only=True),
  que recusa código embutido no arquivo.
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_MODELO = RAIZ / "modelos" / "xtts_v2"
VERSOES_ANTES = RAIZ / ".venv" / "versoes_antes_da_clonagem.txt"
INDICE_TORCH = "https://download.pytorch.org/whl/cu128"  # a RTX série 50 precisa do PyTorch feito para CUDA 12.8
TORCH = ["torch==2.8.0+cu128", "torchaudio==2.8.0+cu128"]
REPOSITORIO = "coqui/XTTS-v2"
ARQUIVOS = ["config.json", "vocab.json", "model.pth", "dvae.pth", "mel_stats.pth", "speakers_xtts.pth", "LICENSE.txt"]


def pip(*argumentos):
    print(">", "pip", *argumentos, flush=True)
    subprocess.run([sys.executable, "-m", "pip", *argumentos, "--no-cache-dir"], check=True)


def main():
    if not VERSOES_ANTES.exists():
        VERSOES_ANTES.write_text(subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True,
                                                text=True, check=True).stdout, encoding="utf-8")
    pip("install", *TORCH, "--index-url", INDICE_TORCH)
    # Repetir as versões do torch impede que o coqui-tts troque pelo torch comum (sem a placa de vídeo)
    pip("install", "coqui-tts==0.28.0", "six", *TORCH, "--extra-index-url", INDICE_TORCH)

    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import hf_hub_download

    for arquivo in ARQUIVOS:
        caminho = Path(hf_hub_download(REPOSITORIO, arquivo, local_dir=PASTA_MODELO))
        print(f"  {caminho.stat().st_size / 1e6:8.1f} MB  {arquivo}", flush=True)

    import torch
    print(f"PyTorch {torch.__version__} | placa de vídeo: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NÃO ENCONTRADA'}")
    print("Pronto. Abra o Merlin, vá em Configurações > Clonar uma voz.")


if __name__ == "__main__":
    main()
