import json
import math
import os
import queue
import random
import tempfile
import threading
import time
import tkinter as tk
import wave
from tkinter import ttk
from urllib.parse import quote_plus

# 100% offline: depois que os modelos estão baixados, nada acessa a internet.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import numpy as np
import ollama
import pygame
import speech_recognition as sr
from AppOpener import open as abrir_app
from faster_whisper import WhisperModel
from piper import PiperVoice

# ==========================================
# CONFIGURAÇÕES
# ==========================================
NOME = "Merlin"
PALAVRAS_ATIVACAO = ["merlin", "merlim", "melim", "merlyn", "melinho", "marlin", "berlim"]  # variações que o Whisper costuma ouvir
FRASES_DESATIVAR = ["desativar", "pode dormir", "dispensado", "até mais", "tchau", "fechar janela"]
FRASES_ENCERRAR = ["encerrar", "desligar completamente", "fechar o merlin"]
TEMPO_INATIVIDADE = 30  # segundos sem comandos -> volta ao modo de espera sozinho
MODELO_IA = "qwen2.5:7b"
MODELO_WHISPER = "small"  # "base" é mais rápido; "medium" é mais preciso

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_VOZES = os.path.join(PASTA, "vozes")
ARQ_CONFIG = os.path.join(PASTA, "merlin_config.json")

# Vozes neurais OFFLINE (Piper). Os arquivos .onnx ficam na pasta "vozes".
VOZES = {
    "Faber (masculina)": "pt_BR-faber-medium",
    "Cadu (masculina)": "pt_BR-cadu-medium",
    "Jeff (masculina)": "pt_BR-jeff-medium",
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
fila_ui = queue.Queue()        # mensagens para a janela (a UI só roda na thread principal)
fila_comandos = queue.Queue()  # frases reconhecidas para o worker processar
ativo = threading.Event()      # Merlin ativado?
falando = threading.Event()    # evita que ele escute a própria voz
ultima_atividade = time.time()
encerrar_programa = threading.Event()

pygame.mixer.init()


# ==========================================
# VOZ (TTS offline com Piper)
# ==========================================
_vozes_carregadas = {}


def _obter_voz(nome):
    if nome not in _vozes_carregadas:
        _vozes_carregadas[nome] = PiperVoice.load(os.path.join(PASTA_VOZES, nome + ".onnx"))
    return _vozes_carregadas[nome]


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
    falando.set()
    arquivo = os.path.join(tempfile.gettempdir(), f"merlin_{os.getpid()}_{time.time_ns()}.wav")
    try:
        with wave.open(arquivo, "wb") as w:
            _obter_voz(voz_atual).synthesize_wav(texto, w)
        pygame.mixer.music.load(arquivo)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"[TTS] Piper falhou ({e}); usando voz do Windows.")
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
def executar_abrir_programa(nome_programa):
    try:
        falar(f"Abrindo {nome_programa}.")
        abrir_app(nome_programa, match_closest=True)
        return f"Sucesso: {nome_programa} foi aberto."
    except Exception as e:
        falar(f"Não consegui abrir {nome_programa}.")
        return f"Erro ao abrir {nome_programa}: {e}"


def executar_pesquisa_web(termo):
    falar(f"Pesquisando por {termo}.")
    if termo.startswith("http") or ".com" in termo:
        url = termo if termo.startswith("http") else f"https://{termo}"
    else:
        url = f"https://www.google.com/search?q={quote_plus(termo)}"
    os.startfile(url)
    return f"Sucesso: Pesquisa por '{termo}' realizada."


funcoes_sistema = {
    "executar_abrir_programa": executar_abrir_programa,
    "executar_pesquisa_web": executar_pesquisa_web,
}

