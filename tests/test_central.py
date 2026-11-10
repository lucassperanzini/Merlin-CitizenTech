import html
import re
import unittest

from merlin.interface.central import ABA_INICIAL, QUADROS, ApiCentral, montar_pagina


class ParteFalsa:
    def __init__(self):
        self.janela = None

    def _usar_janela(self, janela):
        self.janela = janela


class TestCentral(unittest.TestCase):
    def test_cada_ferramenta_entra_num_quadro_com_a_sua_api(self):
        pagina = montar_pagina()
        self.assertNotIn("<!--QUADRO:", pagina)  # todos os lugares foram preenchidos
        for aba in QUADROS:
            achado = re.search(rf'<iframe class="quadro" id="quadro-{aba}" title="{aba}" srcdoc="([^"]*)"', pagina)
            self.assertIsNotNone(achado, aba)
            conteudo = html.unescape(achado.group(1))
            self.assertIn(f"parent.pywebview.api.{aba}[nome]", conteudo)  # a página do quadro só vê a sua parte
            self.assertIn("pywebviewready", conteudo)

    def test_cada_quadro_tem_uma_aba_no_menu(self):
        pagina = montar_pagina()
        for aba in (*QUADROS, ABA_INICIAL, "inteligencia"):
            self.assertIn(f'data-aba="{aba}"', pagina)
            self.assertIn(f'id="mod-{aba}"', pagina)

    def test_mapa_vai_dentro_da_pagina_dos_alertas(self):
        pagina = html.unescape(montar_pagina())
        self.assertNotIn("<!--MAPA-->", pagina)
        self.assertIn("Leaflet 1.9.4", pagina)
        self.assertIn("window.CONTORNO_BRASIL = {", pagina)

    def test_aba_pedida_antes_de_abrir_vale_uma_vez(self):
        api = ApiCentral(ParteFalsa(), ParteFalsa(), ParteFalsa(), ParteFalsa())
        api._aba_pendente = "habilidades"
        self.assertEqual(api.aba_inicial(), "habilidades")
        self.assertEqual(api.aba_inicial(), ABA_INICIAL)

    def test_janela_chega_a_todas_as_partes(self):
        partes = [ParteFalsa() for _ in range(4)]
        ApiCentral(*partes)._usar_janela("janela")
        self.assertTrue(all(p.janela == "janela" for p in partes))


if __name__ == "__main__":
    unittest.main()
