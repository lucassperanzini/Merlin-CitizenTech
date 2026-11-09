"""Todas as configurações ajustáveis do Merlin. Nenhum outro módulo guarda valores fixos de configuração."""
from pathlib import Path

PERSONALIDADE_PADRAO_ID = "merlin"  # as personalidades ficam em merlin/personalidades/, uma por arquivo

TEMPO_INATIVIDADE = 30  # segundos sem comandos -> volta ao modo de espera sozinho
PRAZO_CONFIRMACAO = 20  # segundos para responder antes de uma pergunta de confirmação perder a validade
INTERROMPER_FATOR = 2.5  # quantas vezes mais forte que o eco da própria voz o som precisa ser para interromper
INTERROMPER_DURACAO = 0.25  # segundos que esse som precisa durar (filtra estalos e batidas curtas)
LIMITE_FRASE = 25  # duração máxima, em segundos, de uma frase ouvida
PAUSA_FIM_FRASE = 1.0  # segundos sem voz humana que encerram a frase: mais curto responde mais rápido,
                       # mais longo deixa pausar para pensar no meio do pedido
MAX_TROCAS_LEMBRADAS = 6  # quantas perguntas e respostas da conversa atual o Merlin lembra

MODELO_IA = "qwen3:8b"  # padrão; a escolha feita nas configurações fica salva nas preferências
# Até este número de habilidades, a IA escolhe a intenção de uma vez; acima, em duas etapas (grupo e depois
# intenção), para cada pergunta continuar curta. Veja ferramentas/avaliar_classificador.py.
LIMITE_UMA_ETAPA = 12

PASTA_RAIZ = Path(__file__).resolve().parent.parent
PASTA_MODELOS = PASTA_RAIZ / "modelos"  # modelos de reconhecimento de voz, cada um em uma subpasta
MODELO_WHISPER_GPU = "large-v3-turbo"  # usado na placa de vídeo
MODELO_WHISPER_CPU = "small"  # plano B, mais leve, caso a placa de vídeo falhe
PASTA_VOZES = PASTA_RAIZ / "vozes"
ARQ_PREFERENCIAS = PASTA_RAIZ / "merlin_config.json"
ARQ_OLHO = PASTA_RAIZ / "recursos" / "olho.svg"
ARQ_JANELA = PASTA_RAIZ / "recursos" / "janela.html"
ARQ_CONFIGURACOES = PASTA_RAIZ / "recursos" / "configuracoes.html"
ARQ_RACIOCINIO = PASTA_RAIZ / "recursos" / "raciocinio.html"
ARQ_ASSISTENTES = PASTA_RAIZ / "recursos" / "assistentes.html"
ARQ_HABILIDADES = PASTA_RAIZ / "recursos" / "habilidades.html"
PASTA_SKILLS = PASTA_RAIZ / "skills"  # ajustes das skills feitos na Central (um .json por skill ajustada)
PASTA_ASSISTENTES = PASTA_RAIZ / "assistentes"  # assistentes criados ou ajustados no configurador (um .json cada)
# Os originais (Merlin e Jarvis): o padrão para "Restaurar original". Não podem ser excluídos pela interface.
PASTA_ASSISTENTES_PADRAO = PASTA_RAIZ / "recursos" / "assistentes_padrao"
PASTA_REGISTROS = PASTA_RAIZ / "registros"  # raciocínio da IA, um arquivo de texto por dia
DIAS_DE_REGISTRO = 30  # registros mais antigos que isso são apagados ao abrir o assistente
ARQ_THREE = PASTA_RAIZ / "recursos" / "vendor" / "three.min.js"
ARQ_ESFERA = PASTA_RAIZ / "recursos" / "esfera.js"
VOLUME_SOM_ATIVACAO = 0.7  # de 0 (mudo) a 1

# Janela ativa: um cartão encostado no canto direito, acima da bolinha, para não cobrir o programa em uso
JANELA_LARGURA, JANELA_ALTURA = 400, 620  # em pontos (viram pixels conforme a escala da tela)

# Vozes neurais OFFLINE (Piper). Os arquivos .onnx ficam na pasta "vozes".
# As vozes com efeito (mago, Jarvis) ficam no arquivo de cada personalidade; o seletor junta as duas listas.
VOZ_RESERVA = "pt_BR-faber-medium"  # usada se a voz escolhida não existir
VOZES_PIPER = {
    "Faber (masculina)": "pt_BR-faber-medium",
    "Cadu (masculina)": "pt_BR-cadu-medium",
    "Jeff (masculina)": "pt_BR-jeff-medium",
}

APELIDOS_PROGRAMAS = {
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "calc": "calculadora",
    "notepad": "bloco de notas",
}
