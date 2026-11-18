"""Aba Visão da Central: detecção de fogo em imagens, vídeos e na câmera, com o FireWatch AI (YOLO12n treinado).

Tudo roda neste computador. As imagens não são guardadas; os vídeos analisados (com as caixas desenhadas) ficam
em dados/visao/. O modelo só é carregado quando a aba é aberta pela primeira vez.
"""
import base64
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from merlin.config import PASTA_EXEMPLOS_VISAO, PASTA_VISAO

logger = logging.getLogger(__name__)

TIPOS_IMAGEM = ("Imagens (*.jpg;*.jpeg;*.png;*.webp;*.bmp)",)
TIPOS_VIDEO = ("Vídeos (*.mp4;*.avi;*.mov;*.mkv;*.wmv)",)
LADO_MAXIMO = 1280  # a imagem anotada vai para a página reduzida a este tamanho: a original pode ter 20 MP
QUALIDADE_JPEG = 85
MAX_BYTES_IMAGEM = 25 * 1024 * 1024  # imagem arrastada para a página
QUADROS_DE_AQUECIMENTO = 5  # as webcams entregam as primeiras imagens escuras ou fora de foco
ESPERA_IMAGEM = 60  # segundos que uma imagem espera a anterior terminar (a primeira também carrega o modelo)

AVISO_OCUPADO = "Um vídeo está sendo analisado. Aguarde terminar ou cancele."
AVISO_SEM_CAMERA = "Não encontrei uma câmera neste computador, ou ela está sendo usada por outro programa."
AVISO_IMAGEM_INVALIDA = "Não consegui abrir esta imagem. Use JPG, PNG, WEBP ou BMP."
# O aviso do pacote ("Emergência: Corpo de Bombeiros 193 / Defesa Civil 199") é para o público em geral. Quem usa
# a aba é um agente da Defesa Civil fazendo triagem: o que ele precisa saber é quando a detecção pode errar.
AVISO_DETECCAO = ("Detecção automática de apoio à triagem. Pode haver falsos positivos (tons quentes, como madeira, "
                  "pele ou lareira) e falsos negativos: confirme visualmente antes de registrar a ocorrência ou "
                  "mobilizar equipes.")
# O codificador H.264 do Windows ignora o ajuste de qualidade (~23 Mbps fixos): em 720p, 25 s davam 78 MB.
# Em 640 px de largura são ~6 Mbps, o bastante para o quadro da aba, e o modelo analisa em 640 px de qualquer jeito
LARGURA_VIDEO = 640
PEDACO_VIDEO = 2 * 1024 * 1024
# Muda quando o laço do vídeo muda de um jeito que altera o resultado: os vídeos já analisados deixam de valer
VERSAO_DO_LACO = 1
BLOCO_HASH = 4 * 1024 * 1024  # o vídeo vai para a página em pedaços, pela ponte da Central (sem abrir porta de rede)


@dataclass(frozen=True)
class Exemplo:
    arquivo: str
    titulo: str
    descricao: str
    tipo: str  # "video" ou "imagem"
    sha256: str  # confere o download (ferramentas/baixar_modelos.py)


# Da pasta Teste/ do repositório do FireWatch AI (GS2-ACV), fixados num commit: os arquivos não mudam por baixo.
# Não vêm no repositório do Merlin (~30 MB de vídeo): ferramentas/baixar_modelos.py os baixa para modelos/.
ORIGEM_EXEMPLOS = ("https://raw.githubusercontent.com/JBVJoaoV/GS2-ACV/"
                   "6215e5629d08b71daf7a7e7ffa2e8d29539e91bb/Teste/")
EXEMPLOS = (
    Exemplo("video2.mp4", "Casa em chamas", "Vídeo, 25 s · incêndio em edificação", "video",
            "2dc484d858c7dcc4d440d895189c7f8572519dbafa7c1223afa2179fc68c7f72"),
    Exemplo("video3.mp4", "Incêndio industrial", "Vídeo, 30 s · pilhas de material em chamas", "video",
            "3a82a1d5a10d79889050c2230e246ee25af7732832400e60a72e01c2c8395ecd"),
    Exemplo("video1.mp4", "Lareira acesa", "Vídeo, 20 s · fogo controlado: o modelo também marca", "video",
            "24b39eb80073e976988573a54d2315087e66d813359159d8a6153b0202484d96"),
    Exemplo("images.jpg", "Prédio em chamas", "Imagem · bombeiros em combate", "imagem",
            "6e61755312c8a680193c70a8140735c2099b32d9b4668a0d11e70e35af0cadb6"),
    Exemplo("images (1).jpg", "Incêndio florestal", "Imagem · fogo às margens da estrada", "imagem",
            "b17c73a415f998f93a615d40cccdfe6e7b9f5d2f3a132f7ce7ce64eb64af1a8e"),
)
LARGURA_MINIATURA = 160


