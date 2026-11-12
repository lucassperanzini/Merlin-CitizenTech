"""Focos de calor da NASA FIRMS, pelo robô firms_monitor (instalado à parte, com a configuração no .env).

Roda um ciclo igual ao do robô, com o CSV e os alertas dele, e devolve TODOS os focos ativos da consulta,
marcando quais ainda não estavam no CSV. O robô sozinho só mostra os novos.
"""
import dataclasses
import os
from datetime import datetime
from pathlib import Path

from merlin.config import ARQ_ENV, PASTA_RAIZ

MAX_FOCOS_NO_MAPA = 10000  # vários dias do Brasil inteiro podem passar disso; ficam os mais fortes


class RoboAusente(Exception):
    """O pacote firms_monitor não está instalado no Python do Merlin."""


class ConsultaFalhou(Exception):
    """A mensagem pode ser mostrada à pessoa."""


class _ProvedorQueGuarda:
    """Entrega ao robô os focos de sempre e guarda uma cópia, para a tela mostrar todos, e não só os novos."""

    def __init__(self, provedor):
        self._provedor = provedor
        self.focos = []

    def fetch(self):
        self.focos = list(self._provedor.fetch())
        return self.focos


class _RepositorioQueLembra:
    """O CSV do robô, lembrando o que já estava nele antes deste ciclo."""

    def __init__(self, repositorio):
        self._repositorio = repositorio
        self.conhecidos = set()

    def existing_ids(self):
        self.conhecidos = set(self._repositorio.existing_ids())
        return self.conhecidos

    def save_many(self, ocorrencias):
        return self._repositorio.save_many(ocorrencias)


def _na_raiz(caminho: Path, raiz: Path) -> Path:
    """Os caminhos do .env são relativos à pasta do projeto, e não à pasta de onde o Merlin foi aberto."""
    return caminho if caminho.is_absolute() else raiz / caminho


def _configuracao(arquivo_env: Path, raiz: Path):
    from dotenv import dotenv_values  # lê sem mexer nas variáveis do próprio Merlin
    from firms_monitor import Settings
    from firms_monitor.config import ConfigurationError

    if not arquivo_env.is_file():
        raise ConsultaFalhou(f"Não encontrei o arquivo de configuração do robô ({arquivo_env.name}).")
    lidas = {chave: valor for chave, valor in dotenv_values(arquivo_env).items() if valor is not None}
    try:
        configuracao = Settings.from_env(env={**os.environ, **lidas})
    except ConfigurationError as erro:
        raise ConsultaFalhou(str(erro)) from erro
    return dataclasses.replace(configuracao, output_csv=_na_raiz(configuracao.output_csv, raiz))


