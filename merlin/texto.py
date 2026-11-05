"""Tratamento de texto usado em mais de uma parte do Merlin."""
import unicodedata

from merlin.config import PALAVRAS_ATIVACAO


def normalizar(texto: str) -> str:
    """Só letras e números, em minúsculas e sem acentos, para comparar nomes ditos em voz alta."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def tem_palavra_ativacao(frase: str) -> bool:
    return any(palavra in frase for palavra in PALAVRAS_ATIVACAO)


def remover_palavra_ativacao(frase: str) -> str:
    frase = frase.lower()
    for palavra in PALAVRAS_ATIVACAO:
        frase = frase.replace(palavra, "")
    return frase.strip(" ,.!?")
