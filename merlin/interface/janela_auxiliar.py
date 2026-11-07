"""Janela secundária (a Central): abre uma vez só, volta para a frente se já estiver aberta
e fecha junto com o programa."""
import threading
from pathlib import Path

import webview

FUNDO = "#05070C"


class JanelaAuxiliar:
    def __init__(self, titulo: str, pagina: Path, api, largura: int, altura: int,
                 redimensionavel: bool = False, sempre_na_frente: bool = True):
        self._titulo = titulo
        self._pagina = pagina
        self._api = api
        self._tamanho = (largura, altura)
        self._redimensionavel = redimensionavel
        self._sempre_na_frente = sempre_na_frente
        self._janela = None
        self._trava = threading.Lock()

    def _html(self) -> str:
        return self._pagina.read_text(encoding="utf-8")

    def abrir(self) -> bool:
        """Abre a janela, ou traz para a frente se já estiver aberta. Retorna True se ela foi criada agora."""
        with self._trava:
            if self._janela is not None:
                try:
                    self._janela.show()
                    self._janela.restore()
                    return False
                except Exception:
                    self._janela = None  # foi fechada pelo X
            largura, altura = self._tamanho
            self._janela = webview.create_window(
                self._titulo, html=self._html(), js_api=self._api,
                width=largura, height=altura, resizable=self._redimensionavel,
                on_top=self._sempre_na_frente, background_color=FUNDO,
            )
            self._janela.events.closed += self._ao_fechar
            if hasattr(self._api, "_usar_janela"):  # para a página poder abrir caixas de escolher arquivo
                self._api._usar_janela(self._janela)
            return True

    def fechar(self) -> None:
        with self._trava:
            janela, self._janela = self._janela, None
        if janela is not None:  # fora da trava: o destroy dispara _ao_fechar, que também a usa
            try:
                janela.destroy()
            except Exception:
                pass  # já tinha sido fechada

    def _ao_fechar(self):
        with self._trava:
            self._janela = None
