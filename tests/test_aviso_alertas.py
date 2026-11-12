import queue
import unittest.mock
import unittest

from merlin.alertas.aviso import AvisoDeAlertas, FalaDeAlerta, contar_alertas, frase_do_alerta
from merlin.interface.painel_alertas import ServicoAlertas
from merlin.nucleo.trabalhador import TrabalhadorComandos


def foco(nivel, grau, novo=True, alerta=True):
    return {"nivel": nivel, "grau": grau, "novo": novo, "alerta": alerta}


class TestFrase(unittest.TestCase):
    def test_conta_so_os_novos_em_alerta_do_mais_grave_ao_mais_leve(self):
        r = {"focos": [foco("Alto", 3), foco("Crítico", 4), foco("Alto", 3), foco("Alto", 3, novo=False),
                       foco("Médio", 2, alerta=False), foco("Crítico", 4)]}
        self.assertEqual(contar_alertas(r), [("Crítico", 2), ("Alto", 2)])

    def test_frases(self):
        casos = [
            ([("Alto", 3), ("Médio", 5)], "Alerta de 3 focos de incêndio altos e 5 médios."),
            ([("Crítico", 1), ("Alto", 4)], "Alerta de 1 foco de incêndio crítico e 4 altos."),
            ([("Alto", 1)], "Alerta de 1 foco de incêndio alto."),
            ([("Crítico", 2), ("Alto", 1), ("Médio", 7)], "Alerta de 2 focos de incêndio críticos, 1 alto e 7 médios."),
            ([], ""),
        ]
        for contagem, esperada in casos:
            self.assertEqual(frase_do_alerta(contagem), esperada)


class Falso:
    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        return lambda *args: self.chamadas.append((nome, *args))


class Estado:
    def __init__(self):
        self.fila_comandos = queue.Queue()


class TestAviso(unittest.TestCase):
    def setUp(self):
        self.estado, self.sessao, self.locutor, self.canal = Estado(), Falso(), Falso(), Falso()
        self.aviso = AvisoDeAlertas(self.estado, self.sessao, self.locutor, self.canal)

    def test_alerta_deixa_a_bolinha_vermelha_e_entra_na_fila_para_falar(self):
        self.aviso({"focos": [foco("Alto", 3), foco("Alto", 3), foco("Crítico", 4)]})
        texto = "Alerta de 1 foco de incêndio crítico e 2 altos."
        self.assertEqual(self.canal.chamadas, [("alerta", {"quantidade": 3, "texto": texto})])
        fala = self.estado.fila_comandos.get_nowait()
        self.assertIsInstance(fala, FalaDeAlerta)
        self.assertEqual(self.locutor.chamadas, [])  # só fala quando o trabalhador chegar nela
        fala()
        self.assertEqual(self.sessao.chamadas, [("ativar",)])
        self.assertEqual(self.canal.chamadas[-1], ("atalho_alertas",))  # antes de falar: o atalho vai nesta fala
        self.assertEqual(self.locutor.chamadas, [("falar", texto)])

    def test_sem_foco_novo_em_alerta_fica_quieto(self):
        self.aviso({"focos": [foco("Alto", 3, novo=False), foco("Médio", 2, alerta=False)]})
        self.assertEqual(self.canal.chamadas, [])
        self.assertTrue(self.estado.fila_comandos.empty())

    def test_trabalhador_executa_o_aviso_em_vez_de_processar_como_frase(self):
        processador = Falso()
        trabalhador = TrabalhadorComandos(unittest.mock.Mock(), None, Falso(), processador)
        feito = []
        trabalhador._atender(lambda: feito.append(True))
        self.assertEqual((feito, processador.chamadas), ([True], []))
        trabalhador._atender("abre o chrome")
        self.assertEqual(processador.chamadas, [("processar", "abre o chrome")])

    def test_cada_busca_bem_sucedida_passa_pelo_aviso(self):
        recebidos = []
        servico = ServicoAlertas(lambda: {"focos": [foco("Alto", 3)]}, ao_alertar=recebidos.append)
        servico.buscar()
        self.assertEqual(len(recebidos), 1)
        ServicoAlertas(lambda: {"erro": "sem internet"}, ao_alertar=recebidos.append).buscar()
        self.assertEqual(len(recebidos), 1)  # erro não avisa

    def test_aviso_que_falha_nao_estraga_a_busca(self):
        def quebra(_):
            raise RuntimeError("canal fechado")
        servico = ServicoAlertas(lambda: {"focos": []}, ao_alertar=quebra)
        with self.assertLogs("merlin.interface.painel_alertas", "ERROR"):
            self.assertEqual(servico.buscar()["focos"], [])


