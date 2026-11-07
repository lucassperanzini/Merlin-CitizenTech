"""A IA local sugere a personalidade de um assistente a partir do nome e de uma descrição curta da pessoa.

Ela só sugere: tudo vai para o configurador, onde a pessoa revisa e edita antes de salvar. As frases prontas
passam pelo mesmo filtro das frases geradas na hora (tamanho, pontuação, palavrões).
"""
import json
import logging

from merlin.ia.frases import TAMANHO_MINIMO_ESCRITA, motivo_recusa
from merlin.personalidades.armazenamento import ajustar_frase
from merlin.personalidades.base import ConjuntoFrases
from merlin.personalidades import modelo

logger = logging.getLogger(__name__)

QUANTIDADE_FRASES = 6  # um pouco mais que o mínimo, porque algumas podem ser recusadas pelo filtro

PROMPT = """Você vai criar a personalidade de um assistente pessoal por voz, que fala português do Brasil.
Nome do assistente: {nome}
Como a pessoa o descreveu: {descricao}

Preencha:
- jeito: duas ou três frases, falando com o assistente ("Você é...", "Trate a pessoa por..."), descrevendo o temperamento, o estilo das respostas e como ele chama a pessoa. Sem regras técnicas e sem listar gírias (elas vão em expressoes).
- expressoes: até 6 gírias ou bordões que ele usa, sem palavrões, cada um no formato "expressão — quando usar". Só expressões que combinem com a descrição; nenhuma, se o personagem não tiver gírias.
- apresentacao: uma frase curta que ele diz quando é escolhido, citando o próprio nome.
- variacoes_do_nome: até 6 jeitos como um reconhecedor de voz pode escrever o nome dele errado, em minúsculas (ex.: para "Jarvis": jarves, javis, jervis).
- temas: 8 imagens ou assuntos ligados ao personagem, de uma a três palavras cada, para variar as falas.
- saudacoes: {quantidade} saudações curtas e diferentes, que ele diz ao ser chamado, oferecendo ajuda.
- despedidas: {quantidade} despedidas curtas, sem perguntas, dizendo que volta quando for chamado.

Todas as frases: português correto, no estilo do personagem, cada uma com no máximo 110 caracteres, terminando com ponto final, de exclamação ou de interrogação, sem aspas, emojis ou palavrões."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "jeito": {"type": "string"},
        "apresentacao": {"type": "string"},
        "variacoes_do_nome": {"type": "array", "items": {"type": "string"}},
        "expressoes": {"type": "array", "items": {"type": "string"}},
        "temas": {"type": "array", "items": {"type": "string"}},
        "saudacoes": {"type": "array", "items": {"type": "string"}},
        "despedidas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["jeito", "apresentacao", "variacoes_do_nome", "expressoes", "temas", "saudacoes", "despedidas"],
}


class CriadorAssistente:
    def __init__(self, cliente):
        self._cliente = cliente

    def sugerir(self, nome: str, descricao: str) -> dict:
        """Devolve os dados de um assistente completo, prontos para a pessoa revisar."""
        resposta = self._cliente.perguntar(
            [{"role": "user", "content": PROMPT.format(nome=nome, descricao=descricao, quantidade=QUANTIDADE_FRASES)}],
            formato=ESQUEMA,
            opcoes={"temperature": 0.7},
        )
        sugestao = json.loads(resposta)
        jeito = str(sugestao.get("jeito", "")).strip() or descricao
        dados = modelo.novo_assistente(nome, jeito)
        dados["descricao"] = descricao
        dados["jeito"] = jeito
        apresentacao = _frases([sugestao.get("apresentacao")], ConjuntoFrases("", (), ()))
        if apresentacao:
            dados["apresentacao"] = apresentacao[0]
        variacoes = [str(v).strip().lower() for v in sugestao.get("variacoes_do_nome", []) if len(str(v).strip()) >= 3]
        dados["palavras_ativacao"] = list(dict.fromkeys([nome.lower(), *variacoes]))
        temas = [str(t).strip() for t in sugestao.get("temas", []) if str(t).strip()][:10]
        expressoes = [" ".join(str(e).split()) for e in sugestao.get("expressoes", []) if str(e).strip()]
        dados["expressoes"] = [e for e in dict.fromkeys(expressoes) if len(e) <= 80 and "{" not in e][:6]
        for parte, chave in (("saudacao", "saudacoes"), ("despedida", "despedidas")):
            regras = dados[parte]
            conjunto = ConjuntoFrases("", (), (), sem_perguntas=regras.get("sem_perguntas", False),
                                      tamanho_maximo=regras.get("tamanho_maximo", 170))
            frases = _frases(sugestao.get(chave, []), conjunto)
            dados[parte].update(temas=temas, reservas=frases, exemplos=frases[:3])  # mesmos temas nos dois campos
        return dados


def _frases(itens, conjunto) -> list[str]:
    """Só as frases que também passariam ao salvar: a sugestão nunca traz algo que depois é recusado."""
    frases = []
    for item in itens or []:
        texto = ajustar_frase(str(item or ""))
        motivo = motivo_recusa(texto, conjunto, TAMANHO_MINIMO_ESCRITA) if texto else "vazia"
        if not motivo and texto not in frases:
            frases.append(texto)
        elif texto:
            logger.info("[ASSISTENTES] Frase sugerida recusada (%s): %s", motivo, texto)
    return frases
