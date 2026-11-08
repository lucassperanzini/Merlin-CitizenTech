"""Os grupos de habilidades. Uma habilidade nova escolhe um destes; um grupo novo pode ser criado aqui."""
from merlin.habilidades.base import Grupo

ASSISTENTE = Grupo("assistente", "falar com o próprio assistente: despedir-se, trocar de assistente ou abrir os ajustes dele", 10)
PROGRAMAS = Grupo("programas", "abrir ou fechar um programa do computador, ou abrir uma pasta", 20)
TELA = Grupo("tela", "mandar apertar um botão ou opção da janela de um programa: clicar, confirmar, cancelar, tocar, pausar, pular, salvar, enviar", 30)
INTERNET = Grupo("internet", "pesquisar na internet ou abrir um site", 40)
CONVERSA = Grupo("conversa", "qualquer outra coisa: perguntas, conversa, pedidos de texto e coisas fora do computador", 99)
