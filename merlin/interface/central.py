"""Central: uma janela só para tudo o que é de configurar ou investigar, com um menu lateral de abas.

As abas de ajustes (assistente, inteligência, pastas) são da própria página de configurações. As outras
(assistentes, habilidades e alertas) são as páginas de sempre, cada uma num quadro (iframe) dentro dela.
O raciocínio da IA fica no cartão do assistente (modo debug), não aqui.
Cada página continua falando só com a sua API: a do quadro de habilidades vê pywebview.api.habilidades
como se fosse pywebview.api, e assim por diante."""
import html
import threading

from merlin.config import ARQ_ALERTAS, ARQ_ASSISTENTES, ARQ_CONFIGURACOES, ARQ_HABILIDADES
from merlin.interface.janela_auxiliar import JanelaAuxiliar
from merlin.interface.mapa import com_mapa

LARGURA, ALTURA = 1080, 740
ABA_INICIAL = "assistente"
# Páginas que entram em quadros: o nome é a aba e também o nome da API delas dentro da ApiCentral
QUADROS = {"assistentes": ARQ_ASSISTENTES, "habilidades": ARQ_HABILIDADES, "alertas": ARQ_ALERTAS}
# Mudam como a IA decide e age: no perfil operador, nem entram na página (merlin/interface/perfil.py)
QUADROS_SO_ADMINISTRADOR = {"assistentes", "habilidades"}
# Na página, o que tem data-so-admin é tirado antes de as abas serem montadas
MODO_OPERADOR = "<script>window.MODO_OPERADOR = true;</script>"

# Vai no começo de cada página de quadro: a API dela é a parte correspondente da API da Central, e o aviso de
# "pronto" do pywebview é repassado quando a página termina de carregar (ela escuta esse aviso no fim do corpo)
PONTE = """<script>
  window.pywebview = { api: new Proxy({}, { get: (_, nome) => (...args) => parent.pywebview.api.%(aba)s[nome](...args) }) };
  document.addEventListener("DOMContentLoaded", () => {
    const avisar = () => parent.quandoPronto(() => window.dispatchEvent(new Event("pywebviewready")));
    if (parent.quandoPronto) avisar();
    else parent.addEventListener("DOMContentLoaded", avisar);  // o quadro carregou antes da Central
  });
</script>
<style>
  /* Dentro da Central, o fundo é o dela */
  html, body { background: transparent !important; }
</style>
"""


def quadro(aba: str, arquivo, api: str | None = None) -> str:
    """Um iframe com a página embutida (srcdoc) e a ponte para pywebview.api.<api> da janela onde ele está."""
    conteudo = com_mapa(arquivo.read_text(encoding="utf-8").replace("<head>", "<head>" + PONTE % {"aba": api or aba}, 1))
    return f'<iframe class="quadro" id="quadro-{aba}" title="{aba}" srcdoc="{html.escape(conteudo, quote=True)}"></iframe>'


def montar_pagina(administrador: bool = True) -> str:
    """A página de configurações com as outras páginas embutidas nos quadros (srcdoc: tudo offline, sem arquivos).
    Para o operador, sem os quadros e as abas que mudam a IA."""
    pagina = ARQ_CONFIGURACOES.read_text(encoding="utf-8")
    for aba, arquivo in QUADROS.items():
        marcador = f"<!--QUADRO:{aba}-->"
        if marcador not in pagina:
            raise ValueError(f"a página de configurações não tem o lugar do quadro {aba}")
        liberado = administrador or aba not in QUADROS_SO_ADMINISTRADOR
        pagina = pagina.replace(marcador, quadro(aba, arquivo) if liberado else "")
    if not administrador:
        pagina = pagina.replace("<head>", "<head>" + MODO_OPERADOR, 1)
    return pagina


class ApiCentral:
    """As APIs de cada parte, como atributos: na página, pywebview.api.ajustes.carregar(), etc."""

    def __init__(self, ajustes, assistentes, habilidades, alertas):
        self.ajustes = ajustes
        self.assistentes = assistentes
        self.habilidades = habilidades
        self.alertas = alertas
        self._aba_pendente = ABA_INICIAL

    def aba_inicial(self):
        """A página pergunta, ao carregar, qual aba abrir (a que foi pedida antes de a janela existir)."""
        aba, self._aba_pendente = self._aba_pendente, ABA_INICIAL
        return aba

    def _usar_janela(self, janela):
        for parte in (self.ajustes, self.assistentes, self.habilidades, self.alertas):
            if hasattr(parte, "_usar_janela"):
                parte._usar_janela(janela)


class JanelaCentral(JanelaAuxiliar):
    def __init__(self, api: ApiCentral, administrador: bool = True):
        super().__init__("Central", ARQ_CONFIGURACOES, api, LARGURA, ALTURA,
                         redimensionavel=True, sempre_na_frente=False)
        self._administrador = administrador

    def _html(self) -> str:
        return montar_pagina(self._administrador)

    def abrir_aba(self, aba: str = ABA_INICIAL) -> None:
        """Abre a Central já na aba pedida (ou só troca de aba, se ela já estiver aberta)."""
        self._api._aba_pendente = aba  # vale se a janela for criada agora: a página pergunta ao carregar
        if not self.abrir():
            # Já estava aberta: troca a aba. Em outra thread, porque evaluate_js espera a página responder
            janela = self._janela
            threading.Thread(target=lambda: janela.evaluate_js(f"abrirAba({aba!r})"), daemon=True).start()

    def porta(self, aba: str):
        """Um atalho para uma aba, com abrir() e fechar(), para quem só sabe abrir 'uma janela'."""
        central = self

        class Porta:
            def abrir(self):
                central.abrir_aba(aba)

            def fechar(self):
                central.fechar()

        return Porta()
