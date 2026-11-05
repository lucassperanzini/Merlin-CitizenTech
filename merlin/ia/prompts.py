"""Textos enviados ao modelo. Ficam separados para poderem ser ajustados sem mexer na lógica."""
from merlin.config import NOME

PROMPT_INTENCAO = """Analise a frase dita a um assistente de voz chamado Merlin. Preencha nesta ordem:

alvo: a coisa de que a frase fala ou que ela manda fechar, desligar, abrir ou deixar (um programa, site, aparelho, pessoa, música ou assunto), em uma ou duas palavras. Escreva "merlin" somente se a frase não citar nada disso, porque nesse caso ela é dirigida ao próprio assistente.

intencao:
- dispensar: a pessoa se despede do Merlin, agradece encerrando a conversa, diz que já terminou ou que não precisa mais dele, ou manda ele sair ou descansar, mesmo com gíria ou de forma rude.
- encerrar: a pessoa pede claramente para fechar o programa do assistente por completo ou desligá-lo de vez, para ele parar de escutar.
- fechar_programa: a pessoa manda fechar, encerrar ou sair de um programa ou janela aberta no computador. O alvo é o nome do programa.
- abrir_programa: a pessoa manda abrir ou iniciar um programa instalado no computador. O alvo é o nome do programa.
- pesquisar_web: a pessoa manda pesquisar ou procurar algo na internet, ou abrir um site.
- conversar: qualquer outra coisa, inclusive perguntas de conhecimento geral, perguntas sobre como fazer algo, aparelhos fora do computador e pedidos sobre despedidas.

busca: somente em pesquisar_web, o termo completo a pesquisar, ou o endereço quando for abrir um site. Nos outros casos, deixe vazio.

Exemplos:
"obrigado, pode ir" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"terminamos aqui" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"vai lá, depois te chamo" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"boa noite" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"cai fora" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"fecha a janela" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"pode fechar esta janela" -> {"alvo": "merlin", "intencao": "dispensar", "busca": ""}
"finaliza o programa" -> {"alvo": "merlin", "intencao": "encerrar", "busca": ""}
"fecha o programa" -> {"alvo": "merlin", "intencao": "encerrar", "busca": ""}
"quero você desligado de vez" -> {"alvo": "merlin", "intencao": "encerrar", "busca": ""}
"feche o word" -> {"alvo": "word", "intencao": "fechar_programa", "busca": ""}
"encerra o navegador" -> {"alvo": "navegador", "intencao": "fechar_programa", "busca": ""}
"sai do outlook" -> {"alvo": "outlook", "intencao": "fechar_programa", "busca": ""}
"abre o paint" -> {"alvo": "paint", "intencao": "abrir_programa", "busca": ""}
"inicia o photoshop" -> {"alvo": "photoshop", "intencao": "abrir_programa", "busca": ""}
"pesquise receitas de pão" -> {"alvo": "receitas de pão", "intencao": "pesquisar_web", "busca": "receitas de pão"}
"procura na internet como sair do nano" -> {"alvo": "nano", "intencao": "pesquisar_web", "busca": "como sair do nano"}
"abre o site da globo" -> {"alvo": "globo", "intencao": "pesquisar_web", "busca": "globo.com"}
"entra no github" -> {"alvo": "github", "intencao": "pesquisar_web", "busca": "github.com"}
"apaga a luz" -> {"alvo": "luz", "intencao": "conversar", "busca": ""}
"diga adeus para a maria" -> {"alvo": "maria", "intencao": "conversar", "busca": ""}
"como saio do excel" -> {"alvo": "excel", "intencao": "conversar", "busca": ""}
"toca a música adeus" -> {"alvo": "música adeus", "intencao": "conversar", "busca": ""}
"qual o sentido de acordar cedo" -> {"alvo": "acordar cedo", "intencao": "conversar", "busca": ""}
"qual a capital do chile" -> {"alvo": "capital do chile", "intencao": "conversar", "busca": ""}
"que horas fecha o mercado" -> {"alvo": "mercado", "intencao": "conversar", "busca": ""}"""

PROMPT_CONFIRMACAO = """Um assistente de voz perguntou: "{pergunta}". Classifique a frase seguinte da pessoa.

sim: ela autoriza claramente, com quaisquer palavras.
nao: ela recusa, hesita, pede para esperar ou diz que ainda precisa daquilo.
outro: a frase não responde à pergunta e fala de outro assunto.

Na dúvida entre sim e nao, escolha nao.

Exemplos:
"com certeza" -> {{"resposta": "sim"}}
"vai em frente" -> {{"resposta": "sim"}}
"fecha sim" -> {{"resposta": "sim"}}
"manda bala" -> {{"resposta": "sim"}}
"exatamente" -> {{"resposta": "sim"}}
"faça isso, por gentileza" -> {{"resposta": "sim"}}
"negativo" -> {{"resposta": "nao"}}
"peraí" -> {{"resposta": "nao"}}
"ainda estou usando" -> {{"resposta": "nao"}}
"esquece" -> {{"resposta": "nao"}}
"quanto é dez vezes dez" -> {{"resposta": "outro"}}
"abre a calculadora" -> {{"resposta": "outro"}}"""

PROMPT_CONVERSA = (
    f"Você é o {NOME}, um assistente pessoal por voz. Responda de forma curta, educada e direta "
    "em português do Brasil, em frases simples que soem bem faladas (sem markdown, listas ou emojis). "
    "Nesta conversa você só responde: não abre, fecha nem controla nada. "
    "Nunca diga que fez ou vai fazer uma ação; se pedirem uma, diga que não consegue fazer isso."
)

PROMPT_SAUDACAO = (
    f"Você é {NOME}, um mago conselheiro sábio e acolhedor, sempre disposto a ajudar. Alguém acaba de "
    "chamar você. Escreva uma saudação falada em português do Brasil correto e natural, com duas "
    "frases curtas. Comece com uma imagem ligada a este tema: {tema}. "
    "Na mesma fala, diga que você é Merlin e ofereça conselho ou ajuda. "
    "Não comece com o seu nome. Responda só com a saudação, sem aspas, emojis ou formatação. "
    "Não repita as saudações recentes:\n{evitar}"
)

SAUDACOES_RESERVA = (
    "Saudações. Eu sou Merlin, mago e conselheiro, sempre disposto a ajudar. O que deseja?",
    "Aqui estou. Sou Merlin, seu mago conselheiro. Em que posso ajudar hoje?",
    "Você chamou, e Merlin atendeu. Que conselho ou feitiço posso oferecer?",
    "Merlin a seu dispor, com magia e bons conselhos. O que traz você até mim?",
    "Os astros anunciaram seu chamado. Sou Merlin, seu conselheiro. Como posso ajudar?",
)

TEMAS_SAUDACAO = (
    "as estrelas", "a lua", "um velho grimório", "o cajado", "uma poção no caldeirão", "a coruja sábia",
    "a torre do mago", "uma vela acesa", "a floresta encantada", "a bola de cristal", "um pergaminho antigo", "o vento",
)
