"""Configurador de assistentes: criar assistentes novos e ajustar os existentes, sem mexer em código.

O serviço não conhece a página: recebe e devolve dados simples (os mesmos do arquivo .json do assistente).
"""
import logging
from dataclasses import replace

from merlin.ia.criador_assistente import CriadorAssistente
from merlin.ia.frases import TAMANHO_MINIMO_ESCRITA, motivo_recusa
from merlin.personalidades import EMBUTIDAS, PERSONALIDADES, armazenamento, modelo, personalidade_padrao, recarregar
from merlin.personalidades.armazenamento import DadosInvalidos
from merlin.voz.catalogo import todas_as_vozes

logger = logging.getLogger(__name__)

# Palavras do dia a dia: como palavra de chamada, ativam o assistente no meio de uma conversa qualquer
PALAVRAS_COMUNS = {"sexta", "segunda", "terça", "quarta", "quinta", "sábado", "domingo", "casa", "hoje", "agora",
                   "ajuda", "amigo", "amiga", "chefe", "você", "voce", "assistente", "ok", "olá", "ola", "oi",
                   "bom", "boa", "dia", "noite", "tarde", "sim", "não", "nao"}


class ServicoAssistentes:
    def __init__(self, preferencias, canal, cliente_ia, trocar_personalidade, pasta=None):
        self._preferencias = preferencias
        self._canal = canal
        self._criador = CriadorAssistente(cliente_ia)
        self._trocar_personalidade = trocar_personalidade  # a mesma troca das configurações (limpa a memória etc.)
        self._pasta = pasta  # None = assistentes_citizentech/ (o padrão do armazenamento)

    # --- leitura
    def listar(self) -> list[dict]:
        atual = self._preferencias.personalidade.id
        return [{"id": p.id, "nome": p.nome, "embutido": p.id in EMBUTIDAS, "ajustado": self._ajustado(p.id),
                 "atual": p.id == atual} for p in PERSONALIDADES.values()]

    def opcoes(self) -> dict:
        return {"vozes": [{"rotulo": r, "id": i} for r, i in todas_as_vozes().items()],
                "sons": list(armazenamento.SONS), "visuais": list(armazenamento.VISUAIS)}

    def abrir(self, identificador: str) -> dict:
        p = PERSONALIDADES.get(identificador)
        if p is None:
            return {"erro": "Esse assistente não existe mais."}
        return {**armazenamento.para_dados(p), "embutido": p.id in EMBUTIDAS, "ajustado": self._ajustado(p.id)}

    def novo(self) -> dict:
        return {**modelo.novo_assistente(), "embutido": False, "ajustado": False}

    # --- IA
    def sugerir(self, nome: str, descricao: str) -> dict:
        if not nome.strip() or not descricao.strip():
            return {"erro": "Para a IA sugerir, preencha o nome e conte quem ele é em uma ou duas frases."}
        try:
            return self._criador.sugerir(nome.strip(), descricao.strip())
        except Exception as erro:
            logger.warning("[ASSISTENTES] A IA não conseguiu sugerir: %s", erro)
            return {"erro": "A IA não conseguiu sugerir agora. Verifique se o Ollama está aberto e tente de novo."}

    # --- gravação
    def salvar(self, dados: dict) -> dict:
        dados = dict(dados)
        identificador = dados.get("id") or self._id_livre(armazenamento.id_para(dados.get("nome", "")))
        dados["id"] = identificador
        if identificador not in EMBUTIDAS:
            # As instruções não aparecem na tela: são remontadas do nome e do jeito a cada vez que salva.
            # O original (Merlin) mantém as suas, escritas à mão no arquivo deles.
            if not str(dados.get("prompt_conversa", "")).strip() and dados.get("nome", "").strip():
                jeito = modelo.extrair_jeito(dados["nome"], dados.get("jeito") or dados.get("descricao")
                                             or dados.get("contexto") or "")
                dados["prompt_conversa"] = modelo.prompt_conversa(dados["nome"].strip(), jeito)
            modelo.montar_instrucoes(dados)  # depois: a base é o texto da conversa
        try:
            p = armazenamento.de_dados(dados, EMBUTIDAS.get(identificador))
            self._conferir(p)
        except DadosInvalidos as erro:
            return {"erro": str(erro)}
        armazenamento.salvar(p, *self._pasta_args())
        self._recarregar()
        return {"id": identificador, "avisos": self._avisos(p)}

    def restaurar(self, identificador: str) -> dict:
        if identificador not in EMBUTIDAS:
            return {"erro": "Só os assistentes originais têm um padrão para restaurar."}
        armazenamento.apagar(identificador, *self._pasta_args())
        self._recarregar()
        return {"id": identificador}

    def excluir(self, identificador: str) -> dict:
        if identificador in EMBUTIDAS:
            return {"erro": "Os assistentes originais não podem ser excluídos (só restaurados ao padrão)."}
        armazenamento.apagar(identificador, *self._pasta_args())
        if self._preferencias.personalidade.id == identificador:
            self._trocar_personalidade(personalidade_padrao().id)
        self._recarregar()
        return {}

    def usar(self, identificador: str) -> dict:
        if identificador not in PERSONALIDADES:
            return {"erro": "Salve o assistente antes de usá-lo."}
        self._trocar_personalidade(identificador)
        return {}

    # --- apoio
    def _conferir(self, p) -> None:
        """O que só dá para conferir aqui: vozes existentes e frases que passam no filtro de fala."""
        if p.voz_padrao not in todas_as_vozes().values():
            raise DadosInvalidos("Escolha uma voz da lista.")
        ocupadas = {palavra: outro.nome for outro in PERSONALIDADES.values() if outro.id != p.id
                    for palavra in outro.palavras_ativacao}
        repetidas = [f"{palavra} ({ocupadas[palavra]})" for palavra in p.palavras_ativacao if palavra in ocupadas]
        if repetidas:
            raise DadosInvalidos(f"Palavras de chamada já usadas por outro assistente: {', '.join(repetidas)}.")
        for parte, rotulo in (("saudacao", "saudação"), ("despedida", "despedida")):
            # "sempre dizer o nome" vale para as frases inventadas na hora; as escritas pela pessoa são livres
            conjunto = replace(getattr(p, parte), exige_nome=None)
            for frase in conjunto.reservas:
                motivo = motivo_recusa(frase, conjunto, TAMANHO_MINIMO_ESCRITA)
                if motivo:
                    raise DadosInvalidos(f"Esta {rotulo} {motivo}: \"{frase}\"")

    @staticmethod
    def _avisos(p) -> list[str]:
        comuns = [palavra for palavra in p.palavras_ativacao if palavra in PALAVRAS_COMUNS]
        if comuns:
            return [f"Cuidado: {', '.join(comuns)} é palavra do dia a dia e pode chamar o assistente sem querer."]
        return []

    def _ajustado(self, identificador) -> bool:
        if identificador not in EMBUTIDAS:
            return False
        pasta = self._pasta or armazenamento.PASTA_ASSISTENTES
        return (pasta / f"{identificador}.json").is_file()

    def _id_livre(self, base: str) -> str:
        identificador, n = base, 2
        while identificador in PERSONALIDADES or identificador in EMBUTIDAS:
            identificador, n = f"{base}_{n}", n + 1
        return identificador

    def _pasta_args(self):
        return (self._pasta,) if self._pasta else ()

    def _recarregar(self):
        recarregar(*self._pasta_args())
        self._canal.personalidade()  # a janela principal se ajusta se o assistente atual mudou


class ApiAssistentes:
    """Funções que a página pode chamar (atributos privados: o pywebview expõe os públicos)."""

    def __init__(self, servico):
        self._servico = servico

    def listar(self):
        return {"assistentes": self._servico.listar(), "opcoes": self._servico.opcoes()}

    def abrir(self, identificador):
        return self._servico.abrir(identificador)

    def novo(self):
        return self._servico.novo()

    def sugerir(self, nome, descricao):
        return self._servico.sugerir(nome, descricao)

    def salvar(self, dados):
        return self._servico.salvar(dados)

    def restaurar(self, identificador):
        return self._servico.restaurar(identificador)

    def excluir(self, identificador):
        return self._servico.excluir(identificador)

    def usar(self, identificador):
        return self._servico.usar(identificador)