def _miniatura(caminho: Path, tipo: str) -> str:
    """Um quadro do meio do vídeo (ou a própria imagem), pequeno, para o botão do exemplo."""
    import cv2
    if tipo == "video":
        captura = cv2.VideoCapture(str(caminho))
        try:
            captura.set(cv2.CAP_PROP_POS_FRAMES, int(captura.get(cv2.CAP_PROP_FRAME_COUNT)) // 2)
            ok, imagem = captura.read()
        finally:
            captura.release()
        if not ok:
            return ""
    else:
        imagem = _ler_imagem(caminho.read_bytes())
    altura, largura = imagem.shape[:2]
    imagem = cv2.resize(imagem, (LARGURA_MINIATURA, round(altura * LARGURA_MINIATURA / largura)),
                        interpolation=cv2.INTER_AREA)
    return "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", imagem)[1].tobytes()).decode("ascii")


def _carregar_detector():
    from firewatch_ai import FireWatchAI  # importa o torch e o Ultralytics: só quando a aba é usada
    return FireWatchAI()


def _ler_imagem(dados: bytes):
    """Bytes de uma imagem -> matriz BGR. Lê pelos bytes porque o cv2.imread não abre caminhos com acento no Windows."""
    import cv2
    import numpy as np
    imagem = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise ValueError(AVISO_IMAGEM_INVALIDA)
    return imagem


def _para_pagina(imagem) -> str:
    """Matriz BGR -> data URL JPEG, reduzida para caber na tela sem pesar na ponte com a página."""
    import cv2
    altura, largura = imagem.shape[:2]
    escala = min(1.0, LADO_MAXIMO / max(altura, largura))
    if escala < 1:
        imagem = cv2.resize(imagem, (round(largura * escala), round(altura * escala)), interpolation=cv2.INTER_AREA)
    ok, jpeg = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG])
    if not ok:
        raise RuntimeError("Não consegui preparar a imagem anotada.")
    return "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode("ascii")


def _foto_da_camera(indice: int = 0):
    import cv2
    camera = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
    try:
        if not camera.isOpened():
            raise RuntimeError(AVISO_SEM_CAMERA)
        imagem = None
        for _ in range(QUADROS_DE_AQUECIMENTO):
            ok, quadro = camera.read()
            if ok:
                imagem = quadro
        if imagem is None:
            raise RuntimeError(AVISO_SEM_CAMERA)
        return imagem
    finally:
        camera.release()


class Cancelado(Exception):
    """Levantada dentro do aviso de progresso para interromper o vídeo."""


class SemH264(Exception):
    """O OpenCV desta máquina não grava H.264: o vídeo é feito pelo pacote, em mp4v, e abre fora da Central."""


