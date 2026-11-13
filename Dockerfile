# syntax=docker/dockerfile:1
# Painel web de alertas do Merlin (merlin/web): a aba Alertas servida por HTTP, com o robô FIRMS Monitor.
# O resto do Merlin (voz, janela, automação do Windows) é um app de desktop e não roda em contêiner.
#
# Nenhum segredo entra na imagem: as chaves (FIRMS_MAP_KEY, MAPTILER_KEY) chegam por variável de ambiente
# na hora de rodar (docker-compose.yml), e o .dockerignore deixa o .env fora do contexto do build.

ARG PYTHON_IMAGE=python:3.13-alpine

# ---------- Etapa 1: instala as dependências num ambiente virtual isolado ----------
FROM ${PYTHON_IMAGE} AS construcao

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /construcao
COPY requirements-painel.txt ./
COPY vendor/firms_monitor-1.2.0-py3-none-any.whl vendor/

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --require-virtualenv -r requirements-painel.txt \
    # o pip só serve para instalar: fora da imagem final, não vira alvo de vulnerabilidade
    && /opt/venv/bin/pip uninstall --yes pip

# ---------- Etapa 2: imagem final, só com o ambiente pronto e o código do painel ----------
FROM ${PYTHON_IMAGE} AS final

LABEL org.opencontainers.image.title="merlin-painel-alertas" \
      org.opencontainers.image.description="Painel web de alertas de focos de calor (NASA FIRMS) do Merlin CitizenTech"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PAINEL_HOST=0.0.0.0 \
    PAINEL_PORTA=8080

# Correções de segurança do Alpine, e sem o pip do sistema (a aplicação usa o do /opt/venv, já sem pip)
RUN apk upgrade --no-cache \
    && python -m pip uninstall --yes --root-user-action=ignore pip \
    # usuário sem privilégios, sem senha e sem shell de login
    && addgroup -S -g 10001 appgroup \
    && adduser -S -D -H -u 10001 -G appgroup -s /sbin/nologin appuser

WORKDIR /app

COPY --from=construcao /opt/venv /opt/venv
# O código pertence ao root e o appuser só lê: quem invadir o processo não consegue alterar a aplicação
COPY merlin/ merlin/
COPY recursos/ recursos/

# Só a pasta de dados (CSV do robô e última consulta) é gravável, e só pelo appuser
RUN mkdir -p /app/dados/alertas /app/dados/incendio \
    && chown -R appuser:appgroup /app/dados \
    && chmod -R a-w /app/merlin /app/recursos

USER appuser:appgroup

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["python", "-m", "merlin.web"]
