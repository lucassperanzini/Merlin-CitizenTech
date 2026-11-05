"""Merlin: assistente pessoal por voz, 100% offline."""
import os

# Precisa valer antes de qualquer biblioteca de modelos ser importada:
# depois que os modelos estão baixados, nada acessa a internet.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
