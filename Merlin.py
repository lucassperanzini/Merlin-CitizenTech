import ctypes
import difflib
import io
import json
import math
import os
import queue
import random
import tempfile
import threading
import time
import unicodedata
import wave
from collections import deque
from urllib.parse import quote_plus

# 100% offline: depois que os modelos estão baixados, nada acessa a internet.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import numpy as np
import ollama
import psutil
import pygame
import speech_recognition as sr
import webview
import win32con
import win32gui
import win32process
from AppOpener import give_appnames as nomes_programas_instalados, open as abrir_app
from faster_whisper import WhisperModel
from piper import PiperVoice, SynthesisConfig

# ==========================================
# CONFIGURAÇÕES
# ==========================================
NOME = "Merlin"
PALAVRAS_ATIVACAO = ["merlin", "merlim", "melim", "merlyn", "melinho", "marlin", "berlim"]  # variações que o Whisper costuma ouvir
TEMPO_INATIVIDADE = 30  # segundos sem comandos -> volta ao modo de espera sozinho
PRAZO_CONFIRMACAO = 20  # segundos para responder antes de uma pergunta de confirmação perder a validade
INTERROMPER_FATOR = 2.5     # quantas vezes mais forte que o eco da própria voz o som precisa ser para interromper
INTERROMPER_DURACAO = 0.25  # segundos que esse som precisa durar (filtra estalos e batidas curtas)
MODELO_IA = "qwen2.5:7b"
MODELO_WHISPER = "small"  # "base" é mais rápido; "medium" é mais preciso

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_VOZES = os.path.join(PASTA, "vozes")
ARQ_CONFIG = os.path.join(PASTA, "merlin_config.json")
ARQ_OLHO = os.path.join(PASTA, "merlin_olho.svg")
ARQ_JANELA = os.path.join(PASTA, "merlin_janela.html")

# Vozes neurais OFFLINE (Piper). Os arquivos .onnx ficam na pasta "vozes".
VOZES = {
    "Faber (masculina)": "pt_BR-faber-medium",
    "Cadu (masculina)": "pt_BR-cadu-medium",
    "Jeff (masculina)": "pt_BR-jeff-medium",
    "Mago ancião": "mago_anciao",
}

# Vozes criadas com efeitos sobre um modelo existente. Para ajustar a voz, mude os valores abaixo:
EFEITOS_VOZ = {
    "mago_anciao": {
        "modelo": "pt_BR-faber-medium",
        "tom": 0.85,        # menor = mais grave (também deixa a fala mais lenta)
        "lentidao": 1.05,   # maior = fala mais devagar, sem mudar o tom
        "tremor": 0.06,     # intensidade do tremor de voz idosa (0 = sem tremor)
        "eco": 0.22,        # intensidade do eco, como numa sala de pedra (0 = sem eco)
    },
}


def carregar_config():
    try:
        with open(ARQ_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def salvar_config():
    try:
        with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CONFIG] Não consegui salvar: {e}")


config = carregar_config()
voz_atual = config.get("voz", "pt_BR-faber-medium")
if voz_atual not in VOZES.values():
    voz_atual = "pt_BR-faber-medium"

# ==========================================
# ESTADO COMPARTILHADO ENTRE THREADS
# ==========================================
fila_ui = queue.Queue()        # mensagens para a janela
fila_comandos = queue.Queue()  # frases reconhecidas para o worker processar
ativo = threading.Event()      # Merlin ativado?
falando = threading.Event()    # evita que ele escute a própria voz
reproduzindo = threading.Event()  # o áudio está saindo pelas caixas de som (só aí dá para interromper)
interromper = threading.Event()   # a pessoa falou por cima: a fala atual deve parar
ultima_atividade = time.time()
encerrar_programa = threading.Event()
nivel_voz = 0.0                # maior volume captado desde a última atualização da janela (0 a 1)

pygame.mixer.init()


# ==========================================
# VOZ (TTS offline com Piper)
# ==========================================
_vozes_carregadas = {}


def _obter_voz(nome):
    if nome not in _vozes_carregadas:
        _vozes_carregadas[nome] = PiperVoice.load(os.path.join(PASTA_VOZES, nome + ".onnx"))
    return _vozes_carregadas[nome]


def _modelo_da_voz(voz):
    return EFEITOS_VOZ[voz]["modelo"] if voz in EFEITOS_VOZ else voz


