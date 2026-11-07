"""Textos-modelo para os assistentes criados no configurador.

O "jeito" (como o assistente é e trata a pessoa) vem da descrição dada por ela; o resto é fixo e igual para
todos: são as regras que mantêm as respostas curtas, faladas e sem fingir que fez algo.
As chaves duplas {{tema}}, {{exemplo}} e {{evitar}} viram {tema} etc., preenchidos a cada saudação ou despedida.
"""


def _limpo(texto: str) -> str:
    """Chaves no texto do usuário quebrariam o preenchimento de {tema}, {exemplo} e {evitar}."""
    return " ".join(str(texto).replace("{", "(").replace("}", ")").split())


REGRAS_CONVERSA = ("Responda de forma curta e direta em português do Brasil, em frases simples que soem bem faladas "
                   "(sem markdown, listas ou emojis). Se não souber algo, diga que não sabe. "
                   "Nesta conversa você só responde: não abre, fecha nem controla nada. "
                   "Nunca diga que fez ou vai fazer uma ação; se pedirem uma, diga que não consegue fazer isso.")


def _inicio(nome: str) -> str:
    return f"Você é {_limpo(nome)}, um assistente pessoal por voz."


def prompt_conversa(nome: str, jeito: str) -> str:
    return f"{_inicio(nome)} {_limpo(jeito)} {REGRAS_CONVERSA}"


def extrair_jeito(nome: str, texto: str) -> str:
    """O jeito do assistente sem o começo ("Você é X, um assistente…") nem as regras fixas, que já entram
    sozinhos nas instruções. Evita repetir tudo duas vezes quando o texto da conversa é usado como base."""
    jeito = " ".join(str(texto or "").split())
    for repetido in (_inicio(nome), REGRAS_CONVERSA):
        jeito = jeito.replace(repetido, " ")
    return " ".join(jeito.split())


SEM_TRATAMENTOS = " Não use tratamentos como senhor, senhora ou mestre."


def prompt_saudacao(nome: str, jeito: str, diz_nome: bool = False, sem_tratamentos: bool = False) -> str:
    return (f"{_inicio(nome)} {_limpo(jeito)} Alguém acaba de chamar você. Escreva uma saudação falada em "
            "português do Brasil correto e natural, com uma ou duas frases curtas, no jeito do personagem. "
            "Comece com uma imagem ligada a este tema: {tema}. Mostre que está pronto e ofereça ajuda."
            + (f" Na mesma fala, diga que você é {_limpo(nome)}." if diz_nome else "")
            + (SEM_TRATAMENTOS if sem_tratamentos else "")
            + " Inspire-se no ritmo deste exemplo, sem copiar as palavras: {exemplo} "
            "Responda só com a saudação, sem aspas, emojis ou formatação. "
            "Não repita as saudações recentes:\n{evitar}")


def prompt_despedida(nome: str, jeito: str, sem_tratamentos: bool = False) -> str:
    return (f"{_inicio(nome)} {_limpo(jeito)} A pessoa acaba de dispensar você, mas você continua por perto, em "
            "espera, e volta quando ela chamar você. Escreva uma despedida falada em português "
            "do Brasil correto e natural, com uma ou duas frases curtas, no jeito do personagem. Fale de você na "
            "primeira pessoa, contando o que vai fazer agora, com uma imagem ligada a este tema: {tema}. "
            "Na segunda frase, diga com palavras próprias que volta quando for chamado. Não faça perguntas."
            + (SEM_TRATAMENTOS if sem_tratamentos else "")
            + " Inspire-se no ritmo deste exemplo, sem copiar as palavras: {exemplo} "
            "Responda só com a despedida, sem aspas, emojis ou formatação. "
            "Não repita as despedidas recentes:\n{evitar}")


def montar_instrucoes(dados: dict) -> dict:
    """Remonta as instruções das saudações e despedidas a partir do nome, do jeito e das duas opções
    ("sempre dizer o nome" e "sem senhor/mestre", guardadas nos próprios conjuntos de frases).
    Os assistentes do configurador passam por aqui a cada vez que são salvos: mudar o nome atualiza tudo."""
    nome = dados.get("nome", "")
    # A base é o que a pessoa escreveu em "Como ele conversa" (sem o começo e as regras fixas);
    # sem isso, o jeito sugerido pela IA; por último, a descrição
    jeito = (extrair_jeito(nome, dados.get("prompt_conversa", "")) or extrair_jeito(nome, dados.get("jeito", ""))
             or extrair_jeito(nome, dados.get("descricao", "")))
    dados["jeito"] = jeito
    saudacao = dados.get("saudacao", {})
    diz_nome = bool(saudacao.get("exige_nome"))
    sem_tratamentos = any(dados.get(p, {}).get("proibir_tratamentos") for p in ("saudacao", "despedida"))
    prompts = {"saudacao": prompt_saudacao(nome, jeito, diz_nome, sem_tratamentos),
               "despedida": prompt_despedida(nome, jeito, sem_tratamentos)}
    for parte, prompt in prompts.items():
        conjunto = {**dados.get(parte, {}), "prompt": prompt, "proibir_tratamentos": sem_tratamentos}
        # Exemplos de ritmo para o {exemplo}: as primeiras frases prontas
        conjunto["exemplos"] = list(conjunto.get("reservas") or [])[:3]
        dados[parte] = conjunto
    dados["saudacao"]["exige_nome"] = nome.lower() if diz_nome else ""
    return dados


def novo_assistente(nome: str = "", jeito: str = "") -> dict:
    """Os dados de um assistente novo, ainda sem as frases (que a IA sugere ou a pessoa escreve)."""
    return {
        "id": "", "nome": nome, "descricao": "", "contexto": "", "jeito": jeito,
        "palavras_ativacao": [nome.lower()] if nome else [],
        "voz_padrao": "pt_BR-faber-medium", "visual": "esfera", "cor": "", "som": "Digital",
        "apresentacao": f"{nome} às suas ordens." if nome else "", "dica_vocabulario": "",
        "prompt_conversa": prompt_conversa(nome, jeito) if nome else "",  # vazio: montado ao salvar
        "saudacao": {"prompt": prompt_saudacao(nome, jeito), "temas": [], "reservas": [], "exemplos": []},
        "despedida": {"prompt": prompt_despedida(nome, jeito), "temas": [], "reservas": [], "exemplos": [],
                      "sem_perguntas": True, "tamanho_maximo": 120},
    }
