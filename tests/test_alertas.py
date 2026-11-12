import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

from firms_monitor.domain.models import FireHotspot

from merlin.alertas import focos
from merlin.interface.painel_alertas import ServicoAlertas


def foco(frp, confianca="n", lat=-10.0, minuto=0):
    return FireHotspot(latitude=lat, longitude=-50.0, acquired_at=datetime(2026, 11, 10, 15, minuto, tzinfo=timezone.utc),
                       satellite="N20", instrument="VIIRS", confidence=confianca, frp=frp, daynight="D",
                       brightness=330.0, source="VIIRS_NOAA20_NRT")


class ProvedorFalso:
    def __init__(self, lista):
        self.lista = lista

    def fetch(self):
        return list(self.lista)


class Base(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.raiz = Path(temporaria.name)
        self.env = self.raiz / ".env"
        self.env.write_text("FIRMS_MAP_KEY=chave-de-teste\nALERT_MIN_LEVEL=ALTO\nOUTPUT_CSV=dados/incendio/ocorrencias.csv\n",
                            encoding="utf-8")
        self.provedor = ProvedorFalso([foco(5, lat=-1), foco(150, lat=-2), foco(60, lat=-3), foco(20, lat=-4),
                                       foco(500, confianca="l", lat=-5)])

    def consultar(self):
        return focos.consultar(self.env, self.raiz, self.provedor)


class Consulta(Base):
    def ativos(self, r):
        return [f for f in r["focos"] if not f["filtrado"]]

    def test_todos_os_ativos_do_mais_forte_ao_mais_fraco(self):
        r = self.consultar()
        self.assertEqual([f["frp"] for f in self.ativos(r)], [150, 60, 20, 5])
        self.assertEqual([f["nivel"] for f in self.ativos(r)], ["Crítico", "Alto", "Médio", "Baixo"])
        self.assertEqual((r["coletados"], r["ativos"], r["novos"], r["alertas"]), (5, 4, 4, 2))
        self.assertEqual([f["alerta"] for f in self.ativos(r)], [True, True, False, False])
        self.assertEqual({n["nivel"]: n["quantidade"] for n in r["por_nivel"]}, {"Crítico": 1, "Alto": 1, "Médio": 1, "Baixo": 1})
        self.assertEqual(r["em_alerta"], 2)

    def test_repetir_a_consulta_continua_em_alerta(self):
        self.consultar()
        r = self.consultar()  # os mesmos focos: o robô não avisa de novo, mas eles continuam em alerta
        self.assertEqual((r["novos"], r["alertas"], r["em_alerta"]), (0, 0, 2))

    def test_descartados_vem_depois_com_o_motivo(self):
        self.provedor.lista.append(foco(70, lat=40.0))  # fora do Brasil: o filtro de território do robô tira
        r = self.consultar()
        descartados = [f for f in r["focos"] if f["filtrado"]]
        self.assertEqual([(f["frp"], f["filtrado"]) for f in descartados],
                         [(500, "baixa confiança"), (70, "fora do território monitorado")])
        self.assertEqual(r["focos"][-2:], descartados)  # os ativos vêm primeiro
        self.assertEqual(r["descartados"], 2)
        self.assertTrue(all(not f["novo"] and not f["alerta"] for f in descartados))  # nunca entram no CSV do robô

    def test_segunda_consulta_mostra_todos_e_nenhum_novo(self):
        self.consultar()
        r = self.consultar()
        self.assertEqual(len(self.ativos(r)), 4)
        self.assertEqual((r["novos"], [f["novo"] for f in r["focos"]]), (0, [False] * 5))
        self.provedor.lista.append(foco(80, lat=-6))
        r = self.consultar()
        self.assertEqual([f["frp"] for f in r["focos"] if f["novo"]], [80])

    def test_csv_fica_na_pasta_do_projeto(self):
        r = self.consultar()
        self.assertTrue((self.raiz / "dados" / "incendio" / "ocorrencias.csv").is_file())
        self.assertEqual(Path(r["csv"]), self.raiz / "dados" / "incendio" / "ocorrencias.csv")

    def test_limite_de_focos_no_mapa(self):
        with unittest.mock.patch.object(focos, "MAX_FOCOS_NO_MAPA", 3):
            r = self.consultar()
        self.assertEqual((r["ativos"], [f["frp"] for f in r["focos"]]), (4, [150, 60, 20]))

    def test_sem_chave(self):
        self.env.write_text("ALERT_MIN_LEVEL=ALTO\n", encoding="utf-8")
        with self.assertRaisesRegex(focos.ConsultaFalhou, "FIRMS_MAP_KEY"):
            self.consultar()

    def test_sem_arquivo_de_configuracao(self):
        self.env.unlink()
        with self.assertRaisesRegex(focos.ConsultaFalhou, "configuração"):
            self.consultar()


class Painel(Base):
    def test_erro_vira_mensagem(self):
        self.env.unlink()
        r = ServicoAlertas(lambda: self.consultar()).buscar()
        self.assertIn("configuração", r["erro"])

    def test_robo_ausente(self):
        def ausente():
            raise focos.RoboAusente("firms_monitor")
        self.assertIn("não está instalado", ServicoAlertas(ausente).buscar()["erro"])

    def test_falha_inesperada_nao_derruba(self):
        def quebra():
            raise RuntimeError("bug do robô")
        with self.assertLogs("merlin.interface.painel_alertas", "ERROR"):
            self.assertIn("bug do robô", ServicoAlertas(quebra).buscar()["erro"])

    def test_um_clique_por_vez(self):
        servico = ServicoAlertas(lambda: {"ok": True})
        servico._ocupado.acquire()
        self.assertIn("Já estou", servico.buscar()["erro"])
        servico._ocupado.release()
        self.assertTrue(servico.buscar()["ok"])

    def test_guarda_a_ultima_consulta(self):
        arquivo = self.raiz / "dados" / "alertas" / "ultima.json"
        servico = ServicoAlertas(lambda: self.consultar(), arquivo_ultima=arquivo)
        self.assertEqual(servico.ultima(), {})  # nada consultado ainda
        r = servico.buscar()
        # Outra Central (outro ServicoAlertas) lê a mesma consulta, como ao reabrir o Merlin
        # (sem as marcas da tela aberta: teste, automatica e versao)
        marcas = {"teste", "automatica", "versao"}
        self.assertEqual(ServicoAlertas(arquivo_ultima=arquivo).ultima(), {k: v for k, v in r.items() if k not in marcas})

    def test_erro_nao_apaga_a_consulta_guardada(self):
        arquivo = self.raiz / "ultima.json"
        ServicoAlertas(lambda: {"focos": [], "ativos": 0}, arquivo_ultima=arquivo).buscar()
        ServicoAlertas(lambda: {"erro": "sem internet"}, arquivo_ultima=arquivo).buscar()
        self.assertEqual(ServicoAlertas(arquivo_ultima=arquivo).ultima(), {"focos": [], "ativos": 0})

    def test_arquivo_estragado_e_ignorado(self):
        arquivo = self.raiz / "ultima.json"
        for conteudo in ("{pela metade", "[1, 2]", '{"sem": "focos"}'):
            with self.subTest(conteudo):
                arquivo.write_text(conteudo, encoding="utf-8")
                with self.assertNoLogs("merlin.interface.painel_alertas", "ERROR"):
                    self.assertEqual(ServicoAlertas(arquivo_ultima=arquivo).ultima(), {})

    def servico_com_chave(self, valor, resposta=True):
        self.conferidas = []
        self.env.write_text(f"FIRMS_MAP_KEY=x\nMAPTILER_KEY={valor}\n", encoding="utf-8")
        return ServicoAlertas(arquivo_env=self.env, conferir_chave=lambda c: (self.conferidas.append(c), resposta)[1])

    def test_chave_do_mapa_vem_do_env(self):
        self.assertEqual(ServicoAlertas(arquivo_env=self.env).fundos()["maptiler"], "")  # sem a linha: OpenStreetMap
        for valor, esperado in (("Abc123def_-XYZ", "Abc123def_-XYZ"), ("  Abc123def  ", "Abc123def"), ('a"b<script>', ""), ("curta", "")):
            with self.subTest(valor):
                self.assertEqual(self.servico_com_chave(valor).fundos()["maptiler"], esperado)
        self.env.unlink()
        self.assertEqual(ServicoAlertas(arquivo_env=self.env).fundos()["maptiler"], "")

    def test_chave_recusada_vira_aviso(self):
        servico = self.servico_com_chave("Abc123def", resposta=False)
        r = servico.fundos()
        self.assertEqual(r["maptiler"], "")
        self.assertIn("recusou", r["aviso"])
        servico.fundos()
        self.assertEqual(self.conferidas, ["Abc123def"])  # confere uma vez só

    def test_sem_internet_tenta_conferir_de_novo(self):
        servico = self.servico_com_chave("Abc123def", resposta=None)
        self.assertEqual(servico.fundos()["maptiler"], "Abc123def")  # sem resposta: tenta usar mesmo assim
        servico.fundos()
        self.assertEqual(len(self.conferidas), 2)

    def test_lembra_o_fundo_escolhido(self):
        servico = self.servico_com_chave("Abc123def")
        servico.escolher_fundo("Escuro")
        self.assertEqual(servico.fundos()["escolhido"], "Escuro")

    def test_mapa_so_com_coordenadas_validas(self):
        abertas = []
        servico = ServicoAlertas(abrir_pagina=abertas.append)
        self.assertEqual(servico.abrir_mapa(-10.5, -50.25), {})
        self.assertEqual(abertas, ["https://www.google.com/maps?q=-10.5,-50.25"])
        for lat, lon in (("x", 1), (91, 0), (0, 181), (float("nan"), 0), (None, 0)):
            with self.subTest(lat):
                self.assertIn("erro", servico.abrir_mapa(lat, lon))
        self.assertEqual(len(abertas), 1)


class ModoTesteEBuscaAutomatica(Base):
    def setUp(self):
        super().setUp()
        from merlin.preferencias import Preferencias
        self.arquivo_config = self.raiz / "merlin_config.json"
        self.arquivo_config.write_text('{"perfil": "administrador"}', encoding="utf-8")
        self.preferencias = Preferencias(self.arquivo_config)
        self.ultima = self.raiz / "ultima.json"
        self.consultas = 0

    def consultar(self, do_zero=False):
        self.consultas += 1
        return focos.consultar(self.env, self.raiz, self.provedor, do_zero=do_zero)

    def servico(self, **extra):
        servico = ServicoAlertas(self.consultar, arquivo_ultima=self.ultima, preferencias=self.preferencias, **extra)
        self.addCleanup(servico.parar_agendamento)
        return servico

    def test_modo_teste_apaga_o_csv_e_a_ultima_antes_de_cada_busca(self):
        servico = self.servico()
        csv = self.raiz / "dados" / "incendio" / "ocorrencias.csv"
        servico.buscar()  # uma busca de verdade antes: o CSV já conhece os focos
        self.assertEqual(servico.buscar()["novos"], 0)
        self.assertTrue("erro" not in servico.configurar(0, True))
        for _ in range(3):  # quantas vezes quiser: cada busca começa do zero e todos voltam como novos em alerta
            r = servico.buscar()
            self.assertEqual((r["novos"], r["alertas"], r["teste"]), (4, 2, True))
        self.assertTrue(csv.exists() and self.ultima.exists())  # gravados de novo, só com a última busca
        self.assertEqual(servico.ultima()["novos"], 4)
        servico.configurar(0, False)
        r = servico.buscar()
        self.assertEqual((r["novos"], r["teste"]), (0, False))  # desligado: o CSV volta a acumular

    def test_modo_teste_avisa_o_csv_aberto_em_outro_programa(self):
        servico = self.servico()
        servico.configurar(0, True)
        from unittest import mock
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("em uso")):
            self.assertIn("não consegui apagar o CSV", servico.buscar()["erro"])

    def test_so_o_administrador_configura(self):
        self.arquivo_config.write_text('{"perfil": "operador", "alertas_intervalo": 60, "alertas_modo_teste": true}',
                                       encoding="utf-8")
        from merlin.interface.perfil import AVISO_SO_ADMINISTRADOR
        from merlin.preferencias import Preferencias
        self.preferencias = Preferencias(self.arquivo_config)
        servico = self.servico()
        with self.assertLogs("merlin.interface.painel_alertas", "WARNING"):
            self.assertEqual(servico.configurar(15, False), {"erro": AVISO_SO_ADMINISTRADOR})
        estado = servico.estado_automatico()
        self.assertEqual((estado["administrador"], estado["intervalo"]), (False, 60))  # o intervalo vale para ele
        self.assertFalse(estado["modo_teste"])  # o modo teste, não
        self.assertFalse(servico.buscar()["teste"])

    def test_intervalo_fora_da_lista_e_recusado(self):
        servico = self.servico()
        for invalido in (7, -1, "muito", None):
            self.assertIn("erro", servico.configurar(invalido, False), invalido)
        self.assertEqual(self.preferencias.alertas_intervalo, 0)

    def test_busca_sozinha_no_intervalo_e_para_ao_desligar(self):
        import time
        servico = self.servico(segundos_por_minuto=0.02)  # 15 "minutos" = 0,3 s
        servico.iniciar_agendamento()
        self.assertEqual(servico.estado_automatico()["proxima"], "")  # desligada
        estado = servico.configurar(15, False)
        self.assertTrue(estado["proxima"])
        prazo = time.monotonic() + 5
        while self.consultas < 2 and time.monotonic() < prazo:
            time.sleep(0.02)
        self.assertGreaterEqual(self.consultas, 2)
        self.assertTrue(servico.mais_recente()["automatica"])
        self.assertGreater(servico.estado_automatico()["versao"], 0)
        servico.configurar(0, False)
        feitas = self.consultas
        time.sleep(0.5)
        self.assertEqual(self.consultas, feitas)
        self.assertEqual(Path(self.arquivo_config).read_text(encoding="utf-8").count('"alertas_intervalo": 0'), 1)


if __name__ == "__main__":
    unittest.main()
