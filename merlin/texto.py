"""Tratamento de texto usado em mais de uma parte do assistente."""
import unicodedata


def normalizar(texto: str) -> str:
    """Só letras e números, em minúsculas e sem acentos, para comparar nomes ditos em voz alta."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def com_artigo(nome: str) -> str:
    """"o chrome", "a calculadora". Aproximação pela primeira palavra, para soar natural na fala."""
    feminino = nome.split()[0].lower().endswith("a") if nome.strip() else False
    return f"{'a' if feminino else 'o'} {nome}"


def tem_palavra_ativacao(frase: str, palavras: tuple[str, ...]) -> bool:
    return any(palavra in frase.lower() for palavra in palavras)


def remover_palavra_ativacao(frase: str, palavras: tuple[str, ...]) -> str:
    frase = frase.lower()
    for palavra in palavras:
        frase = frase.replace(palavra, "")
    return frase.strip(" ,.!?")
