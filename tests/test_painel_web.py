import json
import threading
import unittest
import urllib.error
import urllib.request

from merlin.interface.painel_alertas import ApiAlertas, ServicoAlertas
from merlin.web import servidor as painel


class _Preferencias:
    def __init__(self, administrador):
        self.administrador = administrador
        self.alertas_intervalo = 0
        self.alertas_modo_teste = False


class _ComServidor(unittest.TestCase):
    def subir(self, administrador=False):
        servico = ServicoAlertas(consultar=lambda **_: {}, preferencias=_Preferencias(administrador))
        servidor = painel.criar_servidor("127.0.0.1", 0, ApiAlertas(servico))
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        self.base = f"http://127.0.0.1:{servidor.server_address[1]}"

    def pedir(self, caminho, corpo=None, cabecalhos=None):
        dados = None if corpo is None else json.dumps(corpo).encode()
        pedido = urllib.request.Request(self.base + caminho, data=dados, headers=cabecalhos or {})
        try:
            with urllib.request.urlopen(pedido, timeout=5) as resposta:
                return resposta.status, resposta.headers, resposta.read()
        except urllib.error.HTTPError as erro:
            return erro.code, erro.headers, erro.read()

    def chamar(self, nome, *args):
        return self.pedir(f"/api/{nome}", list(args), {"Content-Type": "application/json", "X-Painel": "1"})


class TestPainelWeb(_ComServidor):
    def test_pagina_tem_a_ponte_e_o_mapa(self):
        self.subir()
        status, cabecalhos, corpo = self.pedir("/")
        self.assertEqual(status, 200)
        pagina = corpo.decode("utf-8")
        self.assertIn("window.pywebview = { api: new Proxy", pagina)
        self.assertIn("window.CONTORNO_BRASIL", pagina)
        self.assertNotIn("<!--MAPA-->", pagina)
        self.assertIn("frame-ancestors 'none'", cabecalhos["Content-Security-Policy"])
        self.assertEqual(cabecalhos["X-Content-Type-Options"], "nosniff")

    def test_saude(self):
        self.subir()
        status, _, corpo = self.pedir("/healthz")
        self.assertEqual((status, json.loads(corpo)), (200, {"status": "ok"}))

    def test_chama_o_servico(self):
        self.subir()
        status, _, corpo = self.chamar("estado_automatico")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(corpo)["administrador"])
        self.assertEqual(json.loads(self.chamar("ultima")[2]), {})

    def test_operador_nao_configura(self):
        self.subir()
        self.assertIn("erro", json.loads(self.chamar("configurar", 15, False)[2]))

    def test_administrador_configura(self):
        self.subir(administrador=True)
        r = json.loads(self.chamar("configurar", 15, False)[2])
        self.assertEqual(r["intervalo"], 15)

    def test_recusa_pedidos_fora_da_ponte(self):
        self.subir()
        self.assertEqual(self.pedir("/api/ultima", [], {"Content-Type": "application/json"})[0], 403)  # sem o cabeçalho
        self.assertEqual(self.pedir("/api/ultima", [], {"X-Painel": "1", "Content-Type": "text/plain"})[0], 403)
        self.assertEqual(self.chamar("buscar")[0], 404)  # não está na lista
        self.assertEqual(self.chamar("abrir_mapa", 1, 2)[0], 404)  # fica na ponte, no navegador
        self.assertEqual(self.chamar("_servico")[0], 404)
        self.assertEqual(self.chamar("configurar", 15)[0], 400)  # falta argumento
        self.assertEqual(self.pedir("/nada")[0], 404)

    def test_corpo_grande_recusado(self):
        self.subir()
        status = self.pedir("/api/ultima", ["x" * (painel.MAX_CORPO + 10)],
                            {"Content-Type": "application/json", "X-Painel": "1"})[0]
        self.assertEqual(status, 413)