def aplicar_efeito(amostras, taxa, efeito):
    """Recebe áudio em float (-1 a 1) e devolve o áudio com tom, tremor e eco aplicados."""
    # Esticar o áudio e tocar na mesma taxa deixa a voz mais grave
    novo_tamanho = int(len(amostras) / efeito["tom"])
    posicoes = np.linspace(0, len(amostras) - 1, novo_tamanho)
    audio = np.interp(posicoes, np.arange(len(amostras)), amostras)

    tempo = np.arange(len(audio)) / taxa
    audio = audio * (1 - efeito["tremor"] * (0.5 + 0.5 * np.sin(2 * np.pi * 5.5 * tempo)))

    # Duas reflexões curtas, mais a cauda final para o eco não ser cortado
    atrasos = [(0.09, efeito["eco"]), (0.17, efeito["eco"] * 0.55)]
    cauda = int(max(a for a, _ in atrasos) * taxa)
    saida = np.concatenate([audio, np.zeros(cauda)])
    for atraso, ganho in atrasos:
        n = int(atraso * taxa)
        saida[n:n + len(audio)] += audio * ganho

    pico = np.max(np.abs(saida))
    return saida * (0.95 / pico) if pico > 0.95 else saida


def gerar_audio(texto, voz, arquivo):
    """Sintetiza o texto em um WAV, aplicando o efeito quando a voz tiver um."""
    efeito = EFEITOS_VOZ.get(voz)
    modelo = _obter_voz(_modelo_da_voz(voz))
    if not efeito:
        with wave.open(arquivo, "wb") as w:
            modelo.synthesize_wav(texto, w)
        return

    memoria = io.BytesIO()
    with wave.open(memoria, "wb") as w:
        modelo.synthesize_wav(texto, w, syn_config=SynthesisConfig(length_scale=efeito["lentidao"]))
    memoria.seek(0)
    with wave.open(memoria, "rb") as w:
        taxa = w.getframerate()
        amostras = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    resultado = aplicar_efeito(amostras, taxa, efeito)
    with wave.open(arquivo, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((resultado * 32767).astype(np.int16).tobytes())


def _falar_fallback(texto):
    """Plano B (voz do Windows, também offline) caso o Piper falhe."""
    try:
        import pyttsx3
        eng = pyttsx3.init()
        for v in eng.getProperty("voices"):
            if "brazil" in v.name.lower() or "portuguese" in v.name.lower():
                eng.setProperty("voice", v.id)
                break
        eng.say(texto)
        eng.runAndWait()
    except Exception as e:
        print(f"[TTS fallback] {e}")


def falar(texto):
    """Fala em voz alta (e imprime no terminal para debug)."""
    global ultima_atividade
    print(f"{NOME}: {texto}")
    fila_ui.put(("legenda", texto))
    fila_ui.put(("estado", "falando"))
    interromper.clear()
    arquivo = os.path.join(tempfile.gettempdir(), f"merlin_{os.getpid()}_{time.time_ns()}.wav")
    try:
        gerar_audio(texto, voz_atual, arquivo)
        falando.set()
        pygame.mixer.music.load(arquivo)
        pygame.mixer.music.play()
        reproduzindo.set()
        while pygame.mixer.music.get_busy():
            if interromper.is_set():
                pygame.mixer.music.stop()
                print("[INFO] Fala interrompida.")
                break
            time.sleep(0.02)
        reproduzindo.clear()
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"[TTS] Piper falhou ({e}); usando voz do Windows.")
        reproduzindo.clear()
        falando.set()
        _falar_fallback(texto)
    finally:
        try:
            os.remove(arquivo)
        except OSError:
            pass
        falando.clear()
        ultima_atividade = time.time()
        fila_ui.put(("estado", "ouvindo" if ativo.is_set() else "espera"))


# ==========================================
# FERRAMENTAS QUE O PYTHON VAI EXECUTAR
# ==========================================
APELIDOS_PROGRAMAS = {"vs code": "visual studio code", "vscode": "visual studio code",
                      "calc": "calculadora", "notepad": "bloco de notas"}


def encontrar_programa(nome):
    """Nome do programa instalado que corresponde ao pedido, ou None. O AppOpener não avisa quando não acha."""
    pedido = nome.strip().lower()
    pedido = APELIDOS_PROGRAMAS.get(pedido, pedido)
    instalados = [str(p).lower() for p in nomes_programas_instalados()]
    if pedido in instalados:
        return pedido
    parecidos = difflib.get_close_matches(pedido, instalados, n=1, cutoff=0.6)
    return parecidos[0] if parecidos else None


def executar_abrir_programa(nome_programa):
    programa = encontrar_programa(nome_programa)
    if not programa:
        falar(f"Não encontrei o programa {nome_programa} instalado. Vou procurar na internet.")
        return executar_pesquisa_web(nome_programa)
    try:
        falar(f"Abrindo {programa}.")
        abrir_app(programa, output=False)
        return f"Sucesso: {programa} foi aberto."
    except Exception as e:
        falar(f"Não consegui abrir {programa}.")
        return f"Erro ao abrir {programa}: {e}"


def executar_pesquisa_web(termo):
    falar(f"Pesquisando por {termo}.")
    if termo.startswith("http") or (".com" in termo and " " not in termo):
        url = termo if termo.startswith("http") else f"https://{termo}"
    else:
        url = f"https://www.google.com/search?q={quote_plus(termo)}"
    os.startfile(url)
    return f"Sucesso: Pesquisa por '{termo}' realizada."


