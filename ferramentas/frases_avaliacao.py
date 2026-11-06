"""Frases de avaliação do classificador de intenções, com a resposta certa de cada uma.

Nenhuma delas está nos exemplos dos prompts: assim a avaliação mede se a IA entende, não se decorou.
Ao criar uma habilidade, acrescente aqui frases dela (e frases parecidas que NÃO devem ativá-la).
Formato: (frase, intenção esperada, alvo esperado ou None para não conferir o alvo).
"""

FRASES = [
    # dispensar
    ("valeu, por hoje é só", "dispensar", None),
    ("pode descansar agora", "dispensar", None),
    ("já resolvi, obrigado", "dispensar", None),
    ("tchau", "dispensar", None),
    ("some daqui", "dispensar", None),
    # encerrar
    ("desliga você mesmo de vez", "encerrar", None),
    ("encerra o assistente por completo", "encerrar", None),
    ("para de escutar e fecha tudo de você", "encerrar", None),
    # fechar_programa
    ("fecha o spotify", "fechar_programa", "spotify"),
    ("encerra o excel", "fechar_programa", "excel"),
    ("sai do discord", "fechar_programa", "discord"),
    ("mata o chrome", "fechar_programa", "chrome"),
    # abrir_programa
    ("abre a calculadora", "abrir_programa", "calculadora"),
    ("inicia o spotify", "abrir_programa", "spotify"),
    ("executa o bloco de notas", "abrir_programa", "bloco de notas"),
    ("liga o teams", "abrir_programa", "teams"),
    ("abre as configurações do windows", "abrir_programa", None),
    # pesquisar_web
    ("pesquisa o preço do dólar hoje", "pesquisar_web", "preço do dólar hoje"),
    ("procura no google como fazer pão de queijo", "pesquisar_web", None),
    ("abre o site do youtube", "pesquisar_web", None),
    ("busca notícias sobre futebol", "pesquisar_web", None),
    # clicar_botao
    ("clica em salvar", "clicar_botao", "salvar"),
    ("aperta o ok", "clicar_botao", "ok"),
    ("dá play no spotify", "clicar_botao", "play"),
    ("pausa", "clicar_botao", None),
    ("pula essa música", "clicar_botao", None),
    ("confirma", "clicar_botao", None),
    ("clica em cancelar no word", "clicar_botao", "cancelar"),
    ("seleciona a opção lembrar de mim", "clicar_botao", None),
    # abrir_configuracoes
    ("abre suas configurações", "abrir_configuracoes", None),
    ("quero mudar seus ajustes", "abrir_configuracoes", None),
    ("mostra as configurações do assistente", "abrir_configuracoes", None),
    # conversar: perguntas e pedidos que lembram ações, mas não são
    ("qual a capital da frança", "conversar", None),
    ("quanto é sete vezes oito", "conversar", None),
    ("me conta uma piada", "conversar", None),
    ("como eu fecho um programa travado", "conversar", None),
    ("o que significa o botão salvar como", "conversar", None),
    ("como abro as configurações do celular", "conversar", None),
    ("escreve um parágrafo sobre gatos", "conversar", None),
    ("liga a televisão da sala", "conversar", None),
    ("fecha a porta pra mim", "conversar", None),
    ("diz tchau pro meu irmão", "conversar", None),
    ("tudo bem com você", "conversar", None),
    ("qual o melhor navegador", "conversar", None),
    ("apaga o arquivo relatório", "conversar", None),
    ("cria uma pasta chamada fotos", "conversar", None),
    ("toca uma música animada", "conversar", None),
    ("quais botões tem nessa tela", "conversar", None),  # perguntas sobre botões não clicam
    ("o que dá pra clicar no spotify", "conversar", None),
]
