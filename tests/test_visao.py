"""Aba Visão: o serviço em volta do FireWatch AI. O detector é falso (sem torch nem YOLO); as imagens são reais."""
import base64
import tempfile
import threading
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from merlin.interface.painel_visao import (AVISO_DETECCAO, AVISO_IMAGEM_INVALIDA, AVISO_OCUPADO, LADO_MAXIMO, PEDACO_VIDEO, SemH264,
                                           ServicoVisao, processar_video_h264)

AVISO = "Detecção automática de apoio. Emergência: Corpo de Bombeiros 193 / Defesa Civil 199."


def imagem_png(largura=64, altura=48) -> bytes:
    return cv2.imencode(".png", np.full((altura, largura, 3), 90, dtype=np.uint8))[1].tobytes()


class DetectorFalso:
    confianca = 0.25

    def __init__(self, focos=(0.6, 0.31)):
        self.focos = focos
        self.imagens = []
        self.liberar_video = threading.Event()
        self.liberar_video.set()

    def detectar(self, imagem):
        self.imagens.append(imagem.shape)
        deteccoes = [{"classe": "Fire", "confianca": c, "caixa_xyxy": [1.0, 2.0, 30.0, 40.0]} for c in self.focos]
        return {"status": "fogo_detectado" if deteccoes else "sem_fogo", "total_deteccoes": len(deteccoes),
                "maior_confianca": max(self.focos, default=0.0), "deteccoes": deteccoes,
                "imagem_largura": imagem.shape[1], "imagem_altura": imagem.shape[0],
                "limiar_confianca": self.confianca, "aviso": AVISO}

    def anotar(self, imagem):
        return imagem

    def processar_video(self, entrada, saida, progresso):
        Path(saida).write_bytes(b"video")
        for feito in range(1, 11):
            self.liberar_video.wait(2)
            progresso(feito, 10)
        return {"status": "fogo_detectado", "frames_processados": 10, "frames_com_fogo": 4,
                "primeiro_segundo_com_fogo": 1.2, "maior_confianca": 0.7, "fps": 25.0, "aviso": AVISO}


