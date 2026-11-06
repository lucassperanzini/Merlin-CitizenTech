"""Textos enviados ao modelo. Ficam separados para poderem ser ajustados sem mexer na lógica.

O prompt de intenções é montado a partir das habilidades (merlin/habilidades/), e os textos de cada
personalidade ficam no arquivo dela (merlin/personalidades/)."""

PROMPT_ESCOLHA_BOTAO = """A pessoa pediu a um assistente de voz para clicar em um botão, dizendo o nome do jeito dela. A fala pode ter erros de transcrição.

Botões que existem na janela:
{botoes}

Escolha o botão que ela mais provavelmente quis, pelo sentido e por sinônimos (por exemplo: gravar é salvar, X é fechar, voltar é anterior).
Se nenhum botão servir para o que ela pediu, responda nenhum. Não escolha um botão só por ter letras parecidas."""

PROMPT_DIVISAO = """Separe a frase dita a um assistente de voz nas tarefas independentes que ela pede, na ordem em que devem ser feitas.

Regras:
- Use somente palavras que a pessoa disse. Copie cada tarefa como foi dita, sem resumir nem inventar.
- Se um verbo vale para duas coisas, repita o verbo em cada tarefa.
- "e" dentro do assunto de um pedido não separa tarefas: nomes, textos a escrever e termos de pesquisa ficam inteiros.
- Agradecimentos e cumprimentos junto de um pedido não são tarefas: deixe só o pedido.
- Na dúvida, devolva a frase inteira como uma tarefa só.

Exemplos:
"abre o excel e pesquisa o preço do ouro" -> {"tarefas": ["abre o excel", "pesquisa o preço do ouro"]}
"abre o paint e o outlook" -> {"tarefas": ["abre o paint", "abre o outlook"]}
"fecha o word e depois abre o teams" -> {"tarefas": ["fecha o word", "abre o teams"]}
"cria uma pasta contas, em seguida abre o paint" -> {"tarefas": ["cria uma pasta contas", "abre o paint"]}
"obrigado e agora abre o teams" -> {"tarefas": ["abre o teams"]}
"pesquisa pão e queijo" -> {"tarefas": ["pesquisa pão e queijo"]}
"cria um arquivo lembrete escrito pagar a luz e a água" -> {"tarefas": ["cria um arquivo lembrete escrito pagar a luz e a água"]}
"cria uma pasta contas e boletos" -> {"tarefas": ["cria uma pasta contas e boletos"]}
"qual a diferença entre sol e lua" -> {"tarefas": ["qual a diferença entre sol e lua"]}
"valeu e até amanhã" -> {"tarefas": ["valeu e até amanhã"]}"""

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