# --- Fechar programas ---
# Não usa o close() do AppOpener: ele mata o processo à força (perde trabalho não salvo) e aceita qualquer
# processo de nome parecido. Aqui só janelas visíveis são candidatas, e o WM_CLOSE equivale a clicar no X.
CLASSES_PROTEGIDAS = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
acao_pendente = None  # janelas aguardando confirmação: {"descricao", "janelas", "expira"}


def _normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def _janela_oculta_pelo_sistema(hwnd):
    # Apps da Microsoft Store deixam janelas "visíveis" que na verdade não aparecem na tela
    oculta = ctypes.c_int(0)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(oculta), ctypes.sizeof(oculta))
    return oculta.value != 0


def listar_janelas():
    """Janelas principais abertas pelo usuário, sem as do próprio Merlin e as da área de trabalho."""
    janelas = []

    def visitar(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        titulo = win32gui.GetWindowText(hwnd).strip()
        if not titulo or win32gui.GetClassName(hwnd) in CLASSES_PROTEGIDAS or _janela_oculta_pelo_sistema(hwnd):
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == os.getpid():
            return True
        try:
            programa = os.path.splitext(psutil.Process(pid).name())[0]
        except psutil.Error:
            return True
        janelas.append({"hwnd": hwnd, "pid": pid, "programa": programa, "titulo": titulo})
        return True

    win32gui.EnumWindows(visitar, None)
    return janelas


def escolher_janelas(nome, janelas):
    """Retorna (janelas encontradas, se foi pelo título). Prefere o nome do programa ao título da janela."""
    alvo = _normalizar(nome)
    if len(alvo) < 3:
        return [], False
    palavras = {_normalizar(p) for p in nome.split()}  # "google chrome" combina com chrome

    def combina_programa(j):
        programa = _normalizar(j["programa"])
        return alvo == programa or (len(alvo) >= 4 and alvo in programa) or programa in palavras

    achadas = [j for j in janelas if combina_programa(j)]
    if not achadas:
        parecidos = difflib.get_close_matches(alvo, {_normalizar(j["programa"]) for j in janelas}, n=1, cutoff=0.8)
        achadas = [j for j in janelas if _normalizar(j["programa"]) in parecidos]
    if achadas:
        return achadas, False
    return [j for j in janelas if alvo in _normalizar(j["titulo"])], True


def executar_fechar_programa(nome_programa):
    """Não fecha nada: localiza as janelas e pergunta. Quem fecha é confirmar_fechamento, após o sim."""
    global acao_pendente
    janelas, pelo_titulo = escolher_janelas(nome_programa, listar_janelas())
    if not janelas:
        falar(f"Não encontrei {nome_programa} aberto.")
        return f"Nada encontrado para '{nome_programa}'."

    programas = sorted({j["programa"] for j in janelas})
    if len(programas) > 1:
        falar(f"Encontrei mais de um: {', '.join(programas)}. Qual deles você quer fechar?")
        return f"Ambíguo: {programas}"

    if pelo_titulo and len(janelas) == 1:
        descricao = f"a janela {janelas[0]['titulo'][:60]}"
    elif len(janelas) > 1:
        descricao = f"as {len(janelas)} janelas de {programas[0]}"
    else:
        descricao = programas[0]
    acao_pendente = {"descricao": descricao, "janelas": janelas, "expira": time.time() + PRAZO_CONFIRMACAO}
    falar(f"Posso fechar {descricao}?")
    return f"Aguardando confirmação: {descricao}"


def _ainda_aberta(janela):
    if not win32gui.IsWindow(janela["hwnd"]):
        return False
    return win32process.GetWindowThreadProcessId(janela["hwnd"])[1] == janela["pid"]


def confirmar_fechamento(pendente):
    falhas = 0
    for janela in pendente["janelas"]:
        try:
            if _ainda_aberta(janela):
                win32gui.PostMessage(janela["hwnd"], win32con.WM_CLOSE, 0, 0)
        except win32gui.error as e:
            print(f"[FECHAR] {e}")
            falhas += 1
    time.sleep(2.5)  # dá tempo de o programa fechar antes de anunciar o resultado
    abertas = sum(1 for j in pendente["janelas"] if _ainda_aberta(j))
    if abertas or falhas:
        falar(f"Pedi para fechar {pendente['descricao']}, mas continua aberto. Talvez esteja perguntando se você quer salvar.")
    else:
        falar(f"Pronto, fechei {pendente['descricao']}.")


def pegar_pendente():
    """Entrega a ação pendente uma única vez; se o prazo acabou, ela é descartada sem agir."""
    global acao_pendente
    pendente, acao_pendente = acao_pendente, None
    if pendente and time.time() > pendente["expira"]:
        print("[INFO] Confirmação expirada.")
        return None
    return pendente


# Etapa que decide o que a pessoa quer. O modelo escreve primeiro o alvo da frase, e o código só aceita
# sair quando o alvo é o próprio Merlin (ver classificar_intencao).
ESQUEMA_INTENCAO = {
    "type": "object",
    "properties": {
        "alvo": {"type": "string"},
        "intencao": {
            "type": "string",
            "enum": ["dispensar", "encerrar", "fechar_programa", "abrir_programa", "pesquisar_web", "conversar"],
        },
        "busca": {"type": "string"},
    },
    "required": ["alvo", "intencao", "busca"],
}
PROMPT_INTENCAO = """Analise a frase dita a um assistente de voz chamado Merlin. Preencha nesta ordem:

alvo: a coisa de que a frase fala ou que ela manda fechar, desligar, abrir ou deixar (um programa, site, aparelho, pessoa, música ou assunto), em uma ou duas palavras. Escreva "merlin" somente se a frase não citar nada disso, porque nesse caso ela é dirigida ao próprio assistente.

intencao:
- dispensar: a pessoa se despede do Merlin, agradece encerrando a conversa, diz que já terminou ou que não precisa mais dele, ou manda ele sair ou descansar, mesmo com gíria ou de forma rude.
- encerrar: a pessoa pede claramente para fechar o programa do assistente por completo ou desligá-lo de vez, para ele parar de escutar.
- fechar_programa: a pessoa manda fechar, encerrar ou sair de um programa ou janela aberta no computador. O alvo é o nome do programa.
- abrir_programa: a pessoa manda abrir ou iniciar um programa instalado no computador. O alvo é o nome do programa.
- pesquisar_web: a pessoa manda pesquisar ou procurar algo na internet, ou abrir um site.
- conversar: qualquer outra coisa, inclusive perguntas de conhecimento geral, perguntas sobre como fazer algo, aparelhos fora do computador e pedidos sobre despedidas.

busca: somente em pesquisar_web, o termo completo a pesquisar, ou o endereço quando for abrir um site. Nos outros casos, deixe vazio.

Exemplos:
"obrigado, pode ir" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"terminamos aqui" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"vai lá, depois te chamo" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"boa noite" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"cai fora" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"fecha a janela" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"pode fechar esta janela" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"finaliza o programa" -> {"alvo": "merlin", "intencao": "encerrar", "busca": ""}
"fecha o programa" -> {"alvo": "merlin", "intencao": "encerrar", "busca": ""}
"quero você desligado de vez" -> {"alvo": "merlin", "intencao": "encerrar", "busca": ""}
"feche o word" -> {"alvo": "word", "intencao": "fechar_programa", "busca": ""}
"encerra o navegador" -> {"alvo": "navegador", "intencao": "fechar_programa", "busca": ""}
"sai do outlook" -> {"alvo": "outlook", "intencao": "fechar_programa", "busca": ""}
"abre o paint" -> {"alvo": "paint", "intencao": "abrir_programa", "busca": ""}
"inicia o photoshop" -> {"alvo": "photoshop", "intencao": "abrir_programa", "busca": ""}
"pesquise receitas de pão" -> {"alvo": "receitas de pão", "intencao": "pesquisar_web", "busca": "receitas de pão"}
"procura na internet como sair do nano" -> {"alvo": "nano", "intencao": "pesquisar_web", "busca": "como sair do nano"}
"abre o site da globo" -> {"alvo": "globo", "intencao": "pesquisar_web", "busca": "globo.com"}
"entra no github" -> {"alvo": "github", "intencao": "pesquisar_web", "busca": "github.com"}
"apaga a luz" -> {"alvo": "luz", "intencao": "conversar", "busca": ""}
"diga adeus para a maria" -> {"alvo": "maria", "intencao": "conversar", "busca": ""}
"como saio do excel" -> {"alvo": "excel", "intencao": "conversar", "busca": ""}
"toca a música adeus" -> {"alvo": "música adeus", "intencao": "conversar", "busca": ""}
"qual o sentido de acordar cedo" -> {"alvo": "acordar cedo", "intencao": "conversar", "busca": ""}
"qual a capital do chile" -> {"alvo": "capital do chile", "intencao": "conversar", "busca": ""}
"que horas fecha o mercado" -> {"alvo": "mercado", "intencao": "conversar", "busca": ""}"""

ALVOS_JANELA_DO_MERLIN = {"janela", "essajanela", "estajanela", "ajanela"}

# Resposta a uma pergunta de confirmação. Só "sim" autoriza a ação; o resto nunca age.
ESQUEMA_CONFIRMACAO = {
    "type": "object",
    "properties": {"resposta": {"type": "string", "enum": ["sim", "nao", "outro"]}},
    "required": ["resposta"],
}
PROMPT_CONFIRMACAO = """Um assistente de voz perguntou: "{pergunta}". Classifique a frase seguinte da pessoa.

sim: ela autoriza claramente, com quaisquer palavras.
nao: ela recusa, hesita, pede para esperar ou diz que ainda precisa daquilo.
outro: a frase não responde à pergunta e fala de outro assunto.

Na dúvida entre sim e nao, escolha nao.

Exemplos:
"com certeza" -> {{"resposta": "sim"}}
"vai em frente" -> {{"resposta": "sim"}}
"fecha sim" -> {{"resposta": "sim"}}
"manda bala" -> {{"resposta": "sim"}}
"exatamente" -> {{"resposta": "sim"}}
"faça isso, por gentileza" -> {{"resposta": "sim"}}
"negativo" -> {{"resposta": "nao"}}
"peraí" -> {{"resposta": "nao"}}
"ainda estou usando" -> {{"resposta": "nao"}}
"esquece" -> {{"resposta": "nao"}}
"quanto é dez vezes dez" -> {{"resposta": "outro"}}
"abre a calculadora" -> {{"resposta": "outro"}}"""


# ==========================================
# ATIVAR / DESATIVAR
# ==========================================
def ativar():
    global ultima_atividade
    ultima_atividade = time.time()
    if not ativo.is_set():
        ativo.set()
        fila_ui.put(("mostrar", None))


def desativar():
    global acao_pendente
    acao_pendente = None  # ao sair, nenhuma pergunta continua valendo
    ativo.clear()
    fila_ui.put(("esconder", None))


# ==========================================
# PROCESSAR COMANDO (ENVIAR PARA A IA)
# ==========================================
def limpar_comando(frase):
    frase = frase.lower()
    for p in PALAVRAS_ATIVACAO:
        frase = frase.replace(p, "")
    return frase.strip(" ,.!?")


def classificar_intencao(comando):
    """Retorna (intenção, alvo); em pesquisar_web, o alvo é o termo a pesquisar. Resposta inválida vira "conversar"."""
    resposta = ollama.chat(
        model=MODELO_IA,
        messages=[
            {"role": "system", "content": PROMPT_INTENCAO},
            {"role": "user", "content": comando},
        ],
        format=ESQUEMA_INTENCAO,
        options={"temperature": 0},
    )
    try:
        dados = json.loads(resposta["message"]["content"])
        intencao = dados.get("intencao", "conversar")
        alvo = str(dados.get("alvo", "")).strip()
        busca = str(dados.get("busca", "")).strip()
    except (ValueError, AttributeError):
        return "conversar", ""
    sobre_merlin = alvo.lower() == "merlin"
    if intencao == "fechar_programa" and _normalizar(alvo) in ALVOS_JANELA_DO_MERLIN:
        return "dispensar", "merlin"  # "fecha essa janela" sem citar nada: é a janela dele
    if intencao in ("dispensar", "encerrar") and not sobre_merlin:
        return "conversar", alvo
    if intencao == "fechar_programa" and sobre_merlin:
        return "dispensar", alvo
    if intencao == "abrir_programa" and (sobre_merlin or not alvo):
        return "conversar", alvo
    if intencao == "pesquisar_web":
        return intencao, busca or comando
    return intencao, alvo


def classificar_confirmacao(pergunta, comando):
    """Retorna "sim", "nao" ou "outro". Se a resposta vier inválida, nada é autorizado."""
    resposta = ollama.chat(
        model=MODELO_IA,
        messages=[
            {"role": "system", "content": PROMPT_CONFIRMACAO.format(pergunta=pergunta)},
            {"role": "user", "content": comando},
        ],
        format=ESQUEMA_CONFIRMACAO,
        options={"temperature": 0},
    )
    try:
        return json.loads(resposta["message"]["content"]).get("resposta", "outro")
    except (ValueError, AttributeError):
        return "outro"


SAUDACOES_RESERVA = [
    "Saudações. Eu sou Merlin, mago e conselheiro, sempre disposto a ajudar. O que deseja?",
    "Aqui estou. Sou Merlin, seu mago conselheiro. Em que posso ajudar hoje?",
    "Você chamou, e Merlin atendeu. Que conselho ou feitiço posso oferecer?",
    "Merlin a seu dispor, com magia e bons conselhos. O que traz você até mim?",
    "Os astros anunciaram seu chamado. Sou Merlin, seu conselheiro. Como posso ajudar?",
]
TEMAS_SAUDACAO = [
    "as estrelas", "a lua", "um velho grimório", "o cajado", "uma poção no caldeirão", "a coruja sábia",
    "a torre do mago", "uma vela acesa", "a floresta encantada", "a bola de cristal", "um pergaminho antigo", "o vento",
]
saudacoes_recentes = []


def _saudacao_valida(texto):
    """O modelo às vezes devolve lixo, e a saudação é lida em voz alta sem passar por mais nada."""
    tem_formato_estranho = any(c in texto for c in '{}[]<>*#_`"')
    return 20 <= len(texto) <= 170 and not tem_formato_estranho and "merlin" in texto.lower() and texto[-1] in ".?!"


def gerar_saudacao():
    """Cria uma saudação diferente a cada ativação; sem o Ollama ou com texto inválido, usa uma frase de reserva."""
    evitar = "\n".join(f"- {s}" for s in saudacoes_recentes) or "- nenhuma"
    texto = ""
    try:
        resposta = ollama.chat(
            model=MODELO_IA,
            messages=[{
                "role": "user",
                "content": f"Você é {NOME}, um mago conselheiro sábio e acolhedor, sempre disposto a ajudar. Alguém acaba de "
                           "chamar você. Escreva uma saudação falada em português do Brasil correto e natural, com duas "
                           f"frases curtas. Comece com uma imagem ligada a este tema: {random.choice(TEMAS_SAUDACAO)}. "
                           "Na mesma fala, diga que você é Merlin e ofereça conselho ou ajuda. "
                           "Não comece com o seu nome. Responda só com a saudação, sem aspas, emojis ou formatação. "
                           f"Não repita as saudações recentes:\n{evitar}",
            }],
            options={"temperature": 0.8, "num_predict": 70},
        )
        texto = (resposta["message"]["content"] or "").strip()
    except Exception as e:
        print(f"[SAUDAÇÃO] {e}")
    if not _saudacao_valida(texto) or texto in saudacoes_recentes:
        texto = random.choice([s for s in SAUDACOES_RESERVA if s not in saudacoes_recentes])
    saudacoes_recentes.append(texto)
    del saudacoes_recentes[:-3]  # guarda só as 3 últimas, para sempre sobrar uma frase de reserva
    return texto


def consultar_ia(comando):
    return ollama.chat(
        model=MODELO_IA,
        messages=[
            {
                "role": "system",
                "content": f"Você é o {NOME}, um assistente pessoal por voz. Responda de forma curta, educada e direta "
                           "em português do Brasil, em frases simples que soem bem faladas (sem markdown, listas ou emojis). "
                           "Nesta conversa você só responde: não abre, fecha nem controla nada. "
                           "Nunca diga que fez ou vai fazer uma ação; se pedirem uma, diga que não consegue fazer isso.",
            },
            {"role": "user", "content": comando},
        ],
    )


def processar_comando(frase):
    ativou_agora = False
    tem_chave = any(p in frase for p in PALAVRAS_ATIVACAO)
    if not ativo.is_set():
        if not tem_chave:
            return
        ativar()
        ativou_agora = True

    comando = limpar_comando(frase)
    fila_ui.put(("estado", "pensando"))

    # Qualquer frase depois da pergunta encerra a espera: só um "sim" claro fecha o programa
    pendente = pegar_pendente()

    if not comando:
        falar(gerar_saudacao() if ativou_agora else "Pois não?")
        return

    try:
        if pendente:
            decisao = classificar_confirmacao(f"Posso fechar {pendente['descricao']}?", comando)
            print(f"[CONFIRMAÇÃO]: {decisao}")
            if decisao == "sim":
                confirmar_fechamento(pendente)
                return
            if decisao == "nao":
                falar("Tudo bem, não vou fechar.")
                return
        intencao, alvo = classificar_intencao(comando)
        print(f"[INTENÇÃO]: {intencao} (alvo: {alvo})")
        if intencao == "encerrar":
            falar("Encerrando todos os sistemas. Até logo.")
            encerrar_programa.set()
            return
        if intencao == "dispensar":
            falar("Até mais. Estarei por aqui se precisar.")
            desativar()
            return
        if intencao == "fechar_programa":
            print(f"[LOG]: {executar_fechar_programa(alvo)}")
            return
        if intencao == "abrir_programa":
            print(f"[LOG]: {executar_abrir_programa(alvo)}")
            return
        if intencao == "pesquisar_web":
            print(f"[LOG]: {executar_pesquisa_web(alvo)}")
            return
        texto = consultar_ia(comando).get("message", {}).get("content")
    except Exception as e:
        print(f"[IA] Erro: {e}")
        falar("Não consegui falar com o meu cérebro. Verifique se o Ollama está rodando.")
        return

    falar(texto or "Desculpe, não entendi.")


def worker_comandos():
    while not encerrar_programa.is_set():
        try:
            frase = fila_comandos.get(timeout=0.5)
        except queue.Empty:
            # Auto-desativa após um tempo sem uso
            if ativo.is_set() and not falando.is_set() and time.time() - ultima_atividade > TEMPO_INATIVIDADE:
                print("[INFO] Inatividade, voltando ao modo de espera.")
                desativar()
            continue
        try:
            processar_comando(frase)
        except Exception as e:
            print(f"[ERRO] {e}")
        finally:
            # Garante que o olho não fique preso em "pensando" se nada foi falado
            if ativo.is_set() and not falando.is_set():
                fila_ui.put(("estado", "ouvindo"))


# ==========================================
# ESCUTA EM SEGUNDO PLANO (Ouvido Passivo)
# ==========================================
modelo_stt = None


def _volume(dados):
    amostras = np.frombuffer(dados, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(np.square(amostras)))) if amostras.size else 0.0