def processar_video_h264(detector, entrada: Path, saida: Path, progresso) -> dict:
    """O mesmo que o FireWatchAI.processar_video, mas gravando em H.264 (avc1). O pacote grava em mp4v, que o
    navegador da Central (WebView2) não toca; em H.264 o vídeo analisado toca na própria aba Visão."""
    import cv2
    captura = cv2.VideoCapture(str(entrada))
    if not captura.isOpened():
        raise RuntimeError(f"Não foi possível abrir o vídeo: {entrada.name}")
    fps = captura.get(cv2.CAP_PROP_FPS) or 25.0
    largura_original, altura_original = int(captura.get(cv2.CAP_PROP_FRAME_WIDTH)), int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
    if largura_original <= 0 or altura_original <= 0:
        captura.release()
        raise RuntimeError("Não foi possível identificar a resolução do vídeo.")
    # Reduz antes de analisar: as caixas e os rótulos já saem no tamanho final. O H.264 exige medidas pares.
    escala = min(1.0, LARGURA_VIDEO / largura_original)
    largura = round(largura_original * escala / 2) * 2
    altura = round(altura_original * escala / 2) * 2
    # Direto pelo Media Foundation, o codificador H.264 do próprio Windows: o FFmpeg do OpenCV não traz o
    # libopenh264, e tentar por ele primeiro só deixava erros no terminal antes de cair no Media Foundation
    escritor = cv2.VideoWriter(str(saida), cv2.CAP_MSMF, cv2.VideoWriter_fourcc(*"avc1"), fps, (largura, altura))
    if not escritor.isOpened():
        captura.release()
        saida.unlink(missing_ok=True)
        raise SemH264()
    # Uma passada do modelo por quadro: _prever devolve as caixas e a imagem desenhada juntas. Sem ele (outra
    # versão do pacote), detectar + anotar dão o mesmo resultado com duas passadas.
    prever = getattr(detector, "_prever", None)
    quadros, com_fogo, maior = 0, [], 0.0
    try:
        while True:
            ok, quadro = captura.read()
            if not ok:
                break
            if quadro.shape[1] != largura or quadro.shape[0] != altura:
                quadro = cv2.resize(quadro, (largura, altura), interpolation=cv2.INTER_AREA)
            if prever:
                resultado = prever(quadro)
                confiancas = [float(c) for c in resultado.boxes.conf] if len(resultado.boxes) else []
                anotado = resultado.plot()
            else:
                confiancas = [d["confianca"] for d in detector.detectar(quadro)["deteccoes"]]
                anotado = detector.anotar(quadro)
            if confiancas:
                com_fogo.append(quadros)
                maior = max(maior, *confiancas)
            if anotado.shape[1] != largura or anotado.shape[0] != altura:
                anotado = cv2.resize(anotado, (largura, altura))
            escritor.write(anotado)
            quadros += 1
            progresso(quadros, total)
    finally:
        captura.release()
        escritor.release()
    return {"status": "fogo_detectado" if com_fogo else "sem_fogo", "frames_processados": quadros,
            "frames_com_fogo": len(com_fogo), "primeiro_segundo_com_fogo": round(com_fogo[0] / fps, 2) if com_fogo else None,
            "maior_confianca": round(maior, 4), "fps": round(fps, 2), "aviso": AVISO_DETECCAO}


