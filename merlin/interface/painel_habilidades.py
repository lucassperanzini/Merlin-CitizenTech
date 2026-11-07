"""Painel de habilidades: mostra tudo o que o assistente sabe fazer e deixa testar como uma frase seria entendida.

Só leitura: o painel lê as habilidades registradas (merlin/habilidades/) e, no teste, só classifica a frase.
Nenhuma ação é executada.
"""
import time

from merlin.config import LIMITE_UMA_ETAPA
from merlin.habilidades import HABILIDADES, NOME_CONVERSAR, grupos_em_uso
from merlin.ia.intencoes import ClassificadorIntencao


class ServicoPainelHabilidades:
    def __init__(self, cliente_ia, habilidades=HABILIDADES):
        self._habilidades = tuple(habilidades)
        self._titulos = {h.nome: h.titulo_legivel for h in self._habilidades}
        self._classificador = ClassificadorIntencao(cliente_ia, self._habilidades)

    def listar(self) -> dict:
        grupos = []
        for grupo in grupos_em_uso(self._habilidades):
            habilidades = [self._descrever(h) for h in self._habilidades if h.grupo == grupo]
            grupos.append({"nome": grupo.nome, "descricao": grupo.descricao, "habilidades": habilidades})
        return {
            "grupos": grupos,
            "total": len(self._habilidades),
            "modo": "duas etapas (primeiro o grupo, depois a habilidade)" if self._classificador.duas_etapas
                    else "uma etapa (a IA escolhe entre todas de uma vez)",
            "limite_uma_etapa": LIMITE_UMA_ETAPA,
        }

    def testar(self, frase: str) -> dict:
        """Como a frase seria entendida. Não executa nada."""
        frase = (frase or "").strip()
        if not frase:
            return {"erro": "Escreva uma frase para testar."}
        inicio = time.perf_counter()
        try:
            intencao = self._classificador.classificar(frase)
        except Exception:
            return {"erro": "Não consegui falar com a IA. Verifique se o Ollama está aberto."}
        modelo = intencao.resposta_modelo or {}
        return {
            "habilidade": intencao.tipo.value,
            "titulo": self._titulos.get(intencao.tipo.value, intencao.tipo.value),
            "alvo": intencao.alvo,
            "campos": {k: v for k, v in intencao.campos.items() if v},
            "ia_escolheu": self._titulos.get(modelo.get("intencao"), modelo.get("intencao", "")),
            "grupo": modelo.get("grupo", ""),
            "motivo_regra": intencao.motivo_regra,
            "tempo": round(time.perf_counter() - inicio, 2),
        }

    def _descrever(self, h) -> dict:
        exemplos, contraexemplos = [], []
        for e in h.exemplos:
            if e.intencao is None:
                exemplos.append({"frase": e.frase, "alvo": e.alvo, "campos": {k: v for k, v in e.campos.items() if v}})
            else:
                contraexemplos.append({"frase": e.frase, "vira": self._titulos.get(e.intencao, e.intencao)})
        return {
            "nome": h.nome, "titulo": h.titulo_legivel, "descricao": h.descricao,
            "mexe_no_computador": h.mexe_no_computador,
            # onde ela age: no computador, no próprio assistente (despedir, desligar, ajustes) ou em lugar nenhum
            "age": "computador" if h.mexe_no_computador else ("fala" if h.nome == NOME_CONVERSAR else "assistente"),
            "campos": [{"nome": c.nome, "descricao": c.descricao} for c in h.campos],
            "exemplos": exemplos, "contraexemplos": contraexemplos, "regras": list(h.regras_resumo),
        }


class ApiPainelHabilidades:
    """Funções que a página pode chamar (atributos privados: o pywebview expõe os públicos)."""

    def __init__(self, servico):
        self._servico = servico

    def listar(self):
        return self._servico.listar()

    def testar(self, frase):
        return self._servico.testar(frase)

