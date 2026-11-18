"""Leitor dos protocolos: a fonte citada pelo especialista abre numa janela do Merlin, já na página do trecho.

Usa o leitor de PDF do próprio WebView2 (zoom, busca, imprimir), sem programa externo. Uma janela só: abrir
outra fonte troca o documento na mesma janela.
"""
import logging
import threading

from merlin.ia.especialista import DOCUMENTOS, pdf_do_documento

logger = logging.getLogger(__name__)

LARGURA, ALTURA = 980, 780
FUNDO = "#05070C"
AVISO_SEM_PDF = "O PDF deste protocolo não foi baixado. Rode ferramentas\\baixar_modelos.py."


def endereco(documento: str, pagina: int) -> str | None:
    """file:///.../DOC005.pdf#page=49, ou None se o documento não existe ou não foi baixado."""
    caminho = pdf_do_documento(documento)
    if caminho is None:
        return None
    return f"{caminho.resolve().as_uri()}#page={max(1, int(pagina))}"


class LeitorProtocolos:
    def __init__(self, criar_janela=None):
        self._criar_janela = criar_janela  # para os testes; None usa o pywebview
        self._janela = None
        self._trava = threading.Lock()

    def abrir(self, documento: str, pagina, titulo: str = "") -> dict:
        try:
            pagina = int(pagina)
        except (TypeError, ValueError):
            return {"erro": "Página inválida."}
        if documento not in DOCUMENTOS:
            return {"erro": "Esse documento não faz parte dos protocolos."}
        url = endereco(documento, pagina)
        if url is None:
            return {"erro": AVISO_SEM_PDF}
        nome = f"Protocolo · {titulo or documento} · página {pagina}"
        with self._trava:
            if self._janela is not None:
                try:
                    self._janela.load_url(url)
                    self._janela.set_title(nome)
                    self._janela.show()
                    self._janela.restore()
                    return {}
                except Exception:
                    self._janela = None  # foi fechada pelo X
            self._janela = self._nova(nome, url)
            self._janela.events.closed += self._ao_fechar
        logger.info("[PROTOCOLOS] Abrindo %s na página %d", documento, pagina)
        return {}

    def _nova(self, nome, url):
        if self._criar_janela:
            return self._criar_janela(nome, url)
        import webview
        return webview.create_window(nome, url=url, width=LARGURA, height=ALTURA, resizable=True,
                                     background_color=FUNDO)

    def fechar(self) -> None:
        with self._trava:
            janela, self._janela = self._janela, None
        if janela is not None:
            try:
                janela.destroy()
            except Exception:
                pass

    def _ao_fechar(self):
        with self._trava:
            self._janela = None
