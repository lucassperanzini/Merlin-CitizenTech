"""Aba Automações: mostra os scripts escritos pela IA, deixa escolher a pasta, corrigir o código e executar."""
from urllib.parse import quote

import webview

from merlin.automacao.ambiente import CONHECIDAS, Ambiente, nome_valido
from merlin.automacao.scripts import ArmazemDeScripts, ScriptInvalido
from merlin.config import PASTA_SCRIPTS


class ServicoAutomacoes:
    def __init__(self, pasta_scripts=PASTA_SCRIPTS, copiar=None, ambiente=None, abrir_pagina=None):
        self._scripts = ArmazemDeScripts(pasta_scripts)
        self._copiar = copiar  # escreve na área de transferência (substituível nos testes)
        self._ambiente = ambiente or Ambiente()
        self._abrir_pagina = abrir_pagina

    def estado(self) -> dict:
        scripts = self._scripts.listar()
        for script in scripts:
            script["faltando"] = [{"modulo": m, "pacote": CONHECIDAS.get(m, m), "conhecida": m in CONHECIDAS}
                                  for m in self._ambiente.faltando(script["externos"])]
        return {"scripts": scripts, "python_pronto": self._ambiente.pronto()}

    def _falta_neste_script(self, id_script, modulo) -> dict | None:
        """Só se instala o que este script precisa: a página não consegue pedir um pacote qualquer."""
        script = next((s for s in self.estado()["scripts"] if s["id"] == id_script), None)
        return next((f for f in script["faltando"] if f["modulo"] == modulo), None) if script else None

    def preparar_python(self) -> dict:
        ok, resposta = self._ambiente.preparar()
        return self.estado() if ok else {"erro": f"Não consegui preparar o Python dos scripts. {resposta}"}

    def instalar_biblioteca(self, id_script, modulo) -> dict:
        falta = self._falta_neste_script(id_script, modulo)
        if falta is None or not nome_valido(falta["pacote"]):
            return {"erro": "Este script não precisa dessa biblioteca."}
        if not self._ambiente.pronto():
            return {"erro": "O Python dos scripts ainda não está pronto."}
        ok, resposta = self._ambiente.instalar(falta["pacote"])
        return self.estado() if ok else {"erro": f"Não consegui instalar {falta['pacote']}. {resposta}"}

    def abrir_pagina_pacote(self, id_script, modulo) -> dict:
        falta = self._falta_neste_script(id_script, modulo)
        if falta is None or not nome_valido(falta["pacote"]):
            return {"erro": "Este script não precisa dessa biblioteca."}
        abrir = self._abrir_pagina
        if abrir is None:
            import webbrowser
            abrir = webbrowser.open
        abrir(f"https://pypi.org/project/{quote(falta['pacote'])}/")
        return {}

    def definir_pasta_script(self, id_script, caminho) -> dict:
        try:
            self._scripts.definir_pasta(id_script, caminho)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def salvar_codigo_script(self, id_script, codigo) -> dict:
        try:
            self._scripts.salvar_codigo(id_script, codigo)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def agendar_script(self, id_script, hora) -> dict:
        try:
            self._scripts.agendar(id_script, hora)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def agendar_unico_script(self, id_script, quantidade, unidade) -> dict:
        try:
            segundos = int(float(quantidade)) * (60 if unidade == "minutos" else 1)
        except (TypeError, ValueError, OverflowError):
            return {"erro": "Escolha um tempo válido."}
        try:
            self._scripts.agendar_unico(id_script, segundos)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def cancelar_unico_script(self, id_script) -> dict:
        try:
            self._scripts.cancelar_unico(id_script)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def pausar_agenda_script(self, id_script, pausar) -> dict:
        try:
            self._scripts.pausar_agenda(id_script, bool(pausar))
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def remover_agenda_script(self, id_script) -> dict:
        try:
            self._scripts.remover_agenda(id_script)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def aprovar_script(self, id_script, nome) -> dict:
        try:
            self._scripts.aprovar(id_script, nome)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def desaprovar_script(self, id_script) -> dict:
        try:
            self._scripts.desaprovar(id_script)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()

    def executar_script(self, id_script) -> dict:
        try:
            return self._scripts.executar(id_script)
        except ScriptInvalido as erro:
            return {"erro": str(erro)}
        except OSError as erro:
            return {"erro": f"Não consegui executar: {erro}"}

    def copiar_script(self, id_script) -> dict:
        try:
            codigo = self._scripts.codigo(id_script)
            copiar = self._copiar
            if copiar is None:
                from merlin.acoes.selecao import AreaDeTransferencia
                copiar = AreaDeTransferencia().escrever_texto
            copiar(codigo)
        except ScriptInvalido as erro:
            return {"erro": str(erro)}
        except Exception:  # outro programa pode estar segurando a área de transferência
            return {"erro": "Não consegui copiar agora. Tente de novo."}
        return {}

    def apagar_script(self, id_script) -> dict:
        try:
            self._scripts.apagar(id_script)
        except (ScriptInvalido, OSError) as erro:
            return {"erro": str(erro)}
        return self.estado()


class ApiAutomacoes:
    """Funções que a página pode chamar (atributos privados: o pywebview expõe os públicos)."""

    def __init__(self, servico):
        self._servico = servico
        self._janela = None
        self._script_pedido = ""

    def _usar_janela(self, janela):
        self._janela = janela

    def _pedir_script(self, id_script):
        """O cartão pediu para abrir este script: a página pergunta ao ficar visível."""
        self._script_pedido = id_script

    def script_pedido(self):
        """Entrega o pedido uma única vez, para a aba não voltar sozinha a esse script depois."""
        id_script, self._script_pedido = self._script_pedido, ""
        return id_script

    def escolher_pasta(self):
        """Abre o seletor de pastas do Windows; devolve o caminho escolhido, ou "" se a pessoa cancelar."""
        escolhidas = self._janela.create_file_dialog(webview.FileDialog.FOLDER) if self._janela else None
        return escolhidas[0] if escolhidas else ""

    def estado(self):
        return self._servico.estado()

    def definir_pasta_script(self, id_script, caminho):
        return self._servico.definir_pasta_script(id_script, caminho)

    def salvar_codigo_script(self, id_script, codigo):
        return self._servico.salvar_codigo_script(id_script, codigo)

    def preparar_python(self):
        return self._servico.preparar_python()

    def instalar_biblioteca(self, id_script, modulo):
        return self._servico.instalar_biblioteca(id_script, modulo)

    def abrir_pagina_pacote(self, id_script, modulo):
        return self._servico.abrir_pagina_pacote(id_script, modulo)

    def agendar_script(self, id_script, hora):
        return self._servico.agendar_script(id_script, hora)

    def agendar_unico_script(self, id_script, quantidade, unidade):
        return self._servico.agendar_unico_script(id_script, quantidade, unidade)

    def cancelar_unico_script(self, id_script):
        return self._servico.cancelar_unico_script(id_script)

    def pausar_agenda_script(self, id_script, pausar):
        return self._servico.pausar_agenda_script(id_script, pausar)

    def remover_agenda_script(self, id_script):
        return self._servico.remover_agenda_script(id_script)

    def aprovar_script(self, id_script, nome):
        return self._servico.aprovar_script(id_script, nome)

    def desaprovar_script(self, id_script):
        return self._servico.desaprovar_script(id_script)

    def executar_script(self, id_script):
        return self._servico.executar_script(id_script)

    def copiar_script(self, id_script):
        return self._servico.copiar_script(id_script)

    def apagar_script(self, id_script):
        return self._servico.apagar_script(id_script)
