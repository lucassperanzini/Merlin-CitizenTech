#!/usr/bin/env bash
# Força a CPU do contêiner do painel acima de 80% para o alerta "CPU acima de 80%" do Grafana disparar.
#
# Roda um laço ocupando 1 núcleo dentro do próprio contêiner do painel (o limite dele é 1 núcleo) pelo tempo
# pedido. O alerta é avaliado a cada 30 s e dispara depois de 1 minuto acima de 80%: com o padrão de 180 s,
# ele passa de Normal para Pending e depois Firing, e volta a Normal quando o laço termina.
#
# Uso (Git Bash no Windows, ou Linux/macOS), na pasta do projeto, com o docker compose rodando:
#   scripts/teste_alerta_cpu.sh [segundos]
# Acompanhe em: Grafana > Alerting > Alert rules > "CPU acima de 80%" (e no dashboard Métricas de Ouro).
set -euo pipefail

DURACAO="${1:-180}"
cd "$(git rev-parse --show-toplevel)"

if [[ -z "$(docker compose ps -q painel 2>/dev/null)" ]]; then
  echo "O contêiner do painel não está rodando. Suba antes: docker compose up -d" >&2
  exit 1
fi

echo "Ocupando 1 núcleo no contêiner do painel por $DURACAO s..."
echo "Acompanhe no Grafana: Alerting > Alert rules > CPU acima de 80%"
docker compose exec -T painel python -c "
import time
fim = time.monotonic() + $DURACAO
while time.monotonic() < fim:
    pass
"
echo "Pronto. A CPU volta ao normal e o alerta volta a Normal em cerca de 1 minuto."