class SomFalso:
    def __init__(self, duracao=0.05):
        self.duracao, self.tocadas, self.canais = duracao, 0, []

    def get_length(self):
        return self.duracao

    def play(self):
        self.tocadas += 1
        canal = unittest.mock.Mock()
        self.canais.append(canal)
        return canal


class EstadoDoAlarme:
    def __init__(self):
        import threading
        self.falando, self.encerrando = threading.Event(), threading.Event()
        self.mudo = []

    def silenciar_microfone(self, segundos):
        self.mudo.append(segundos)


def esperar(condicao, limite=2.0):
    import time
    fim = time.monotonic() + limite
    while not condicao() and time.monotonic() < fim:
        time.sleep(0.01)
    return condicao()


class TestAlarme(unittest.TestCase):
    def setUp(self):
        from merlin.voz.alarme import Alarme
        self.som, self.estado = SomFalso(), EstadoDoAlarme()
        self.alarme = Alarme(self.estado, pausa=0.05, carregar=lambda arquivo: self.som)
        self.addCleanup(self.alarme.parar)

    def test_repete_ate_parar_e_silencia_o_microfone_a_cada_ciclo(self):
        self.alarme.tocar()
        self.assertTrue(esperar(lambda: self.som.tocadas >= 3))
        self.assertTrue(all(s > self.som.duracao for s in self.estado.mudo))  # um pouco além do som
        self.alarme.parar()
        self.som.canais[-1].stop.assert_called_once()  # o ciclo em andamento é cortado na hora
        tocadas = self.som.tocadas
        esperar(lambda: False, 0.3)
        self.assertEqual(self.som.tocadas, tocadas)
        self.assertFalse(self.alarme.ligado)

    def test_nao_toca_por_cima_da_voz_do_merlin(self):
        self.estado.falando.set()
        self.alarme.tocar()
        esperar(lambda: False, 0.3)
        self.assertEqual(self.som.tocadas, 0)
        self.estado.falando.clear()
        self.assertTrue(esperar(lambda: self.som.tocadas >= 1))

    def test_pausado_pela_fala_do_alerta(self):
        self.alarme.pausar()
        self.alarme.tocar()
        esperar(lambda: False, 0.3)
        self.assertEqual(self.som.tocadas, 0)
        self.alarme.retomar()
        self.assertTrue(esperar(lambda: self.som.tocadas >= 1))

    def test_sem_caixa_de_som_o_resto_do_aviso_continua(self):
        from merlin.voz.alarme import Alarme
        def quebra(arquivo):
            raise RuntimeError("sem dispositivo de áudio")
        alarme = Alarme(self.estado, carregar=quebra)
        with self.assertLogs("merlin.voz.alarme", "WARNING"):
            alarme.tocar()
        self.assertFalse(alarme.ligado)


class AlarmeFalso:
    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        return lambda *args: self.chamadas.append(nome)


class TestAlarmeNoAviso(unittest.TestCase):
    def setUp(self):
        self.estado, self.sessao, self.locutor, self.canal = Estado(), Falso(), Falso(), Falso()
        self.alarme = AlarmeFalso()
        self.aviso = AvisoDeAlertas(self.estado, self.sessao, self.locutor, self.canal, self.alarme)

    def test_toca_ao_chegar_pausa_na_fala_e_para_quando_visto(self):
        self.aviso({"focos": [foco("Alto", 3)]})
        self.assertEqual(self.alarme.chamadas, ["tocar"])
        self.assertTrue(self.aviso.pendente)
        self.estado.fila_comandos.get_nowait()()
        self.assertEqual(self.alarme.chamadas, ["tocar", "pausar", "retomar"])  # fala sem o alarme por cima
        self.aviso.visto()
        self.assertEqual(self.alarme.chamadas[-1], "parar")
        self.assertEqual(self.canal.chamadas[-1], ("alerta", None))  # a bolinha e o cartão voltam ao normal
        self.assertFalse(self.aviso.pendente)

    def test_visto_sem_alerta_nao_mexe_na_janela(self):
        self.aviso.visto()
        self.assertEqual(self.canal.chamadas, [])

    def test_aba_alertas_na_tela_desliga(self):
        vistos = []
        ServicoAlertas(ao_ver=lambda: vistos.append(True)).vistos()
        self.assertEqual(vistos, [True])


if __name__ == "__main__":
    unittest.main()