def consultar(arquivo_env: Path = ARQ_ENV, raiz: Path = PASTA_RAIZ, provedor=None, do_zero=False) -> dict:
    """provedor: só nos testes, no lugar da consulta à NASA.
    do_zero=True (modo teste): apaga o CSV do robô antes de consultar, então todo foco ativo volta como novo
    e todo foco do nível de alerta vira alerta. O CSV é gravado de novo no fim, só com esta consulta."""
    try:
        from firms_monitor import FireMonitorService
        from firms_monitor.bootstrap import build_query
        from firms_monitor.domain.filters import CompositeFilter, ConfidenceFilter, MinFrpFilter
        from firms_monitor.domain.risk import RiskClassifier
        from firms_monitor.infrastructure.firms import FirmsApiClient, FirmsApiError, FirmsCsvParser, FirmsHotspotProvider
        from firms_monitor.infrastructure.notification import LogAlertNotifier
        from firms_monitor.infrastructure.persistence import CsvOccurrenceRepository, OccurrenceRepositoryError
    except ImportError as erro:
        raise RoboAusente(str(erro)) from erro

    cfg = _configuracao(Path(arquivo_env), Path(raiz))
    if provedor is None:
        cliente = FirmsApiClient(map_key=cfg.map_key, base_url=cfg.base_url, timeout_seconds=cfg.timeout_seconds,
                                 max_retries=cfg.max_retries)
        try:
            provedor = FirmsHotspotProvider(cliente, FirmsCsvParser(), build_query(cfg))
        except ValueError as erro:  # ConfigurationError é um ValueError
            raise ConsultaFalhou(str(erro)) from erro
    # A mesma montagem do build_fire_monitor do robô, com o provedor e o CSV embrulhados
    guardados = _ProvedorQueGuarda(provedor)
    if do_zero:
        try:
            cfg.output_csv.unlink(missing_ok=True)
        except OSError as erro:  # aberto no Excel, por exemplo
            raise ConsultaFalhou(f"Modo teste: não consegui apagar o CSV do robô ({erro}). Feche o arquivo e tente de novo.") from erro
    csv = _RepositorioQueLembra(CsvOccurrenceRepository(cfg.output_csv, cfg.csv_delimiter))
    # Os filtros do próprio robô (confiança, FRP mínimo e, da versão 1.1, território): a aba nunca fica para trás
    try:
        from firms_monitor.bootstrap import build_filter
    except ImportError:  # robô 1.0, sem build_filter
        def build_filter(c):
            return CompositeFilter([ConfidenceFilter(c.min_numeric_confidence), MinFrpFilter(c.min_frp)])
    try:
        filtro = build_filter(cfg)
    except ValueError as erro:  # TERRITORY_FILTER inválido
        raise ConsultaFalhou(str(erro)) from erro
    confianca, frp_minimo = ConfidenceFilter(cfg.min_numeric_confidence), MinFrpFilter(cfg.min_frp)
    classificador = RiskClassifier.from_thresholds(cfg.risk_medio_frp, cfg.risk_alto_frp, cfg.risk_critico_frp)
    servico = FireMonitorService(provider=guardados, hotspot_filter=filtro, classifier=classificador, repository=csv,
                                 notifier=LogAlertNotifier(), alert_min_level=cfg.alert_min_level)
    try:
        relatorio = servico.run()
    except FirmsApiError as erro:
        raise ConsultaFalhou(f"A NASA não respondeu como esperado: {erro}") from erro
    except OccurrenceRepositoryError as erro:
        raise ConsultaFalhou(f"Não consegui gravar o CSV das ocorrências: {erro}") from erro
    except OSError as erro:  # sem internet, por exemplo
        raise ConsultaFalhou(f"Não consegui consultar a NASA: {erro}") from erro

    def motivo(h) -> str:
        """Por que o filtro do robô tirou este foco. Vazio: foco ativo."""
        if filtro.accepts(h):
            return ""
        if not confianca.accepts(h):
            return "baixa confiança"
        if not frp_minimo.accepts(h):
            return "FRP abaixo do mínimo"
        return "fora do território monitorado"

    unicos = {h.hotspot_id: h for h in guardados.focos}  # sem repetir o mesmo foco
    todos = [(classificador.classify(h), h, motivo(h)) for h in unicos.values()]
    ordem = lambda trio: (-int(trio[0]), -trio[1].frp)  # noqa: E731
    classificados = sorted((t for t in todos if not t[2]), key=ordem)
    descartados = sorted((t for t in todos if t[2]), key=ordem)
    por_nivel = {}
    for nivel, _, _ in classificados:
        por_nivel[nivel.label] = por_nivel.get(nivel.label, 0) + 1
    por_motivo = {}
    for _, _, m in descartados:
        por_motivo[m] = por_motivo.get(m, 0) + 1
    # Os ativos vêm primeiro: se passar do limite, quem fica de fora são os descartados
    no_mapa = (classificados + descartados)[:MAX_FOCOS_NO_MAPA]
    return {
        "consultado_em": datetime.now().strftime("%d/%m às %H:%M"),
        "fonte": cfg.source, "dias": cfg.day_range, "alerta_a_partir_de": cfg.alert_min_level.label,
        "coletados": relatorio.fetched, "ativos": len(classificados), "novos": relatorio.new_occurrences,
        # alertas: os que o robô avisou agora, só os focos novos. em_alerta: todos os ativos do nível de alerta para cima
        "alertas": relatorio.alerts_sent,
        "em_alerta": sum(1 for nivel, _, _ in classificados if nivel >= cfg.alert_min_level),
        "por_nivel": [{"nivel": n.label, "quantidade": por_nivel.get(n.label, 0)} for n in sorted(type(cfg.alert_min_level), reverse=True)],
        "descartados": len(descartados),
        "por_motivo": [{"motivo": m, "quantidade": q} for m, q in sorted(por_motivo.items(), key=lambda par: -par[1])],
        "focos": [{"nivel": nivel.label, "grau": int(nivel), "frp": round(h.frp, 1),
                   "quando": h.acquired_at.strftime("%d/%m %H:%M"), "latitude": h.latitude, "longitude": h.longitude,
                   "satelite": h.satellite, "confianca": h.confidence, "filtrado": m,
                   # um foco descartado nunca entra no CSV do robô, então "novo" e "alerta" só valem para os ativos
                   "novo": not m and h.hotspot_id not in csv.conhecidos, "alerta": not m and nivel >= cfg.alert_min_level}
                  for nivel, h, m in no_mapa],
        "csv": str(cfg.output_csv),
    }
