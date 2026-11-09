"""Aba Skills: mostra tudo o que o assistente sabe fazer, testa como uma frase seria entendida (sem executar nada)
e deixa editar o título, a descrição e os exemplos de cada skill. As regras e a ação continuam no código."""
import time

from merlin import habilidades as registro
from merlin.config import LIMITE_UMA_ETAPA, PASTA_SKILLS
from merlin.habilidades import HABILIDADES, NOME_CONVERSAR, ajustes, atuais, grupos_em_uso
from merlin.ia.intencoes import ClassificadorIntencao


class ServicoPainelHabilidades:
    def __init__(self, cliente_ia, pasta=PASTA_SKILLS):
        self._pasta = pasta
        self._classificador = ClassificadorIntencao(cliente_ia)

    @property
    def _habilidades(self):
        return atuais()

    @property
    def _titulos(self) -> dict:
        return {h.nome: h.titulo_legivel for h in self._habilidades}

    def salvar(self, nome: str, dados: dict) -> dict:
        original = next((h for h in HABILIDADES if h.nome == nome), None)
        if original is None:
            return {"erro": "Essa skill não existe."}
        try:
            limpos = ajustes.conferir(original, dados or {}, {h.nome for h in HABILIDADES})
        except ajustes.AjusteInvalido as erro:
            return {"erro": str(erro)}
        ajustes.salvar(nome, limpos, self._pasta)
        registro.recarregar(self._pasta)
        return {"ok": True}

    def ligar(self, nome: str, ligada: bool) -> dict:
        if nome == NOME_CONVERSAR:
            return {"erro": "Conversar não pode ser desligada: é para onde vai todo pedido que não é outra skill."}
        if nome not in {h.nome for h in HABILIDADES}:
            return {"erro": "Essa skill não existe."}
        nomes = ajustes.desligadas(self._pasta)
        (nomes.discard if ligada else nomes.add)(nome)
        ajustes.salvar_desligadas(nomes, self._pasta)
        registro.recarregar(self._pasta)
        return {"ok": True}

    def restaurar(self, nome: str) -> dict:
        ajustes.apagar(nome, self._pasta)
        registro.recarregar(self._pasta)
        return {"ok": True}

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
            "opcoes": [{"nome": h.nome, "titulo": h.titulo_legivel} for h in self._habilidades],
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
            "resumo": h.resumo or h.descricao, "icone": h.icone,
            "ligada": registro.esta_ligada(h.nome), "pode_desligar": h.nome != NOME_CONVERSAR,
            "ajustada": (self._pasta / f"{h.nome}.json").is_file(),
            "todos_exemplos": [{"frase": e.frase, "alvo": e.alvo, "intencao": e.intencao, "campos": dict(e.campos)}
                               for e in h.exemplos],
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

    def salvar(self, nome, dados):
        return self._servico.salvar(nome, dados)

    def restaurar(self, nome):
        return self._servico.restaurar(nome)

    def ligar(self, nome, ligada):
        return self._servico.ligar(nome, ligada)

