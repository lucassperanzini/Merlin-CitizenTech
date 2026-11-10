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
        self.assertEqual(servico.buscar(), {"ok": True})

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


if __name__ == "__main__":
    unittest.main()
