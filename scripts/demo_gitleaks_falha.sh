#!/usr/bin/env bash
# Demonstração do Módulo 3: um commit com uma chave exposta é barrado pelo Gitleaks.
#
# O que faz:
#   1. cria a branch demo/gitleaks-falha-<data> a partir da atual;
#   2. gera credenciais FALSAS (no formato de uma chave da AWS e de um token do GitHub) e faz o commit delas;
#   3. roda o Gitleaks (a mesma imagem da esteira) nesse commit e mostra o bloqueio (código de saída 1);
#   4. explica como ver a esteira falhar no GitHub (pull request para a main) e como limpar tudo.
#
# As chaves são aleatórias e não dão acesso a nada. Elas são montadas na hora, por partes: este arquivo
# não contém nenhuma chave, então ele mesmo não dispara o Gitleaks quando vai para a main.
#
# Uso (Git Bash no Windows, ou Linux/macOS, com o Docker rodando):
#   scripts/demo_gitleaks_falha.sh            cria a branch, o commit e roda o Gitleaks
#   scripts/demo_gitleaks_falha.sh --limpar   volta para a branch anterior e apaga as branches da demo
set -euo pipefail

GITLEAKS_IMAGE="ghcr.io/gitleaks/gitleaks:v8.28.0" # a mesma da esteira (.github/workflows/devsecops.yml)
PREFIXO_BRANCH="demo/gitleaks-falha"
ARQUIVO_VAZADO="demo_vazamento/credenciais.env"

raiz="$(git rev-parse --show-toplevel)"
cd "$raiz"

aleatorio() { # $1: caracteres permitidos, $2: tamanho
  # o head fecha o cano quando já tem o bastante e o tr recebe SIGPIPE: isso é o esperado, não um erro
  LC_ALL=C tr -dc "$1" </dev/urandom 2>/dev/null | head -c "$2" || true
}

if [[ "${1:-}" == "--limpar" ]]; then
  anterior="$(git config --get merlin.demoBranchAnterior || echo main)"
  git switch "$anterior"
  for branch in $(git for-each-ref --format='%(refname:short)' "refs/heads/$PREFIXO_BRANCH-*"); do
    git branch -D "$branch"
    echo "Branch local apagada: $branch"
    echo "  Se ela foi enviada ao GitHub, apague lá também:  git push origin --delete $branch"
  done
  git config --unset merlin.demoBranchAnterior || true
  exit 0
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Há alterações não commitadas. Faça o commit ou guarde-as (git stash) antes da demonstração." >&2
  exit 2
fi

anterior="$(git branch --show-current)"
branch="$PREFIXO_BRANCH-$(date +%Y%m%d-%H%M%S)"
git config merlin.demoBranchAnterior "$anterior"
git switch -c "$branch"

# Credenciais falsas, montadas por partes (o prefixo separado impede que este arquivo case com as regras)
prefixo_aws="AK""IA"
chave_aws="${prefixo_aws}$(aleatorio 'A-Z2-7' 16)"
segredo_aws="$(aleatorio 'A-Za-z0-9' 40)"
prefixo_github="gh""p_"
token_github="${prefixo_github}$(aleatorio 'A-Za-z0-9' 36)"

mkdir -p "$(dirname "$ARQUIVO_VAZADO")"
cat >"$ARQUIVO_VAZADO" <<EOF
# DEMONSTRAÇÃO: credenciais falsas commitadas por engano (nunca faça isso)
AWS_ACCESS_KEY_ID=$chave_aws
AWS_SECRET_ACCESS_KEY=$segredo_aws
GITHUB_TOKEN=$token_github
EOF

git add "$ARQUIVO_VAZADO"
git commit -m "demo: commit com credenciais expostas (deve ser barrado pelo Gitleaks)" >/dev/null
echo
echo "Commit criado na branch $branch com credenciais falsas em $ARQUIVO_VAZADO."
echo "Rodando o Gitleaks (o mesmo da esteira) só neste commit..."
echo

set +e
# MSYS_NO_PATHCONV: no Git Bash do Windows, impede que /repo vire um caminho do Windows
MSYS_NO_PATHCONV=1 docker run --rm -v "$raiz:/repo" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo \
  "$GITLEAKS_IMAGE" git /repo --log-opts="-1 $branch" --redact --no-banner --verbose --exit-code 1
codigo=$?
set -e

echo
if [[ $codigo -eq 1 ]]; then
  echo "BLOQUEADO: o Gitleaks encontrou as credenciais (código de saída 1). Na esteira, este é o passo"
  echo "'1. Secret scanning (Gitleaks)' falhando, e o deploy não acontece."
else
  echo "Inesperado: o Gitleaks terminou com o código $codigo." >&2
fi
echo
echo "Para ver a esteira barrar no GitHub (evidência):"
echo "  git push -u origin $branch"
echo "  e abra um pull request de $branch para a main: o job do Gitleaks fica vermelho."
echo "  NUNCA faça o merge desse pull request."
echo
echo "Para limpar depois:"
echo "  scripts/demo_gitleaks_falha.sh --limpar"
echo "  git push origin --delete $branch   (se tiver enviado)"
exit 0
