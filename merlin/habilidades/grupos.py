"""Os grupos de habilidades. Uma habilidade nova escolhe um destes; um grupo novo pode ser criado aqui."""
from merlin.habilidades.base import Cartao, Grupo

ASSISTENTE = Grupo("assistente", "falar com o próprio assistente: despedir-se ou abrir os ajustes dele", 10)
PROGRAMAS = Grupo("programas", "abrir ou fechar um programa do computador, ou abrir uma pasta", 20)
DEFESA_CIVIL = Grupo("defesa_civil", "perguntas sobre protocolos e procedimentos da Defesa Civil e do combate a "
                     "incêndios", 30)
# Abrir e fechar programa: na aba Skills, um cartão só ("Programas"), com as duas partes dentro
CARTAO_PROGRAMAS = Cartao("programas", "Programas", "Abre e fecha os programas do computador.", "🖥️")

CONVERSA = Grupo("conversa", "qualquer outra coisa: perguntas, conversa, pedidos de texto e coisas fora do computador", 99)
