import json
import unittest

from merlin.estado import EstadoAssistente
from merlin.ia.intencoes import ClassificadorIntencao, Intencao, TipoIntencao
from merlin.interface.janela_raciocinio import ApiRaciocinio
from merlin.nucleo.processador import ProcessadorComandos
from merlin.nucleo.raciocinio import Raciocinio, TipoPasso
from merlin.nucleo.resposta import Resultado
from merlin.nucleo.sessao import Sessao
from tests.falsos import CanalFalso, ClassificadorFalso, ClienteFalso, ConfirmadorFalso, DivisorFalso, LocutorFalso, SaudacaoFalsa


class TestRegistro(unittest.TestCase):
    def test_guarda_em_ordem_e_entrega_so_os_novos(self):
        r = Raciocinio()
        r.registrar(TipoPasso.OUVI, "abre o chrome")
        r.registrar(TipoPasso.INTENCAO, "abrir_programa", alvo="chrome", local="", tempo=0.4321)
        passos = r.desde(0)
        self.assertEqual([p.tipo for p in passos], [TipoPasso.OUVI, TipoPasso.INTENCAO])
        self.assertEqual(passos[1].detalhes, (("alvo", "chrome"), ("tempo", "0,43 s")))  # vazio fica de fora
        self.assertEqual(r.desde(passos[0].numero), [passos[1]])

    def test_guarda_so_os_mais_recentes(self):
        r = Raciocinio(limite=3)
        for i in range(5):
            r.registrar(TipoPasso.FALA, str(i))
        self.assertEqual([p.texto for p in r.desde(0)], ["2", "3", "4"])

    def test_listas_e_nomes_compostos(self):
        r = Raciocinio()
        r.registrar(TipoPasso.BOTOES, "3", nomes=["Play", "Pausar"], como_escolhi="pelo nome")
        self.assertEqual(r.desde(0)[0].detalhes, (("nomes", "Play, Pausar"), ("como escolhi", "pelo nome")))

    def test_api_da_pagina(self):
        r = Raciocinio()
        r.registrar(TipoPasso.OUVI, "oi")
        api = ApiRaciocinio(r)
        self.assertEqual(api.novos(0)[0]["tipo"], "ouvi")
        self.assertEqual(api.novos(1), [])
        api.limpar()
        self.assertEqual(api.novos(0), [])


class TestMotivoDasRegras(unittest.TestCase):
    def _classificar(self, intencao, alvo, comando):
        resposta = json.dumps({"alvo": alvo, "intencao": intencao, "busca": "", "local": ""})
        return ClassificadorIntencao(ClienteFalso(resposta)).classificar(comando)

    def test_sem_regra_nao_ha_motivo_e_guarda_a_resposta_do_modelo(self):
        i = self._classificar("abrir_programa", "chrome", "abre o chrome")
        self.assertEqual(i.motivo_regra, "")
        self.assertEqual(i.resposta_modelo["alvo"], "chrome")

    def test_regra_explica_a_mudanca(self):
        self.assertIn("verbo de abrir", self._classificar("fechar_programa", "chrome", "abre o chrome").motivo_regra)
        self.assertIn("pergunta", self._classificar("clicar_botao", "salvar", "o que faz o salvar").motivo_regra)
        self.assertIn("discord", self._classificar("encerrar", "discord", "encerra o discord").motivo_regra)

    def test_motivo_nao_muda_a_igualdade(self):
        a = Intencao(TipoIntencao.CONVERSAR, "x", "y", motivo_regra="um")
        self.assertEqual(a, Intencao(TipoIntencao.CONVERSAR, "x", "y"))


class TestProcessadorAnota(unittest.TestCase):
    def test_anota_o_pedido_inteiro(self):
        estado, canal = EstadoAssistente(), CanalFalso()
        sessao = Sessao(estado, canal)
        sessao.ativar()
        raciocinio = Raciocinio()
        intencao = Intencao(TipoIntencao.ABRIR_PROGRAMA, "chrome", "abre o chrome", motivo_regra="exemplo de regra")
        acoes = {t: (lambda i: Resultado("abri o chrome", registro="Abriu: chrome")) for t in TipoIntencao}
        processador = ProcessadorComandos(estado, sessao, canal, LocutorFalso(), DivisorFalso(), ClassificadorFalso(intencao),
                                          ConfirmadorFalso(), SaudacaoFalsa(), acoes, raciocinio=raciocinio)
        processador.processar("abre o chrome")
        passos = raciocinio.desde(0)
        self.assertEqual([p.tipo for p in passos], [TipoPasso.OUVI, TipoPasso.TAREFAS, TipoPasso.INTENCAO,
                                                    TipoPasso.REGRA, TipoPasso.ACAO, TipoPasso.FALA])
        self.assertIn("abrir_programa", passos[2].texto)
        self.assertEqual(passos[4].texto, "Abriu: chrome")


if __name__ == "__main__":
    unittest.main()
