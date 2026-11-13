"""O mapa das páginas (Leaflet e o contorno do Brasil), embutido na própria página para abrir mesmo sem internet.

Fica fora da central.py porque o painel web (merlin/web) também usa, e ele roda sem o pywebview."""
from merlin.config import ARQ_CONTORNO_BRASIL, PASTA_LEAFLET

MARCADOR_MAPA = "<!--MAPA-->"


def mapa_embutido() -> str:
    """O Leaflet e o contorno do Brasil, dentro da própria página: o mapa abre mesmo sem internet."""
    css = (PASTA_LEAFLET / "leaflet.css").read_text(encoding="utf-8")
    js = (PASTA_LEAFLET / "leaflet.js").read_text(encoding="utf-8")
    contorno = ARQ_CONTORNO_BRASIL.read_text(encoding="utf-8").replace("</", "<\\/")  # um "</script>" no meio fecharia o script
    return f"<style>{css}</style><script>{js}</script><script>window.CONTORNO_BRASIL = {contorno};</script>"


def com_mapa(pagina: str) -> str:
    """A página com o mapa no lugar do marcador (se ela tiver um)."""
    return pagina.replace(MARCADOR_MAPA, mapa_embutido(), 1) if MARCADOR_MAPA in pagina else pagina
