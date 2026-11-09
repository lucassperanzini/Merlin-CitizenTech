import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from merlin.acoes.gerar_script import extrair_horario
from merlin.automacao.agendador import Agendador
from merlin.automacao.scripts import ArmazemDeScripts, ScriptInvalido
from merlin.nucleo.trabalhador import TrabalhadorComandos

ANTES = datetime(2026, 11, 9, 14, 0)
NA_HORA = datetime(2026, 11, 9, 15, 0, 30)


class Base(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        python = patch("merlin.automacao.scripts.PYTHON_DOS_SCRIPTS", Path(sys.executable))
        python.start()
        self.addCleanup(python.stop)
        self.raiz = Path(temporaria.name).resolve()
        self.pasta = self.raiz / "teste"
        self.pasta.mkdir()
        self.armazem = ArmazemDeScripts(self.raiz / "s")
        self.id = self.armazem.guardar("x", 'PASTA = "x"\nimport os\nprint("rodou", len(os.listdir(PASTA)))\n', "", [])
        self.agendador = Agendador(self.armazem)

    def aprovar(self):
        self.armazem.definir_pasta(self.id, str(self.pasta))
        self.assertTrue(self.armazem.executar(self.id)["ok"])
        self.armazem.aprovar(self.id, "contar")

    def agendar(self, agora=ANTES, hora="15:00"):
        self.aprovar()
        self.armazem.agendar(self.id, hora, agora)

    def script(self):
        return self.armazem.listar()[0]

    def historico(self):
        return self.script()["historico"]


class Regras(Base):
    def test_exige_aprovado(self):
        self.armazem.definir_pasta(self.id, str(self.pasta))
        with self.assertRaisesRegex(ScriptInvalido, "Aprove"):
            self.armazem.agendar(self.id, "15:00", ANTES)

    def test_hora_invalida(self):
        self.aprovar()
        for ruim in ("", "25:00", "15:60", "1500", None):
            with self.subTest(ruim), self.assertRaises(ScriptInvalido):
                self.armazem.agendar(self.id, ruim, ANTES)

    def test_nao_troca_pasta_agendada(self):
        self.agendar()
        with self.assertRaisesRegex(ScriptInvalido, "Remova"):
            self.armazem.definir_pasta(self.id, str(self.raiz))

    def test_remover_aprovacao_tira_a_agenda(self):
        self.agendar()
        self.armazem.desaprovar(self.id)
        self.assertIsNone(self.script()["agenda"])


class Disparo(Base):
    def test_roda_uma_vez_na_hora_e_registra(self):
        self.agendar()
        self.agendador.verificar(ANTES)
        self.assertEqual(self.historico(), [])
        self.agendador.verificar(NA_HORA)
        self.agendador.verificar(NA_HORA.replace(minute=2))
        self.assertEqual(len(self.historico()), 1)
        self.assertTrue(self.historico()[0]["ok"])
        self.assertIn("rodou", self.historico()[0]["resumo"])

    def test_roda_no_dia_seguinte(self):
        self.agendar()
        self.agendador.verificar(NA_HORA)
        self.agendador.verificar(NA_HORA.replace(day=10))
        self.assertEqual(len(self.historico()), 2)

    def test_horario_perdido_nao_compensa(self):
        self.agendar()
        self.agendador.verificar(NA_HORA.replace(minute=6))
        self.assertEqual(self.historico(), [])

    def test_agendar_depois_da_hora_fica_para_amanha(self):
        self.agendar(agora=NA_HORA.replace(minute=1))
        self.agendador.verificar(NA_HORA.replace(minute=2))
        self.assertEqual(self.historico(), [])
        self.agendador.verificar(NA_HORA.replace(day=10))
        self.assertEqual(len(self.historico()), 1)

    def test_pausado_nao_roda(self):
        self.agendar()
        self.armazem.pausar_agenda(self.id, True, ANTES)
        self.agendador.verificar(NA_HORA)
        self.assertEqual(self.historico(), [])
        self.armazem.pausar_agenda(self.id, False, ANTES)
        self.agendador.verificar(NA_HORA)
        self.assertEqual(len(self.historico()), 1)

    def test_codigo_mudado_nao_roda_e_avisa(self):
        self.agendar()
        marca = self.pasta / "marca.txt"
        self.armazem.salvar_codigo(self.id, f'PASTA = "x"\nopen(r"{marca}", "x").close()\n')
        self.agendador.verificar(NA_HORA)
        self.assertFalse(marca.exists())
        self.assertFalse(self.historico()[0]["ok"])
        self.assertIn("aprovado de novo", self.historico()[0]["resumo"])

    def test_erro_do_script_fica_no_historico(self):
        self.aprovar()
        self.armazem.salvar_codigo(self.id, 'PASTA = "x"\nimport os\nif os.path.exists("erro.txt"):\n    print(1/0)\n')
        self.assertTrue(self.armazem.executar(self.id)["ok"])
        self.armazem.aprovar(self.id, "contar")
        self.armazem.agendar(self.id, "15:00", ANTES)
        (self.pasta / "erro.txt").write_text("x", encoding="utf-8")
        self.agendador.verificar(NA_HORA)
        self.assertFalse(self.historico()[0]["ok"])
        self.assertIn("ZeroDivisionError", self.historico()[0]["resumo"])

    def test_historico_tem_limite(self):
        for numero in range(15):
            self.armazem.registrar_execucao(self.id, str(numero), True, "x")
        self.assertEqual(len(self.historico()), 10)
        self.assertEqual(self.historico()[0]["quando"], "14")


class UmaVez(Base):
    T = NA_HORA.timestamp()

    def setUp(self):
        super().setUp()
        self.avisos = []
        self.agendador = Agendador(self.armazem, avisar=lambda fala, cartao: self.avisos.append(fala))

    def marcar(self, segundos=30):
        self.aprovar()
        self.armazem.agendar_unico(self.id, segundos, self.T)

    def em(self, segundos):
        return datetime.fromtimestamp(self.T + segundos)

    def test_roda_uma_vez_so_depois_do_tempo(self):
        self.marcar()
        self.agendador.verificar_unicos(self.em(29))
        self.assertEqual(self.historico(), [])
        self.agendador.verificar_unicos(self.em(30))
        self.agendador.verificar_unicos(self.em(31))
        self.assertEqual(len(self.historico()), 1)
        self.assertTrue(self.historico()[0]["ok"])
        self.assertIsNone(self.script()["unica"])
        self.assertEqual(len(self.avisos), 1)

    def test_cancelar(self):
        self.marcar()
        self.armazem.cancelar_unico(self.id)
        self.agendador.verificar_unicos(self.em(31))
        self.assertEqual(self.historico(), [])

    def test_exige_aprovado(self):
        self.armazem.definir_pasta(self.id, str(self.pasta))
        with self.assertRaisesRegex(ScriptInvalido, "Aprove"):
            self.armazem.agendar_unico(self.id, 30, self.T)

    def test_tempo_invalido(self):
        self.aprovar()
        for ruim in (0, -1, 86401, "30", None):
            with self.subTest(ruim), self.assertRaises(ScriptInvalido):
                self.armazem.agendar_unico(self.id, ruim, self.T)

    def test_merlin_fechado_nao_roda_de_surpresa(self):
        self.marcar()
        self.agendador.verificar_unicos(self.em(30 + 61))
        self.assertFalse(self.historico()[0]["ok"])
        self.assertIn("fechado", self.historico()[0]["resumo"])
        self.assertEqual(self.avisos, [])
        self.assertIsNone(self.script()["unica"])

    def test_codigo_mudado_nao_roda(self):
        self.marcar()
        self.armazem.salvar_codigo(self.id, 'PASTA = "x"\nprint(2)\n')
        self.agendador.verificar_unicos(self.em(31))
        self.assertIn("aprovado de novo", self.historico()[0]["resumo"])

    def test_nao_atrapalha_o_diario(self):
        self.agendar()
        self.armazem.agendar_unico(self.id, 30, self.T)
        self.agendador.verificar_unicos(self.em(31))
        self.assertIsNotNone(self.script()["agenda"])
        self.agendador.verificar(NA_HORA)
        self.assertEqual(len(self.historico()), 2)


class Aviso(Base):
    def setUp(self):
        super().setUp()
        self.avisos = []
        self.agendador = Agendador(self.armazem, avisar=lambda fala, cartao: self.avisos.append((fala, cartao)))

    def test_avisa_com_o_nome_e_o_resultado(self):
        self.agendar()
        self.agendador.verificar(NA_HORA)
        fala, cartao = self.avisos[0]
        self.assertIn("contar", fala)
        self.assertIn("sem erro", fala)
        self.assertIn("rodou", cartao)

    def test_avisa_quando_nao_roda(self):
        self.agendar()
        self.armazem.salvar_codigo(self.id, 'PASTA = "x"\nprint(2)\n')
        self.agendador.verificar(NA_HORA)
        self.assertIn("não funcionou", self.avisos[0][0])
        self.assertIn("aprovado de novo", self.avisos[0][1])

    def test_avisa_uma_vez_e_so_quando_roda(self):
        self.agendar()
        self.agendador.verificar(ANTES)
        self.assertEqual(self.avisos, [])
        self.agendador.verificar(NA_HORA)
        self.agendador.verificar(NA_HORA.replace(minute=1))
        self.assertEqual(len(self.avisos), 1)


class EntregaDoAviso(unittest.TestCase):
    def setUp(self):
        self.ordem = []
        self.estado = MagicMock()
        self.estado.falando.is_set.return_value = False
        sessao, canal, locutor = MagicMock(), MagicMock(), MagicMock()
        sessao.ativar.side_effect = lambda: self.ordem.append("ativar")
        locutor.falar.side_effect = lambda fala: self.ordem.append(fala)
        canal.resultado_script.side_effect = lambda texto: self.ordem.append(texto)
        self.locutor = locutor
        self.trabalhador = TrabalhadorComandos(self.estado, sessao, canal, MagicMock(), locutor)

    def test_abre_fala_e_mostra_um_por_vez(self):
        self.trabalhador.avisar("fala 1", "cartão 1")
        self.trabalhador.avisar("fala 2", "cartão 2")
        self.trabalhador._entregar_aviso()
        self.assertEqual(self.ordem, ["ativar", "fala 1", "cartão 1"])

    def test_espera_terminar_a_fala_em_andamento(self):
        self.estado.falando.is_set.return_value = True
        self.trabalhador.avisar("fala", "cartão")
        self.trabalhador._entregar_aviso()
        self.assertEqual(self.ordem, [])
        self.estado.falando.is_set.return_value = False
        self.trabalhador._entregar_aviso()
        self.assertEqual(self.ordem, ["ativar", "fala", "cartão"])

    def test_erro_na_fala_nao_derruba(self):
        self.locutor.falar.side_effect = RuntimeError("sem som")
        self.trabalhador.avisar("fala", "cartão")
        with self.assertLogs("merlin.nucleo.trabalhador", "ERROR"):
            self.trabalhador._entregar_aviso()


class Frase(unittest.TestCase):
    def test_tira_o_horario_do_pedido(self):
        casos = {"cria um script que faz x todo dia às 15:00": ("cria um script que faz x", "15:00"),
                 "cria um script que faz x todo dia as 15:00 da tarde": ("cria um script que faz x", "15:00"),
                 "cria um script que faz x, todos os dias às 3 da tarde": ("cria um script que faz x", "15:00"),
                 "cria um script que faz x às 8h30 todo dia": ("cria um script que faz x", "08:30"),
                 "cria um script que faz x diariamente às 9 horas": ("cria um script que faz x", "09:00"),
                 "cria um script que faz x todo dia": ("cria um script que faz x", ""),
                 "cria um script que faz x": ("cria um script que faz x", "")}
        for frase, esperado in casos.items():
            with self.subTest(frase):
                self.assertEqual(extrair_horario(frase), esperado)

    def test_hora_impossivel_nao_sugere(self):
        self.assertEqual(extrair_horario("faz x todo dia às 30")[1], "")


if __name__ == "__main__":
    unittest.main()
