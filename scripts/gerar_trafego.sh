#!/usr/bin/env bash
# Gera tráfego no painel para as métricas de ouro aparecerem no Grafana (latência, tráfego e erros):
# pedidos normais (página, saúde, API) e alguns de erro de propósito (404 e 403).
#
# Uso (Git Bash no Windows, ou Linux/macOS), com o docker compose rodando:
#   scripts/gerar_trafego.sh [segundos] [endereço]
#   scripts/gerar_trafego.sh 120 http://127.0.0.1:8080
set -euo pipefail

DURACAO="${1:-120}"
BASE="${2:-http://127.0.0.1:8080}"
API=(-H "Content-Type: application/json" -H "X-Painel: 1" -d "[]")

if ! curl -fsS -o /dev/null "$BASE/healthz"; then
  echo "O painel não respondeu em $BASE/healthz. Suba antes: docker compose up -d" >&2
  exit 1
fi

echo "Gerando tráfego em $BASE por $DURACAO s (Ctrl+C para parar)..."
fim=$((SECONDS + DURACAO))
ok=0
erros=0
while ((SECONDS < fim)); do
  for _ in 1 2 3 4 5; do
    curl -s -o /dev/null "$BASE/" && ok=$((ok + 1))
    curl -s -o /dev/null -X POST "${API[@]}" "$BASE/api/estado_automatico" && ok=$((ok + 1))
    curl -s -o /dev/null -X POST "${API[@]}" "$BASE/api/ultima" && ok=$((ok + 1))
  done
  # Erros de propósito: rota que não existe (404) e chamada sem o cabeçalho da ponte (403)
  curl -s -o /dev/null "$BASE/nao-existe" && erros=$((erros + 1))
  curl -s -o /dev/null -X POST -H "Content-Type: application/json" -d "[]" "$BASE/api/ultima" && erros=$((erros + 1))
  sleep 0.2
done
echo "Pronto: $ok pedidos normais e $erros de erro. Veja o dashboard 'Métricas de Ouro' no Grafana."