class ServicoVisao:
    def __init__(self, carregar=_carregar_detector, pasta=PASTA_VISAO, abrir=None, camera=_foto_da_camera,
                 pasta_exemplos=PASTA_EXEMPLOS_VISAO, exemplos=EXEMPLOS, processar_video=processar_video_h264):
        """processar_video: o laço que grava em H.264 (toca na aba). None usa o do pacote (mp4v, abre fora)."""
        self._processar_video = processar_video
        self._carregar = carregar
        self._pasta = Path(pasta)
        self._pasta_exemplos = Path(pasta_exemplos)
        self._exemplos = {e.arquivo: e for e in exemplos}
        self._miniaturas: dict[str, str] = {}
        self._abrir = abrir or os.startfile  # abre o vídeo ou a pasta no programa padrão do Windows
        self._camera = camera
        self._detector = None
        self._erro = ""
        self._carregando = False
        self._trava_carga = threading.Lock()
        self._trava_uso = threading.Lock()  # o Ultralytics não é feito para duas análises ao mesmo tempo
        self._video = {"estado": "parado"}
        self._cancelar = threading.Event()

    # --- modelo
    def estado(self) -> dict:
        return {"pronto": self._detector is not None, "carregando": self._carregando, "erro": self._erro,
                "limiar": getattr(self._detector, "confianca", None)}

    def preparar(self) -> dict:
        """Carrega o modelo em segundo plano (a página chama ao abrir a aba)."""
        if self._detector is None and not self._carregando:
            self._carregando = True
            threading.Thread(target=self._obter, name="carregar-visao", daemon=True).start()
        return self.estado()

    def _obter(self):
        with self._trava_carga:
            if self._detector is None:
                try:
                    inicio = time.perf_counter()
                    self._detector = self._carregar()
                    self._erro = ""
                    logger.info("[VISÃO] Modelo carregado em %.1f s.", time.perf_counter() - inicio)
                except Exception as erro:
                    logger.error("[VISÃO] Não consegui carregar o modelo: %s", erro)
                    self._erro = f"Não consegui carregar o modelo de visão: {erro}"
                finally:
                    self._carregando = False
            if self._detector is None:
                raise RuntimeError(self._erro)
            return self._detector

    # --- imagens
    def analisar_arquivo(self, caminho: str) -> dict:
        try:
            dados = Path(caminho).read_bytes()
        except OSError as erro:
            return {"erro": f"Não consegui ler o arquivo: {erro}"}
        return self._analisar(lambda: _ler_imagem(dados), Path(caminho).name)

    def analisar_dados(self, dados_base64: str, nome: str = "imagem") -> dict:
        """Imagem arrastada para a página, em base64 (com ou sem o prefixo data:)."""
        try:
            dados = base64.b64decode(str(dados_base64).split(",", 1)[-1], validate=True)
        except ValueError:
            return {"erro": AVISO_IMAGEM_INVALIDA}
        if len(dados) > MAX_BYTES_IMAGEM:
            return {"erro": f"A imagem passa de {MAX_BYTES_IMAGEM // (1024 * 1024)} MB."}
        return self._analisar(lambda: _ler_imagem(dados), str(nome or "imagem")[:120])

    def analisar_camera(self) -> dict:
        return self._analisar(self._camera, "Foto da câmera")

    def _analisar(self, obter_imagem, origem: str) -> dict:
        # Uma imagem espera a anterior (são milissegundos); durante um vídeo, que pode levar minutos, ela é recusada
        if self._video.get("estado") == "analisando" or not self._trava_uso.acquire(timeout=ESPERA_IMAGEM):
            return {"erro": AVISO_OCUPADO}
        try:
            detector = self._obter()
            imagem = obter_imagem()
            inicio = time.perf_counter()
            r = detector.detectar(imagem)
            anotada = detector.anotar(imagem)
            milissegundos = round((time.perf_counter() - inicio) * 1000)
        except (ValueError, RuntimeError) as erro:
            return {"erro": str(erro)}
        except Exception as erro:
            logger.error("[VISÃO] Falhou ao analisar %s: %s", origem, erro)
            return {"erro": f"A análise falhou: {erro}"}
        finally:
            self._trava_uso.release()
        logger.info("[VISÃO] %s: %s (%d focos, maior %.0f%%)", origem, r["status"], r["total_deteccoes"],
                    r["maior_confianca"] * 100)
        return {
            "origem": origem, "fogo": r["status"] == "fogo_detectado", "focos": r["total_deteccoes"],
            "maior_confianca": r["maior_confianca"], "limiar": r["limiar_confianca"], "aviso": AVISO_DETECCAO,
            "largura": r["imagem_largura"], "altura": r["imagem_altura"], "milissegundos": milissegundos,
            "deteccoes": [{"confianca": d["confianca"], "caixa": d["caixa_xyxy"]} for d in r["deteccoes"]],
            "imagem": _para_pagina(anotada),
        }

    # --- exemplos
    def exemplos(self) -> list[dict]:
        """Os exemplos baixados, com a miniatura. Os que faltam não aparecem (a página explica como baixar)."""
        lista = []
        for e in self._exemplos.values():
            caminho = self._pasta_exemplos / e.arquivo
            if not caminho.is_file():
                continue
            if e.arquivo not in self._miniaturas:
                try:
                    self._miniaturas[e.arquivo] = _miniatura(caminho, e.tipo)
                except Exception as erro:  # sem miniatura, o exemplo continua utilizável
                    logger.warning("[VISÃO] Sem miniatura para %s: %s", e.arquivo, erro)
                    self._miniaturas[e.arquivo] = ""
            lista.append({"arquivo": e.arquivo, "titulo": e.titulo, "descricao": e.descricao, "tipo": e.tipo,
                          "miniatura": self._miniaturas[e.arquivo]})
        return lista

    def analisar_exemplo(self, arquivo: str) -> dict:
        """Só os exemplos da lista: a página não escolhe um caminho qualquer do disco."""
        exemplo = self._exemplos.get(arquivo)
        caminho = self._pasta_exemplos / arquivo if exemplo else None
        if not caminho or not caminho.is_file():
            return {"erro": "Este exemplo não foi baixado. Rode ferramentas\\baixar_modelos.py."}
        if exemplo.tipo == "video":
            return self.iniciar_video(str(caminho))
        r = self.analisar_arquivo(str(caminho))
        return {**r, "origem": f"Exemplo: {exemplo.titulo}"} if "erro" not in r else r

    # --- vídeo
    def _chave(self, entrada: Path) -> str:
        """O que define o resultado: o conteúdo do vídeo (não o nome: dois vídeos podem ter o mesmo), o limiar do
        modelo, a versão do pacote e a do laço. Mudou qualquer um, o vídeo é analisado de novo."""
        conteudo = hashlib.sha256()
        with open(entrada, "rb") as arquivo:
            while bloco := arquivo.read(BLOCO_HASH):
                conteudo.update(bloco)
        try:
            from importlib.metadata import version
            pacote = version("firewatch-ai")
        except Exception:
            pacote = "?"
        limiar = getattr(self._obter(), "confianca", None)
        partes = f"{conteudo.hexdigest()}|{limiar}|{pacote}|{LARGURA_VIDEO}|{VERSAO_DO_LACO}|{bool(self._processar_video)}"
        return hashlib.sha256(partes.encode()).hexdigest()[:16]

    def _ja_analisado(self, saida: Path) -> dict | None:
        resumo = saida.with_suffix(".json")
        if not (saida.is_file() and resumo.is_file()):
            return None
        try:
            dados = json.loads(resumo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # resumo estragado: analisa de novo
        # O aviso é sempre o atual: um resumo antigo pode ter guardado outro texto
        return {**dados, "estado": "pronto", "saida": str(saida), "tamanho": saida.stat().st_size, "reaproveitado": True,
                "aviso": AVISO_DETECCAO}

    def iniciar_video(self, caminho: str) -> dict:
        if self._video.get("estado") == "analisando":
            return {"erro": AVISO_OCUPADO}
        entrada = Path(caminho)
        try:
            chave = self._chave(entrada)
        except OSError as erro:
            return {"erro": f"Não consegui ler o vídeo: {erro}"}
        except RuntimeError as erro:  # o modelo não carregou
            return {"erro": str(erro)}
        # Procura pela chave, não pelo nome: uma cópia renomeada do mesmo vídeo também é reaproveitada
        existente = next(self._pasta.glob(f"*_firewatch_{chave}.mp4"), None) if self._pasta.is_dir() else None
        saida = existente or self._pasta / f"{entrada.stem}_firewatch_{chave}.mp4"
        anterior = self._ja_analisado(saida)
        if anterior:
            logger.info("[VISÃO] Vídeo %s já analisado: resultado reaproveitado", entrada.name)
            self._video = {**anterior, "origem": entrada.name}
            return self.progresso_video()
        if not self._trava_uso.acquire(blocking=False):
            return {"erro": AVISO_OCUPADO}
        self._pasta.mkdir(parents=True, exist_ok=True)
        self._cancelar.clear()
        self._video = {"estado": "analisando", "origem": entrada.name, "feitos": 0, "total": 0}
        threading.Thread(target=self._analisar_video, args=(entrada, saida), name="video-visao", daemon=True).start()
        return self.progresso_video()

    def _analisar_video(self, entrada: Path, saida: Path) -> None:
        def progresso(feitos, total):
            self._video.update(feitos=feitos, total=total)
            if self._cancelar.is_set():
                raise Cancelado()

        inicio = time.perf_counter()
        try:
            detector = self._obter()
            try:
                if not self._processar_video:
                    raise SemH264()
                r, tocavel = self._processar_video(detector, entrada, saida, progresso), True
            except SemH264:
                logger.warning("[VISÃO] Sem H.264 neste computador: o vídeo será gravado em mp4v e abre fora da Central")
                self._video.update(feitos=0, total=0)
                r, tocavel = detector.processar_video(entrada, saida=saida, progresso=progresso), False
            self._video = {"estado": "pronto", "origem": entrada.name, "saida": str(saida), "tocavel": tocavel,
                           "tamanho": saida.stat().st_size,
                           "fogo": r["status"] == "fogo_detectado", "quadros": r["frames_processados"],
                           "quadros_com_fogo": r["frames_com_fogo"], "primeiro_segundo": r["primeiro_segundo_com_fogo"],
                           "maior_confianca": r["maior_confianca"], "fps": r["fps"], "aviso": AVISO_DETECCAO,
                           "segundos": round(time.perf_counter() - inicio, 1)}
            # O resumo ao lado do vídeo: na próxima vez, o mesmo vídeo não é analisado de novo
            guardar = {k: v for k, v in self._video.items() if k not in ("estado", "saida", "tamanho")}
            saida.with_suffix(".json").write_text(json.dumps(guardar, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("[VISÃO] Vídeo %s: %s", entrada.name, r["status"])
        except Cancelado:
            self._apagar(saida)  # o pedaço gravado até ali não serve para nada
            self._video = {"estado": "cancelado", "origem": entrada.name}
        except Exception as erro:
            logger.error("[VISÃO] Falhou ao analisar o vídeo %s: %s", entrada.name, erro)
            self._apagar(saida)
            self._video = {"estado": "erro", "origem": entrada.name, "erro": f"A análise do vídeo falhou: {erro}"}
        finally:
            self._trava_uso.release()

    @staticmethod
    def _apagar(saida: Path) -> None:
        saida.unlink(missing_ok=True)
        saida.with_suffix(".json").unlink(missing_ok=True)

    def progresso_video(self) -> dict:
        return dict(self._video)

    def parte_do_video(self, inicio: int) -> dict:
        """Um pedaço do vídeo analisado, em base64, para a página montar e tocar. Só o último vídeo analisado:
        a página não escolhe arquivo nenhum."""
        saida = self._video.get("saida")
        if self._video.get("estado") != "pronto" or not self._video.get("tocavel") or not saida:
            return {"erro": "Nenhum vídeo analisado para tocar."}
        try:
            with open(saida, "rb") as arquivo:
                total = os.fstat(arquivo.fileno()).st_size
                inicio = max(0, min(int(inicio), total))
                arquivo.seek(inicio)
                dados = arquivo.read(PEDACO_VIDEO)
        except OSError as erro:
            return {"erro": f"O vídeo analisado não está mais na pasta: {erro}"}
        return {"dados": base64.b64encode(dados).decode("ascii"), "inicio": inicio, "total": total,
                "fim": inicio + len(dados) >= total}

    def cancelar_video(self) -> dict:
        self._cancelar.set()
        return self.progresso_video()

    def abrir_video(self) -> dict:
        saida = self._video.get("saida")
        if not saida or not Path(saida).is_file():
            return {"erro": "O vídeo analisado não está mais na pasta."}
        self._abrir(saida)
        return {}

    def abrir_pasta(self) -> dict:
        self._pasta.mkdir(parents=True, exist_ok=True)
        self._abrir(str(self._pasta))
        return {}


class ApiVisao:
    """Funções que a página pode chamar (atributos privados: o pywebview expõe os públicos)."""

    def __init__(self, servico):
        self._servico = servico
        self._janela = None

    def _usar_janela(self, janela):
        """Chamado pela JanelaAuxiliar: a caixa de escolher arquivo precisa da janela."""
        self._janela = janela

    def _escolher(self, tipos) -> str:
        import webview
        if not self._janela:
            return ""
        escolhidos = self._janela.create_file_dialog(webview.FileDialog.OPEN, file_types=tipos)
        return escolhidos[0] if escolhidos else ""

    def preparar(self):
        return self._servico.preparar()

    def estado(self):
        return self._servico.estado()

    def escolher_imagem(self):
        caminho = self._escolher(TIPOS_IMAGEM)
        return self._servico.analisar_arquivo(caminho) if caminho else {"cancelado": True}

    def analisar_dados(self, dados_base64, nome):
        return self._servico.analisar_dados(dados_base64, nome)

    def foto_camera(self):
        return self._servico.analisar_camera()

    def exemplos(self):
        return self._servico.exemplos()

    def analisar_exemplo(self, arquivo):
        return self._servico.analisar_exemplo(arquivo)

    def escolher_video(self):
        caminho = self._escolher(TIPOS_VIDEO)
        return self._servico.iniciar_video(caminho) if caminho else {"cancelado": True}

    def progresso_video(self):
        return self._servico.progresso_video()

    def parte_do_video(self, inicio):
        return self._servico.parte_do_video(inicio)

    def cancelar_video(self):
        return self._servico.cancelar_video()

    def abrir_video(self):
        return self._servico.abrir_video()

    def abrir_pasta(self):
        return self._servico.abrir_pasta()