def calcular_nivel(dados, limiar):
    """Converte um trecho de áudio (16 bits) em um nível de 0 a 1; 0 = abaixo do limiar de voz."""
    if limiar <= 0:
        return 0.0
    razao = _volume(dados) / limiar
    if razao <= 1:
        return 0.0
    decibeis = 20 * math.log10(razao)  # decibéis acima do limiar de voz; 30 dB já é a onda máxima
    return min(1.0, 0.12 + 0.88 * decibeis / 30)


class DetectorInterrupcao:
    """Decide se a pessoa falou por cima do Merlin, comparando o som captado com o eco da própria voz dele."""

    APRENDIZADO = 0.5  # segundos iniciais só para medir o eco
    TOLERANCIA = 0.12  # pausas entre sílabas menores que isto não contam como silêncio
    QUEDA_DO_ECO = 0.998  # o eco medido baixa aos poucos, acompanhando trechos mais fracos da fala

    def __init__(self):
        self.reiniciar()

    def reiniciar(self):
        self.inicio = self.acima_desde = self.ultimo_acima = None
        self.eco = 0.0

    def analisar(self, volume, limiar, agora):
        if self.inicio is None:
            self.inicio = agora
        if agora - self.inicio < self.APRENDIZADO:
            self.eco = max(self.eco, volume)
            return False
        if volume > max(limiar * 1.5, self.eco * INTERROMPER_FATOR):
            if self.acima_desde is None:
                self.acima_desde = agora
            self.ultimo_acima = agora
            return agora - self.acima_desde >= INTERROMPER_DURACAO
        if self.acima_desde is not None and agora - self.ultimo_acima <= self.TOLERANCIA:
            return False  # pausa curta no meio da fala da pessoa
        self.acima_desde = None
        self.eco = max(volume, self.eco * self.QUEDA_DO_ECO)
        return False