class Base(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.detector = DetectorFalso()
        self.abertos = []
        # processar_video=None: o caminho do pacote (o detector falso grava um vídeo de mentira)
        self.servico = ServicoVisao(carregar=lambda: self.detector, pasta=self.pasta / "visao",
                                    abrir=self.abertos.append, camera=lambda: np.zeros((30, 40, 3), np.uint8),
                                    processar_video=None)

    def esperar_video(self, estado, limite=3):
        fim = time.monotonic() + limite
        while self.servico.progresso_video()["estado"] != estado and time.monotonic() < fim:
            time.sleep(0.01)
        return self.servico.progresso_video()


class TestModelo(Base):
    def test_carrega_em_segundo_plano_quando_a_aba_abre(self):
        self.servico.preparar()
        fim = time.monotonic() + 2
        while not self.servico.estado()["pronto"] and time.monotonic() < fim:
            time.sleep(0.01)
        self.assertEqual(self.servico.estado(), {"pronto": True, "carregando": False, "erro": "", "limiar": 0.25})

    def test_falha_na_carga_vira_mensagem(self):
        def quebra():
            raise OSError("sem os pesos")
        servico = ServicoVisao(carregar=quebra, pasta=self.pasta)
        with self.assertLogs("merlin.interface.painel_visao", "ERROR"):
            r = servico.analisar_dados(base64.b64encode(imagem_png()).decode(), "x.png")
        self.assertIn("sem os pesos", r["erro"])
        self.assertIn("sem os pesos", servico.estado()["erro"])


class TestImagem(Base):
    def test_arquivo_com_acento_no_caminho(self):
        # o cv2.imread não abre caminhos com acento no Windows: a leitura é feita pelos bytes
        caminho = self.pasta / "incêndio na área.png"
        caminho.write_bytes(imagem_png())
        r = self.servico.analisar_arquivo(str(caminho))
        self.assertTrue(r["fogo"])
        self.assertEqual((r["focos"], r["maior_confianca"], r["origem"]), (2, 0.6, "incêndio na área.png"))
        self.assertEqual((r["largura"], r["altura"]), (64, 48))
        self.assertTrue(r["imagem"].startswith("data:image/jpeg;base64,"))
        # O aviso é para o agente que faz a triagem, não o do pacote para o público ("Emergência: 193 / 199")
        self.assertEqual(r["aviso"], AVISO_DETECCAO)
        self.assertNotIn("199", r["aviso"])

    def test_imagem_arrastada_em_base64(self):
        dados = "data:image/png;base64," + base64.b64encode(imagem_png()).decode()
        r = self.servico.analisar_dados(dados, "solta.png")
        self.assertEqual(r["origem"], "solta.png")
        self.assertEqual(r["deteccoes"][0], {"confianca": 0.6, "caixa": [1.0, 2.0, 30.0, 40.0]})

    def test_sem_fogo(self):
        self.detector.focos = ()
        r = self.servico.analisar_dados(base64.b64encode(imagem_png()).decode(), "x.png")
        self.assertEqual((r["fogo"], r["focos"], r["deteccoes"]), (False, 0, []))

    def test_arquivo_que_nao_e_imagem(self):
        caminho = self.pasta / "texto.jpg"
        caminho.write_text("não sou uma imagem")
        self.assertEqual(self.servico.analisar_arquivo(str(caminho)), {"erro": AVISO_IMAGEM_INVALIDA})
        self.assertEqual(self.servico.analisar_dados("@@@", "x"), {"erro": AVISO_IMAGEM_INVALIDA})

    def test_imagem_grande_e_reduzida_para_a_pagina(self):
        grande = cv2.imencode(".png", np.zeros((3000, 4000, 3), np.uint8))[1].tobytes()
        r = self.servico.analisar_dados(base64.b64encode(grande).decode(), "grande.png")
        pagina = cv2.imdecode(np.frombuffer(base64.b64decode(r["imagem"].split(",")[1]), np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(max(pagina.shape[:2]), LADO_MAXIMO)
        self.assertEqual((r["largura"], r["altura"]), (4000, 3000))  # o tamanho original continua informado

    def test_foto_da_camera(self):
        r = self.servico.analisar_camera()
        self.assertEqual((r["origem"], r["largura"], r["altura"]), ("Foto da câmera", 40, 30))

    def test_camera_indisponivel(self):
        def sem_camera():
            raise RuntimeError("Não encontrei uma câmera")
        self.servico._camera = sem_camera
        self.assertEqual(self.servico.analisar_camera(), {"erro": "Não encontrei uma câmera"})


class TestExemplos(Base):
    def setUp(self):
        super().setUp()
        from merlin.interface.painel_visao import Exemplo
        self.exemplos = self.pasta / "exemplos"
        self.exemplos.mkdir()
        (self.exemplos / "predio.png").write_bytes(imagem_png())
        video = cv2.VideoWriter(str(self.exemplos / "casa.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
        for _ in range(10):
            video.write(np.full((48, 64, 3), 60, np.uint8))
        video.release()
        self.servico = ServicoVisao(carregar=lambda: self.detector, pasta=self.pasta / "visao", abrir=self.abertos.append,
                                    processar_video=None, pasta_exemplos=self.exemplos, exemplos=(
                                        Exemplo("casa.mp4", "Casa em chamas", "Vídeo, 1 s", "video", "x"),
                                        Exemplo("predio.png", "Prédio em chamas", "Imagem", "imagem", "x"),
                                        Exemplo("faltando.mp4", "Não baixado", "Vídeo", "video", "x")))

    def test_lista_so_os_baixados_com_miniatura(self):
        lista = self.servico.exemplos()
        self.assertEqual([e["arquivo"] for e in lista], ["casa.mp4", "predio.png"])
        self.assertTrue(all(e["miniatura"].startswith("data:image/jpeg;base64,") for e in lista))

    def test_exemplo_de_imagem(self):
        r = self.servico.analisar_exemplo("predio.png")
        self.assertEqual((r["origem"], r["focos"]), ("Exemplo: Prédio em chamas", 2))

    def test_exemplo_de_video_usa_o_mesmo_caminho_dos_videos(self):
        self.assertEqual(self.servico.analisar_exemplo("casa.mp4")["estado"], "analisando")
        self.assertEqual(self.esperar_video("pronto")["origem"], "casa.mp4")

    def test_so_arquivos_da_lista(self):
        # A página não consegue mandar analisar um caminho qualquer do disco
        for pedido in ("faltando.mp4", "../visao/qualquer.mp4", r"C:\Windows\win.ini", "nao_existe.jpg"):
            with self.subTest(pedido):
                self.assertIn("baixar_modelos", self.servico.analisar_exemplo(pedido)["erro"])

    def test_os_exemplos_reais_tem_hash_para_conferir_o_download(self):
        from merlin.interface.painel_visao import EXEMPLOS, ORIGEM_EXEMPLOS
        self.assertRegex(ORIGEM_EXEMPLOS, r"/[0-9a-f]{40}/")  # fixado num commit
        for e in EXEMPLOS:
            self.assertRegex(e.sha256, r"^[0-9a-f]{64}$", e.arquivo)
            self.assertIn(e.tipo, ("video", "imagem"))


class TestVideo(Base):
    def test_analisa_em_segundo_plano_e_salva_na_pasta(self):
        entrada = self.pasta / "drone.mp4"
        entrada.write_bytes(b"x")
        self.assertEqual(self.servico.iniciar_video(str(entrada))["estado"], "analisando")
        v = self.esperar_video("pronto")
        self.assertEqual((v["fogo"], v["quadros"], v["quadros_com_fogo"], v["primeiro_segundo"]), (True, 10, 4, 1.2))
        self.assertTrue(Path(v["saida"]).is_file())
        self.assertEqual(Path(v["saida"]).parent, self.pasta / "visao")
        self.assertTrue(Path(v["saida"]).name.startswith("drone_firewatch_"))
        self.servico.abrir_video()
        self.assertEqual(self.abertos, [v["saida"]])

    def test_imagem_durante_o_video_e_recusada(self):
        self.detector.liberar_video.clear()
        (self.pasta / "longo.mp4").write_bytes(b"longo")
        self.servico.iniciar_video(str(self.pasta / "longo.mp4"))
        self.assertEqual(self.servico.analisar_camera(), {"erro": AVISO_OCUPADO})
        self.assertEqual(self.servico.iniciar_video(str(self.pasta / "outro.mp4")), {"erro": AVISO_OCUPADO})
        self.detector.liberar_video.set()
        self.esperar_video("pronto")
        self.assertNotIn("erro", self.servico.analisar_camera())  # terminou: a análise volta a funcionar

    def test_cancelar_apaga_o_video_pela_metade(self):
        self.detector.liberar_video.clear()
        (self.pasta / "longo.mp4").write_bytes(b"longo")
        self.servico.iniciar_video(str(self.pasta / "longo.mp4"))
        self.servico.cancelar_video()
        self.detector.liberar_video.set()
        self.assertEqual(self.esperar_video("cancelado")["estado"], "cancelado")
        self.assertEqual(list((self.pasta / "visao").iterdir()), [])
        self.assertNotIn("erro", self.servico.analisar_camera())

    def test_abrir_a_pasta(self):
        self.servico.abrir_pasta()
        self.assertEqual(self.abertos, [str(self.pasta / "visao")])
        self.assertIn("erro", self.servico.abrir_video())  # nenhum vídeo analisado ainda


def video_real(caminho: Path, quadros=12, fps=10) -> Path:
    escritor = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    for i in range(quadros):
        escritor.write(np.full((48, 64, 3), 20 * i % 255, np.uint8))
    escritor.release()
    return caminho


class ResultadoFalso:
    """O que o Ultralytics devolve por quadro: as caixas (com a confiança) e a imagem desenhada."""

    class Caixas:
        def __init__(self, confiancas):
            self.conf = confiancas

        def __len__(self):
            return len(self.conf)

    def __init__(self, quadro, confiancas):
        self.boxes = self.Caixas(confiancas)
        self._quadro = quadro

    def plot(self):
        return self._quadro


class DetectorComPrever:
    def __init__(self):
        self.quadro = 0

    def _prever(self, quadro):
        self.quadro += 1
        return ResultadoFalso(quadro, [0.7] if self.quadro > 6 else [])  # o fogo aparece no 7º quadro


class TestVideoJaAnalisado(Base):
    """O mesmo vídeo não é analisado de novo: o resultado e o vídeo marcado são reaproveitados."""

    def analisar(self, caminho):
        self.servico.iniciar_video(str(caminho))
        return self.esperar_video("pronto")

    def contar_analises(self):
        chamadas = []
        original = self.detector.processar_video
        self.detector.processar_video = lambda *a, **k: (chamadas.append(1), original(*a, **k))[1]
        return chamadas

    def test_segunda_vez_reaproveita_sem_analisar(self):
        chamadas = self.contar_analises()
        video = self.pasta / "drone.mp4"
        video.write_bytes(b"conteudo do drone")
        primeira = self.analisar(video)
        segunda = self.servico.iniciar_video(str(video))  # volta pronto na hora, sem passar por "analisando"
        self.assertEqual(len(chamadas), 1)
        self.assertEqual((segunda["estado"], segunda["reaproveitado"]), ("pronto", True))
        self.assertEqual(segunda["saida"], primeira["saida"])
        self.assertEqual((segunda["quadros_com_fogo"], segunda["primeiro_segundo"]), (4, 1.2))
        self.assertTrue(Path(primeira["saida"]).with_suffix(".json").is_file())

    def test_vale_pelo_conteudo_e_nao_pelo_nome(self):
        chamadas = self.contar_analises()
        a, b = self.pasta / "a.mp4", self.pasta / "b.mp4"
        a.write_bytes(b"mesmo conteudo")
        b.write_bytes(b"mesmo conteudo")
        self.analisar(a)
        self.assertTrue(self.servico.iniciar_video(str(b))["reaproveitado"])  # cópia renomeada
        a.write_bytes(b"outro conteudo")  # mesmo nome, vídeo diferente
        self.assertEqual(self.analisar(a).get("reaproveitado"), None)
        self.assertEqual(len(chamadas), 2)

    def test_limiar_diferente_analisa_de_novo(self):
        chamadas = self.contar_analises()
        video = self.pasta / "drone.mp4"
        video.write_bytes(b"drone")
        self.analisar(video)
        self.detector.confianca = 0.4
        self.assertNotIn("reaproveitado", self.analisar(video))
        self.assertEqual(len(chamadas), 2)

    def test_resumo_apagado_ou_estragado_analisa_de_novo(self):
        chamadas = self.contar_analises()
        video = self.pasta / "drone.mp4"
        video.write_bytes(b"drone")
        resumo = Path(self.analisar(video)["saida"]).with_suffix(".json")
        resumo.write_text("{quebrado", encoding="utf-8")
        self.assertNotIn("reaproveitado", self.analisar(video))
        self.assertEqual(len(chamadas), 2)

    def test_cancelado_nao_deixa_resumo(self):
        self.detector.liberar_video.clear()
        video = self.pasta / "drone.mp4"
        video.write_bytes(b"drone")
        self.servico.iniciar_video(str(video))
        self.servico.cancelar_video()
        self.detector.liberar_video.set()
        self.esperar_video("cancelado")
        self.assertEqual(list((self.pasta / "visao").iterdir()), [])

    def test_video_que_nao_existe(self):
        self.assertIn("Não consegui ler o vídeo", self.servico.iniciar_video(str(self.pasta / "sumiu.mp4"))["erro"])


class TestVideoH264(unittest.TestCase):
    """O laço do Merlin grava em H.264 para o vídeo tocar dentro da Central (o pacote grava em mp4v)."""

    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def test_grava_em_h264_e_resume_como_o_pacote(self):
        saida, progresso = self.pasta / "saida.mp4", []
        r = processar_video_h264(DetectorComPrever(), video_real(self.pasta / "entrada.mp4"), saida,
                                 lambda feitos, total: progresso.append(feitos))
        self.assertEqual((r["status"], r["frames_processados"], r["frames_com_fogo"]), ("fogo_detectado", 12, 6))
        self.assertEqual(r["primeiro_segundo_com_fogo"], 0.6)  # 7º quadro a 10 quadros por segundo
        self.assertEqual(progresso, list(range(1, 13)))
        captura = cv2.VideoCapture(str(saida))
        codec = int(captura.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode()
        captura.release()
        self.assertIn(codec.lower(), ("avc1", "h264"))  # o mesmo formato: grava como avc1, a leitura diz h264

    def test_sem_h264_cai_para_o_pacote_e_abre_fora(self):
        def sem_h264(*_):
            raise SemH264()
        detector = DetectorFalso()
        servico = ServicoVisao(carregar=lambda: detector, pasta=self.pasta / "visao", processar_video=sem_h264)
        (self.pasta / "x.mp4").write_bytes(b"x")
        with self.assertLogs("merlin.interface.painel_visao", "WARNING"):
            servico.iniciar_video(str(self.pasta / "x.mp4"))
            fim = time.monotonic() + 3
            while servico.progresso_video()["estado"] == "analisando" and time.monotonic() < fim:
                time.sleep(0.01)
        v = servico.progresso_video()
        self.assertEqual((v["estado"], v["tocavel"]), ("pronto", False))
        self.assertIn("erro", servico.parte_do_video(0))  # não toca na página: abre no player do Windows

    def test_video_vai_para_a_pagina_em_pedacos(self):
        servico = ServicoVisao(carregar=DetectorComPrever, pasta=self.pasta / "visao")
        self.assertIn("erro", servico.parte_do_video(0))  # nada analisado ainda
        servico.iniciar_video(str(video_real(self.pasta / "entrada.mp4", quadros=30)))
        fim = time.monotonic() + 5
        while servico.progresso_video()["estado"] == "analisando" and time.monotonic() < fim:
            time.sleep(0.01)
        v = servico.progresso_video()
        self.assertTrue(v["tocavel"])
        juntos, inicio = b"", 0
        while True:
            parte = servico.parte_do_video(inicio)
            juntos += base64.b64decode(parte["dados"])
            inicio = parte["inicio"] + len(base64.b64decode(parte["dados"]))
            if parte["fim"]:
                break
        self.assertEqual(juntos, Path(v["saida"]).read_bytes())
        self.assertEqual(parte["total"], v["tamanho"])
        self.assertLessEqual(len(base64.b64decode(servico.parte_do_video(0)["dados"])), PEDACO_VIDEO)


if __name__ == "__main__":
    unittest.main()