class TestMetricas(_ComServidor):
    def test_metrics_conta_pedidos_status_e_latencia(self):
        self.subir()
        self.pedir("/")
        self.pedir("/nada")  # 404
        self.chamar("ultima")
        self.pedir("/api/ultima", [], {"Content-Type": "application/json"})  # 403
        status, cabecalhos, corpo = self.pedir("/metrics")
        self.assertEqual(status, 200)
        self.assertTrue(cabecalhos["Content-Type"].startswith("text/plain; version=0.0.4"))
        texto = corpo.decode()
        self.assertIn('painel_http_requests_total{metodo="GET",rota="/",status="200"} 1', texto)
        self.assertIn('painel_http_requests_total{metodo="GET",rota="desconhecida",status="404"} 1', texto)
        self.assertIn('painel_http_requests_total{metodo="POST",rota="/api/ultima",status="200"} 1', texto)
        self.assertIn('painel_http_requests_total{metodo="POST",rota="/api/ultima",status="403"} 1', texto)
        self.assertIn('painel_http_request_duration_seconds_bucket{metodo="POST",rota="/api/ultima",le="+Inf"} 2', texto)
        self.assertIn('painel_http_request_duration_seconds_count{metodo="GET",rota="/"} 1', texto)

    def test_rota_desconhecida_nao_cria_serie_nova(self):
        self.subir()
        for i in range(5):
            self.chamar(f"inventada{i}")
        texto = self.pedir("/metrics")[2].decode()
        self.assertIn('rota="/api/desconhecida",status="404"} 5', texto)
        self.assertNotIn("inventada", texto)

    def test_falha_inesperada_conta_como_500(self):
        metricas = painel.Metricas()

        class ApiQuebrada:
            def ultima(self):
                raise RuntimeError("quebrou")
        servidor = painel.criar_servidor("127.0.0.1", 0, ApiQuebrada(), metricas=metricas)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        self.base = f"http://127.0.0.1:{servidor.server_address[1]}"
        with self.assertLogs("merlin.web.servidor", "ERROR"):
            self.assertEqual(self.chamar("ultima")[0], 500)
        self.assertIn('rota="/api/ultima",status="500"} 1', metricas.texto())

    def test_buscas_na_nasa(self):
        metricas = painel.Metricas()
        ok = painel.consultar_medido(lambda **_: {"ativos": 12, "em_alerta": 3}, metricas)
        ok()

        def quebra(**_):
            raise painel.focos.ConsultaFalhou("sem internet")
        with self.assertRaises(painel.focos.ConsultaFalhou):
            painel.consultar_medido(quebra, metricas)()
        texto = metricas.texto()
        self.assertIn('painel_alertas_buscas_total{resultado="ok"} 1', texto)
        self.assertIn('painel_alertas_buscas_total{resultado="erro"} 1', texto)
        self.assertIn("painel_alertas_focos_ativos 12", texto)
        self.assertIn("painel_alertas_focos_em_alerta 3", texto)


class TestPreferenciasDoPainel(unittest.TestCase):
    def test_padrao_e_operador_de_hora_em_hora(self):
        p = painel.PreferenciasDoPainel({})
        self.assertEqual((p.administrador, p.alertas_intervalo, p.alertas_modo_teste), (False, 60, False))

    def test_valores_do_ambiente(self):
        p = painel.PreferenciasDoPainel({"PAINEL_PERFIL": " Administrador ", "ALERTAS_INTERVALO": "15"})
        self.assertEqual((p.administrador, p.alertas_intervalo), (True, 15))

    def test_intervalo_invalido_usa_o_padrao(self):
        for valor in ("7", "abc", "-1"):
            with self.subTest(valor), self.assertLogs("merlin.web.servidor", "WARNING"):
                self.assertEqual(painel.PreferenciasDoPainel({"ALERTAS_INTERVALO": valor}).alertas_intervalo, 60)


if __name__ == "__main__":
    unittest.main()
