"""Descobre o que a pessoa quer. A IA responde a intenção e o alvo; as regras de cada habilidade têm a palavra final.

Tudo o que é específico de um pedido (descrição, exemplos, regras) fica no arquivo da habilidade, em
merlin/habilidades/. Aqui só há o mecanismo, que funciona igual para qualquer número de habilidades.

Com poucas habilidades, a IA escolhe entre todas de uma vez. Com muitas (ver LIMITE_UMA_ETAPA no config), escolhe
em duas etapas: primeiro o grupo (programas, tela, internet…) e depois a intenção dentro dele. Assim cada pergunta
à IA continua curta e com poucas opções parecidas, mesmo que o assistente aprenda muitas coisas.
"""
import json
from dataclasses import dataclass, field
from enum import Enum

from merlin.config import LIMITE_UMA_ETAPA
from merlin.habilidades import HABILIDADES, NOME_CONVERSAR
from merlin.habilidades.base import Leitura
from merlin.ia import prompt_intencao

# Gerado a partir das habilidades: TipoIntencao.ABRIR_PROGRAMA, TipoIntencao.CONVERSAR, ...
TipoIntencao = Enum("TipoIntencao", [(h.nome.upper(), h.nome) for h in HABILIDADES], type=str)

# Pedidos que fazem algo no computador. Conversa, despedida e encerramento não entram aqui.
ACOES_NO_COMPUTADOR = frozenset(TipoIntencao(h.nome) for h in HABILIDADES if h.mexe_no_computador)

MAX_CORRECOES = 4  # uma regra pode levar a outra habilidade, que tem as próprias regras; isto evita ciclos


@dataclass(frozen=True)
class Intencao:
    tipo: TipoIntencao
    alvo: str  # em PESQUISAR_WEB, é o termo a pesquisar
    comando: str  # a frase original, já sem o nome do assistente
    local: str = ""  # em CLICAR_BOTAO, o programa onde clicar; vazio = a janela em uso
    # Para a janela de raciocínio: o que o modelo respondeu e, se uma regra do código mudou a decisão, por quê
    resposta_modelo: dict = field(default_factory=dict, compare=False)
    motivo_regra: str = field(default="", compare=False)
    campos: dict = field(default_factory=dict, compare=False)  # dados extras declarados pela habilidade


class ClassificadorIntencao:
    def __init__(self, cliente, habilidades=HABILIDADES, duas_etapas: bool | None = None):
        """duas_etapas=None decide sozinho pelo número de habilidades."""
        self._cliente = cliente
        self._habilidades = tuple(habilidades)
        self._por_nome = {h.nome: h for h in self._habilidades}
        self.duas_etapas = len(self._habilidades) > LIMITE_UMA_ETAPA if duas_etapas is None else duas_etapas
        self._uma_etapa = self._preparar(self._habilidades)
        if self.duas_etapas:
            self._prompt_grupos = prompt_intencao.montar_prompt_grupos(self._habilidades)
            self._esquema_grupos = prompt_intencao.montar_esquema_grupos(self._habilidades)
            self._por_grupo = {g.nome: self._preparar(prompt_intencao.habilidades_do_grupo(self._habilidades, g.nome))
                               for g in prompt_intencao.grupos_em_uso(self._habilidades)}

    def classificar(self, comando: str) -> Intencao:
        """Resposta inválida do modelo vira CONVERSAR, para nunca executar uma ação por engano."""
        prompt, esquema, extra = self._uma_etapa[0], self._uma_etapa[1], {}
        if self.duas_etapas:
            grupo = self._escolher_grupo(comando)
            extra = {"grupo": grupo}
            if grupo is None:
                return Intencao(TipoIntencao.CONVERSAR, "", comando, motivo_regra="o modelo deu uma resposta inválida")
            habilidades_do_grupo = self._por_grupo[grupo][2]
            if [h.nome for h in habilidades_do_grupo] == [NOME_CONVERSAR]:
                return Intencao(TipoIntencao.CONVERSAR, "", comando, resposta_modelo=extra)  # nada a perguntar
            prompt, esquema, _ = self._por_grupo[grupo]
        resposta = self._perguntar(prompt, esquema, comando)
        try:
            dados = json.loads(resposta)
            nome = str(dados.get("intencao", NOME_CONVERSAR))
            if nome not in self._por_nome:
                raise ValueError(nome)
            alvo = str(dados.get("alvo", "")).strip()
            campos = {c: str(v).strip() for c, v in dados.items() if c not in ("alvo", "intencao")}
        except (ValueError, AttributeError):
            return Intencao(TipoIntencao.CONVERSAR, "", comando, motivo_regra="o modelo deu uma resposta inválida")
        return self._aplicar_regras(Leitura(nome, alvo, campos, comando), {**extra, **dados})

    def _escolher_grupo(self, comando) -> str | None:
        try:
            grupo = json.loads(self._perguntar(self._prompt_grupos, self._esquema_grupos, comando)).get("grupo")
        except (ValueError, AttributeError):
            return None
        return grupo if grupo in self._por_grupo else None

    def _perguntar(self, prompt, esquema, comando) -> str:
        return self._cliente.perguntar(
            [{"role": "system", "content": prompt}, {"role": "user", "content": comando}],
            formato=esquema,
            opcoes={"temperature": 0},
        )

    def _aplicar_regras(self, leitura: Leitura, resposta_modelo: dict) -> Intencao:
        """Cada habilidade confere a decisão com a própria regra; uma correção pode passar para outra habilidade."""
        motivos = []
        for _ in range(MAX_CORRECOES):
            habilidade = self._por_nome[leitura.intencao]
            correcao = habilidade.regra(leitura) if habilidade.regra else None
            if correcao is None:
                break
            if correcao.motivo:
                motivos.append(correcao.motivo)
            mudou = correcao.intencao != leitura.intencao
            leitura = Leitura(correcao.intencao, leitura.alvo if correcao.alvo is None else correcao.alvo,
                              {**leitura.campos, **correcao.campos}, leitura.comando)
            if not mudou:
                break
        final = self._por_nome[leitura.intencao]
        # Só ficam os dados que a habilidade final declara: um "local" sobrando de outra não vale
        campos = {c.nome: leitura.campos.get(c.nome, "") for c in final.campos}
        return Intencao(TipoIntencao(final.nome), leitura.alvo, leitura.comando, campos.get("local", ""),
                        resposta_modelo=resposta_modelo, motivo_regra="; ".join(motivos), campos=campos)

    def _preparar(self, habilidades):
        habilidades = list(habilidades)
        return prompt_intencao.montar_prompt(habilidades), prompt_intencao.montar_esquema(habilidades), habilidades