class FluxoComMedidor:
    """Fica entre o microfone e o reconhecimento: mede o volume e, enquanto o Merlin fala, entrega silêncio."""

    def __init__(self, fluxo, recognizer):
        self.fluxo = fluxo
        self.recognizer = recognizer
        self.detector = DetectorInterrupcao()
        self.previa = deque(maxlen=64)  # áudio recente, para não perder o começo da frase que interrompeu
        self.atrasados = deque()
        self.inicio_da_voz = 0.0

    def _durante_a_fala(self, dados):
        # O limiar automático desabaria se recebesse silêncio artificial
        self.recognizer.dynamic_energy_threshold = False
        agora = time.time()
        self.previa.append((agora, dados))
        self.atrasados.clear()
        if not reproduzindo.is_set():
            self.detector.reiniciar()
        elif not interromper.is_set():
            if self.detector.analisar(_volume(dados), self.recognizer.energy_threshold, agora):
                print(f"[INFO] Voz por cima da fala (eco medido: {self.detector.eco:.0f}, som: {_volume(dados):.0f}).")
                self.inicio_da_voz = self.detector.acima_desde
                interromper.set()
        return bytes(len(dados))

    def read(self, tamanho):
        global nivel_voz
        dados = self.fluxo.read(tamanho)
        if falando.is_set():
            return self._durante_a_fala(dados)

        self.recognizer.dynamic_energy_threshold = True
        if self.previa:
            if interromper.is_set():
                # Só o que veio depois de a voz começar: o trecho anterior tem o eco do próprio Merlin
                self.atrasados.extend(d for t, d in self.previa if t >= self.inicio_da_voz)
                interromper.clear()
            self.previa.clear()
        if ativo.is_set():
            nivel_voz = max(nivel_voz, calcular_nivel(dados, self.recognizer.energy_threshold))
        if self.atrasados:
            self.atrasados.append(dados)
            return self.atrasados.popleft()
        return dados

    def close(self):
        self.fluxo.close()