ferramentas = [
    {
        "type": "function",
        "function": {
            "name": "executar_abrir_programa",
            "description": "Use para abrir programas instalados no PC (ex: chrome, spotify, notepad, calc).",
            "parameters": {
                "type": "object",
                "properties": {"nome_programa": {"type": "string", "description": "O nome do aplicativo."}},
                "required": ["nome_programa"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "executar_pesquisa_web",
            "description": "Use para pesquisar na internet ou abrir sites específicos.",
            "parameters": {
                "type": "object",
                "properties": {"termo": {"type": "string", "description": "O termo de busca ou URL."}},
                "required": ["termo"],
            },
        },
    },
]


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

    if not comando:
        falar("Sim? Como posso ajudar?" if ativou_agora else "Pois não?")
        return

    if any(f in comando for f in FRASES_ENCERRAR):
        falar("Encerrando todos os sistemas. Até logo.")
        encerrar_programa.set()
        return

    if any(f in comando for f in FRASES_DESATIVAR):
        falar("Até mais. Estarei por aqui se precisar.")
        desativar()
        return

    try:
        resposta = ollama.chat(
            model=MODELO_IA,
            messages=[
                {
                    "role": "system",
                    "content": f"Você é o {NOME}, um assistente pessoal por voz. Responda de forma curta, educada e direta "
                               "em português do Brasil, em frases simples que soem bem faladas (sem markdown, listas ou emojis). "
                               "Use as ferramentas imediatamente quando solicitado.",
                },
                {"role": "user", "content": comando},
            ],
            tools=ferramentas,
        )
    except Exception as e:
        print(f"[IA] Erro: {e}")
        falar("Não consegui falar com o meu cérebro. Verifique se o Ollama está rodando.")
        return

    msg = resposta.get("message", {})
    if msg.get("tool_calls"):
        for tool in msg["tool_calls"]:
            nome = tool["function"]["name"]
            args = tool["function"]["arguments"]
            if nome in funcoes_sistema:
                print(f"[LOG]: {funcoes_sistema[nome](**args)}")
    elif msg.get("content"):
        falar(msg["content"])
    else:
        falar("Desculpe, não entendi.")


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


# ==========================================
# ESCUTA EM SEGUNDO PLANO (Ouvido Passivo)
# ==========================================
modelo_stt = None


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
    if falando.is_set():
        return  # não processa o que ele mesmo está falando
    try:
        frase = transcrever(audio)
        if not frase:
            return
        print(f"[OUVI]: {frase}")
        if ativo.is_set() or any(p in frase for p in PALAVRAS_ATIVACAO):
            fila_comandos.put(frase)
    except Exception as e:
        print(f"Erro no reconhecimento: {e}")


# ==========================================
# JANELA COM O OLHO
# ==========================================
class JanelaMerlin:
    LARGURA, ALTURA = 420, 520
    CORES = {  # cor da íris por estado
        "espera": "#3b4a6b",
        "ouvindo": "#2ec4ff",
        "pensando": "#ffb020",
        "falando": "#7CFFB2",
    }

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(NOME)
        self.root.configure(bg="#0a0d14")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._fechar_manual)
        x = self.root.winfo_screenwidth() - self.LARGURA - 30
        self.root.geometry(f"{self.LARGURA}x{self.ALTURA}+{x}+40")

        tk.Label(self.root, text=NOME.upper(), fg="#9fb4d9", bg="#0a0d14",
                 font=("Segoe UI", 16, "bold")).pack(pady=(14, 0))

        self.canvas = tk.Canvas(self.root, width=self.LARGURA, height=300, bg="#0a0d14", highlightthickness=0)
        self.canvas.pack()

        self.legenda = tk.Label(self.root, text="", fg="#d6e2ff", bg="#0a0d14", wraplength=self.LARGURA - 40,
                                font=("Segoe UI", 11), height=4, justify="center")
        self.legenda.pack(pady=4)

        # Seletor de voz
        quadro = tk.Frame(self.root, bg="#0a0d14")
        quadro.pack(pady=6)
        tk.Label(quadro, text="Voz:", fg="#9fb4d9", bg="#0a0d14", font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
        self.var_voz = tk.StringVar()
        nome_atual = next((n for n, v in VOZES.items() if v == voz_atual), list(VOZES)[0])
        self.var_voz.set(nome_atual)
        combo = ttk.Combobox(quadro, textvariable=self.var_voz, values=list(VOZES), state="readonly", width=26)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._trocar_voz)

        self.estado = "espera"
        self.t = 0.0
        self.olhar_x = self.olhar_y = 0.0
        self.alvo_x = self.alvo_y = 0.0
        self.proximo_olhar = 0.0
        self.piscada = 0.0       # 0 = aberto, 1 = fechado
        self.proxima_piscada = 2.0
        self.abertura = 0.0      # animação de abrir o olho ao ativar
        self.visivel = False

        self.root.withdraw()
        self.root.after(33, self._tick)

    # --- eventos ---
    def _trocar_voz(self, _evento=None):
        global voz_atual
        voz_atual = VOZES[self.var_voz.get()]
        config["voz"] = voz_atual
        salvar_config()
        threading.Thread(target=falar, args=(f"Olá, esta é a minha nova voz.",), daemon=True).start()

    def _fechar_manual(self):
        # Fechar no X equivale a desativar (o programa segue escutando)
        desativar()

    def _mostrar(self):
        self.abertura = 0.0
        self.visivel = True
        self.legenda.config(text="")
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)

    def _esconder(self):
        self.visivel = False
        self.estado = "espera"
        self.root.withdraw()

    # --- loop principal da UI ---
    def _tick(self):
        try:
            while True:
                tipo, dado = fila_ui.get_nowait()
                if tipo == "mostrar":
                    self._mostrar()
                    self.estado = "ouvindo"
                elif tipo == "esconder":
                    self._esconder()
                elif tipo == "estado" and self.visivel:
                    self.estado = dado
                elif tipo == "legenda" and self.visivel:
                    self.legenda.config(text=dado)
        except queue.Empty:
            pass

        if encerrar_programa.is_set():
            self.root.destroy()
            return

        if self.visivel:
            self._desenhar()
        self.root.after(33, self._tick)

    def _desenhar(self):
        dt = 0.033
        self.t += dt
        c = self.canvas
        c.delete("all")
        cx, cy = self.LARGURA / 2, 150

        self.abertura = min(1.0, self.abertura + dt * 2.5)

        # Movimento do olhar
        if self.t >= self.proximo_olhar:
            self.alvo_x = random.uniform(-1, 1) if self.estado != "falando" else random.uniform(-0.3, 0.3)
            self.alvo_y = random.uniform(-0.6, 0.6)
            self.proximo_olhar = self.t + random.uniform(0.8, 2.5)
        self.olhar_x += (self.alvo_x - self.olhar_x) * 0.15
        self.olhar_y += (self.alvo_y - self.olhar_y) * 0.15

        # Piscada
        if self.t >= self.proxima_piscada:
            self.piscada = min(1.0, self.piscada + dt * 12)
            if self.piscada >= 1.0:
                self.proxima_piscada = self.t + random.uniform(2.0, 5.0)
                self.piscada = 0.999
        elif self.piscada > 0:
            self.piscada = max(0.0, self.piscada - dt * 12)

        cor = self.CORES.get(self.estado, self.CORES["ouvindo"])
        pulso = 0.5 + 0.5 * math.sin(self.t * (7 if self.estado == "falando" else 3))

        # Brilho (halo)
        for i in range(6, 0, -1):
            r = 125 + i * 7 + pulso * 6
            c.create_oval(cx - r * 1.35, cy - r * 0.7, cx + r * 1.35, cy + r * 0.7,
                          outline=cor, width=1, stipple="gray25" if i > 2 else "")

        # Olho: altura depende da abertura e da piscada
        aberto = self.abertura * (1 - self.piscada)
        largura = 150
        altura = max(2, 80 * aberto)
        c.create_oval(cx - largura, cy - altura, cx + largura, cy + altura,
                      fill="#e8eefc", outline=cor, width=3)

        # Íris e pupila (clipadas visualmente pela altura)
        if aberto > 0.15:
            ix = cx + self.olhar_x * 55
            iy = cy + self.olhar_y * 20 * aberto
            ri = min(52, altura - 4) if altura < 56 else 52
            c.create_oval(ix - ri, iy - ri, ix + ri, iy + ri, fill=cor, outline="#0a0d14", width=2)
            rp = ri * (0.45 + 0.1 * pulso if self.estado in ("falando", "pensando") else 0.45)
            c.create_oval(ix - rp, iy - rp, ix + rp, iy + rp, fill="#05070c", outline="")
            c.create_oval(ix - ri * 0.45, iy - ri * 0.6, ix - ri * 0.2, iy - ri * 0.35, fill="#ffffff", outline="")

        # Pálpebras (contorno)
        c.create_arc(cx - largura, cy - altura, cx + largura, cy + altura, start=0, extent=180,
                     style="arc", outline=cor, width=4)


# ==========================================
# INICIALIZAÇÃO
# ==========================================
def iniciar_audio(janela):
    r = sr.Recognizer()
    m = sr.Microphone()
    with m as source:
        print("Calibrando o ruído ambiente...")
        r.adjust_for_ambient_noise(source, duration=2)
    print("Carregando modelos offline...")
    transcrever(sr.AudioData(b"\x00\x00" * 16000, 16000, 2))  # pré-carrega o Whisper
    _obter_voz(voz_atual)
    print(f"{NOME} em modo de espera. Diga '{PALAVRAS_ATIVACAO[0]}' para ativar.")
    threading.Thread(target=worker_comandos, daemon=True).start()
    r.listen_in_background(m, callback_escuta, phrase_time_limit=8)


def main():
    janela = JanelaMerlin()
    threading.Thread(target=iniciar_audio, args=(janela,), daemon=True).start()
    janela.root.mainloop()
    os._exit(0)


if __name__ == "__main__":
    main()
