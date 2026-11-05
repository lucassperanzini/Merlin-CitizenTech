"""Todas as configurações ajustáveis do Merlin. Nenhum outro módulo guarda valores fixos de configuração."""
from dataclasses import dataclass
from pathlib import Path

NOME = "Merlin"
PALAVRAS_ATIVACAO = ("merlin", "merlim", "melim", "merlyn", "melinho", "marlin", "berlim")  # variações que o Whisper costuma ouvir

TEMPO_INATIVIDADE = 30  # segundos sem comandos -> volta ao modo de espera sozinho
PRAZO_CONFIRMACAO = 20  # segundos para responder antes de uma pergunta de confirmação perder a validade
INTERROMPER_FATOR = 2.5  # quantas vezes mais forte que o eco da própria voz o som precisa ser para interromper
INTERROMPER_DURACAO = 0.25  # segundos que esse som precisa durar (filtra estalos e batidas curtas)
LIMITE_FRASE = 8  # duração máxima, em segundos, de uma frase ouvida
MAX_TROCAS_LEMBRADAS = 6  # quantas perguntas e respostas da conversa atual o Merlin lembra
MAX_TAREFAS_POR_FRASE = 3  # evita que uma transcrição errada dispare uma sequência longa de ações

MODELO_IA = "qwen2.5:7b"

PASTA_RAIZ = Path(__file__).resolve().parent.parent
PASTA_MODELOS = PASTA_RAIZ / "modelos"  # modelos de reconhecimento de voz, cada um em uma subpasta
MODELO_WHISPER_GPU = "large-v3-turbo"  # usado na placa de vídeo
MODELO_WHISPER_CPU = "small"  # plano B, mais leve, caso a placa de vídeo falhe
PASTA_VOZES = PASTA_RAIZ / "vozes"
ARQ_PREFERENCIAS = PASTA_RAIZ / "merlin_config.json"
ARQ_OLHO = PASTA_RAIZ / "recursos" / "olho.svg"
ARQ_JANELA = PASTA_RAIZ / "recursos" / "janela.html"
ARQ_SOM_ATIVACAO = PASTA_RAIZ / "recursos" / "ativacao.wav"
VOLUME_SOM_ATIVACAO = 0.7  # de 0 (mudo) a 1

JANELA_LARGURA, JANELA_ALTURA = 680, 820

# Vozes neurais OFFLINE (Piper). Os arquivos .onnx ficam na pasta "vozes".
VOZ_PADRAO = "pt_BR-faber-medium"
VOZES = {
    "Faber (masculina)": "pt_BR-faber-medium",
    "Cadu (masculina)": "pt_BR-cadu-medium",
    "Jeff (masculina)": "pt_BR-jeff-medium",
    "Mago ancião": "mago_anciao",
}


@dataclass(frozen=True)
class EfeitoVoz:
    """Voz criada com efeitos sobre um modelo existente."""

    modelo: str
    tom: float  # menor = mais grave (também deixa a fala mais lenta)
    lentidao: float  # maior = fala mais devagar, sem mudar o tom
    tremor: float  # intensidade do tremor de voz idosa (0 = sem tremor)
    eco: float  # intensidade do eco, como numa sala de pedra (0 = sem eco)


EFEITOS_VOZ = {
    "mago_anciao": EfeitoVoz(modelo="pt_BR-faber-medium", tom=0.85, lentidao=1.05, tremor=0.06, eco=0.22),
}

APELIDOS_PROGRAMAS = {
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "calc": "calculadora",
    "notepad": "bloco de notas",
}