class MicrofoneComMedidor(sr.Microphone):
    """O listen_in_background só avisa ao fim da frase; o medidor permite reagir enquanto a pessoa fala."""

    def __init__(self, recognizer):
        super().__init__()
        self.recognizer = recognizer

    def __enter__(self):
        super().__enter__()
        self.stream = FluxoComMedidor(self.stream, self.recognizer)
        return self


def transcrever(audio):
    """Reconhecimento de fala offline com faster-whisper."""
    global modelo_stt
    if modelo_stt is None:
        modelo_stt = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    bruto = audio.get_raw_data(convert_rate=16000, convert_width=2)
    amostras = np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0
    segmentos, _ = modelo_stt.transcribe(
        amostras, language="pt", beam_size=1, vad_filter=True,
        initial_prompt="Merlin, abra o navegador. Merlin, pesquise na internet.",
        condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segmentos if s.no_speech_prob < 0.6).strip().lower()


def callback_escuta(recognizer, audio):
    if ativo.is_set() and not falando.is_set():
        fila_ui.put(("estado", "pensando"))  # a frase terminou e está sendo transcrita
    try:
        frase = transcrever(audio)
        if frase:
            print(f"[OUVI]: {frase}")
            if ativo.is_set() or any(p in frase for p in PALAVRAS_ATIVACAO):
                fila_comandos.put(frase)
                return
    except Exception as e:
        print(f"Erro no reconhecimento: {e}")
    if ativo.is_set():
        fila_ui.put(("estado", "ouvindo"))  # era só ruído: volta a ouvir


