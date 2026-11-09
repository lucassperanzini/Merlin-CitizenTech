"""Pede um script à IA e o guarda na aba Automações, com a explicação e os avisos. Daqui, nada é executado."""
import logging
import re
import time

from merlin.automacao.analise_script import analisar
from merlin.automacao.scripts import AVISO_FIXO, ArmazemDeScripts
from merlin.nucleo.resposta import Resultado
from merlin.nucleo.sessao import Pendencia

logger = logging.getLogger(__name__)

PRAZO_PARA_DECIDIR = 300  # segundos: depois disso o script continua na aba, mas o cartão não responde mais
BLOCO = re.compile(r"```(?:python|py)?[ \t]*\r?\n(.*?)```", re.S | re.I)
SISTEMA = """Você escreve um único script Python 3 para Windows que faz exatamente o que a pessoa pediu, sem trocar nem acrescentar nada.
Bibliotecas disponíveis: a biblioteca padrão do Python, pandas, numpy, pillow e matplotlib. Não use nenhuma outra.
Se o script criar arquivos, ele não pode substituir arquivos que já existem.
Se o script precisar de uma pasta do computador, escreva no início dele exatamente PASTA = r"C:\\Exemplo" e use essa constante. Se não precisar, não crie essa constante.
Responda com um bloco ```python com o script e, depois dele, uma explicação simples em português, em até 4 frases, do que ele faz."""


_DIA = r"(?:todos?\s+(?:os\s+)?dias?|diariamente)"
_HORA = r"[àa]s\s+(\d{1,2})(?:\s*[:h]\s*(\d{2}))?(?:\s*h(?:oras?)?)?(?:\s+d[ae]\s+(manh[ãa]|tarde|noite))?"
_DIA_E_HORA = re.compile(rf"[,\s]*{_DIA}\s*,?\s*{_HORA}\b", re.I)
_HORA_E_DIA = re.compile(rf"[,\s]*{_HORA}\s*,?\s*{_DIA}\b", re.I)
_SO_DIA = re.compile(rf"[,\s]*\b{_DIA}\b", re.I)


def extrair_horario(comando: str) -> tuple[str, str]:
    """Tira o "todo dia às 15:00" da frase. Quem cuida do horário é o Merlin; senão a IA escreve um script que fica esperando."""
    achado = _DIA_E_HORA.search(comando) or _HORA_E_DIA.search(comando)
    if not achado:
        return _SO_DIA.sub("", comando).strip(" ,"), ""
    hora, minuto = int(achado.group(1)), int(achado.group(2) or 0)
    periodo = (achado.group(3) or "").lower()
    if periodo in ("tarde", "noite") and hora < 12:
        hora += 12
    elif periodo == "noite" and hora == 12:
        hora = 0
    sem_horario = (comando[:achado.start()] + comando[achado.end():]).strip(" ,")
    return sem_horario, f"{hora:02d}:{minuto:02d}" if hora < 24 and minuto < 60 else ""


def _separar(texto: str) -> tuple[str, str] | None:
    achado = BLOCO.search(texto)
    if not achado or not achado.group(1).strip():
        return None
    return achado.group(1).strip() + "\n", texto[achado.end():].strip()


class GerarScript:
    def __init__(self, cliente_ia, sessao, canal, armazem):
        self._cliente = cliente_ia
        self._sessao = sessao
        self._canal = canal
        self._armazem = armazem

    def __call__(self, intencao) -> Resultado:
        pedido, hora_sugerida = extrair_horario(intencao.comando)
        try:
            resposta = self._cliente.perguntar(
                [{"role": "system", "content": SISTEMA}, {"role": "user", "content": pedido}],
                opcoes={"temperature": 0})
        except Exception as erro:  # a IA pode estar desligada ou sem memória
            logger.error("[SCRIPT] A IA não respondeu: %s", erro)
            return Resultado("não consegui falar com a IA", registro=f"Erro da IA: {erro}")
        partes = _separar(resposta)
        analise = analisar(partes[0]) if partes else None
        if analise is None or not analise.valido:
            return Resultado("não consegui escrever um script válido. Tente pedir de outro jeito",
                             registro="A IA não devolveu um script válido", frase_completa=True)
        if analise.bloqueios:
            motivos = " e ".join(analise.bloqueios)
            return Resultado(f"Não vou criar esse script porque ele {motivos}. "
                             "Por enquanto, só faço scripts que leem informações ou criam arquivos novos.",
                             registro=f"Script recusado: {motivos}", frase_completa=True)
        codigo, explicacao = partes
        try:
            id_script = self._armazem.guardar(intencao.comando, codigo, explicacao, (AVISO_FIXO, *analise.avisos), hora_sugerida)
        except OSError as erro:
            logger.error("[SCRIPT] Não consegui guardar: %s", erro)
            return Resultado("não consegui guardar o script", registro=f"Erro ao guardar: {erro}")
        self._sessao.aguardar_confirmacao(Pendencia(
            pergunta="Quer ver o script?",
            ao_confirmar=lambda: self._ver(id_script),
            resposta_recusa="Tudo bem, descartei o script.",
            expira_em=time.time() + PRAZO_PARA_DECIDIR,
            ao_recusar=lambda: self._armazem.apagar(id_script),
        ))

        def mostrar():
            self._sessao.ativar()  # no modo discreto, o cartão ainda está fechado
            self._canal.script(explicacao or "O script está pronto.")
        return Resultado("Criei um script para você. Ele ainda não foi testado e só roda se você clicar em Executar.",
                         registro=f"Script criado: {id_script}", frase_completa=True, finaliza=True, depois=mostrar)

    def _ver(self, id_script: str) -> Resultado:
        self._canal.abrir_script(id_script)
        return Resultado("abrindo o script na aba Automações", registro=f"Script aberto: {id_script}")


def criar(recursos) -> GerarScript:
    return GerarScript(recursos.cliente_ia, recursos.sessao, recursos.canal, ArmazemDeScripts())