# ==========================================
# JANELA COM O OLHO
# ==========================================
class ApiJanela:
    """Funções que a página da janela pode chamar."""

    def trocar_voz(self, rotulo):
        global voz_atual
        if rotulo not in VOZES:
            return
        voz_atual = VOZES[rotulo]
        config["voz"] = voz_atual
        salvar_config()
        threading.Thread(target=falar, args=("Olá, esta é a minha nova voz.",), daemon=True).start()


class JanelaMerlin:
    LARGURA, ALTURA = 680, 820

    def __init__(self):
        rotulo_atual = next((n for n, v in VOZES.items() if v == voz_atual), list(VOZES)[0])
        with open(ARQ_OLHO, encoding="utf-8") as f:
            olho = f.read()
        with open(ARQ_JANELA, encoding="utf-8") as f:
            pagina = f.read()
        pagina = pagina.replace("<!--OLHO-->", olho).replace(
            "/*DADOS*/", json.dumps({"vozes": list(VOZES), "atual": rotulo_atual}, ensure_ascii=False))

        # A posição vai na criação: janela.move() exibiria a janela escondida
        tela = webview.screens[0]
        largura = min(self.LARGURA, int(tela.width * 0.9))
        altura = min(self.ALTURA, int(tela.height * 0.88))
        x = tela.x + (tela.width - largura) // 2
        y = tela.y + (tela.height - altura) // 2

        self.visivel = False
        self.nivel = 0.0
        self.ultimo_nivel = 0.0
        self.janela = webview.create_window(
            NOME, html=pagina, js_api=ApiJanela(), width=largura, height=altura, x=x, y=y,
            resizable=False, on_top=True, hidden=True, background_color="#05070C",
        )
        self.janela.events.closing += self._ao_fechar

    def executar(self):
        """Bloqueia a thread principal até a janela ser destruída."""
        webview.start(self._loop_ui, gui="edgechromium")

    def _ao_fechar(self):
        # Fechar no X equivale a desativar (o programa segue escutando)
        if encerrar_programa.is_set():
            return True
        desativar()
        return False

    def _js(self, funcao, *args):
        self.janela.evaluate_js(f"{funcao}({', '.join(json.dumps(a) for a in args)})")

    def _atualizar_nivel(self):
        """Envia o volume à página cerca de 15 vezes por segundo, com queda suave para não piscar."""
        global nivel_voz
        agora = time.time()
        if not self.visivel or agora - self.ultimo_nivel < 0.066:
            return
        self.ultimo_nivel = agora
        captado, nivel_voz = nivel_voz, 0.0
        novo = max(captado, self.nivel * 0.8)
        if novo < 0.02:
            novo = 0.0
        if novo != self.nivel:
            self.nivel = novo
            self._js("definirNivel", round(novo, 2))

    def _loop_ui(self):
        self.janela.events.loaded.wait()
        while not encerrar_programa.is_set():
            try:
                tipo, dado = fila_ui.get(timeout=0.05)
            except queue.Empty:
                tipo, dado = None, None
            try:
                self._atualizar_nivel()
                if tipo == "mostrar":
                    self.visivel = True
                    self.nivel = 0.0
                    self._js("aoMostrar")
                    self.janela.show()
                elif tipo == "esconder":
                    self.visivel = False
                    self.janela.hide()
                elif tipo == "estado" and self.visivel:
                    self._js("definirEstado", dado)
                elif tipo == "legenda" and self.visivel:
                    self._js("definirLegenda", dado)
            except Exception as e:
                print(f"[JANELA] {e}")
        self.janela.destroy()


# ==========================================
# INICIALIZAÇÃO
# ==========================================
def iniciar_audio():
    r = sr.Recognizer()
    m = MicrofoneComMedidor(r)
    with m as source:
        print("Calibrando o ruído ambiente...")
        r.adjust_for_ambient_noise(source, duration=2)
    print("Carregando modelos offline...")
    transcrever(sr.AudioData(b"\x00\x00" * 16000, 16000, 2))  # pré-carrega o Whisper
    _obter_voz(_modelo_da_voz(voz_atual))
    print(f"{NOME} em modo de espera. Diga '{PALAVRAS_ATIVACAO[0]}' para ativar.")
    threading.Thread(target=worker_comandos, daemon=True).start()
    r.listen_in_background(m, callback_escuta, phrase_time_limit=8)


def main():
    janela = JanelaMerlin()
    threading.Thread(target=iniciar_audio, daemon=True).start()
    janela.executar()
    os._exit(0)


if __name__ == "__main__":
    main()
