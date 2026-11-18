# Merlin

Assistente pessoal por voz para Windows, **100% local**: ouve, entende e responde em voz alta, executa tarefas no computador (abrir e fechar programas, abrir pastas) e responde a perguntas sobre os **protocolos de incêndio da Defesa Civil**, citando o documento e a página. Nada do que você fala sai do seu PC.

Vem com um assistente pronto, o **Merlin**, com tom profissional e tratamento neutro para atender os agentes públicos da Defesa Civil.

O projeto também tem um **painel de alertas de focos de calor** (dados da NASA FIRMS para a Defesa Civil), que roda em contêiner com esteira DevSecOps, infraestrutura como código e observabilidade.

**Índice**

| Parte | Seções |
|---|---|
| **Merlin (assistente por voz no Windows)** | [O que ele faz](#o-que-ele-faz) · [Requisitos](#requisitos) · [Requisitos para testar](#requisitos-para-testar) · [Instalação](#instalação) · [Como usar](#como-usar) · [Como funciona](#como-funciona) · [Privacidade](#privacidade) · [Desenvolvimento](#desenvolvimento) · [Problemas comuns](#problemas-comuns) |
| **Infraestrutura, DevSecOps e Observabilidade** | [Visão geral](#infraestrutura-devsecops-e-observabilidade) · [1. Diagrama da arquitetura](#1-diagrama-da-arquitetura) · [2. Matriz de responsabilidade compartilhada](#2-matriz-de-responsabilidade-compartilhada) · [3. Mapeamento LGPD](#3-mapeamento-lgpd) · [4. Estimativa de custo](#4-estimativa-de-custo) · [5. Guia de reprodução](#5-guia-de-reprodução) |

---

## O que ele faz

- **Ativação por voz:** diga o nome do assistente ("Merlin, abre o chrome").
- **Modo discreto:** um pedido rápido junto com o nome ("Merlin, abre o spotify") é resolvido sem abrir o cartão: a resposta aparece num balão ao lado da bolinha e ele volta a esperar. Conversas, perguntas de confirmação, erros e respostas longas abrem o cartão.
- **Tarefas no computador:** abrir e fechar programas e abrir pastas ("abre o spotify", "fecha o word", "abre a pasta downloads"). Se o programa pedido não estiver instalado, ele avisa e pesquisa o nome no navegador.
- **Várias tarefas numa frase:** "abre o chrome e fecha o telegram" vira uma resposta só ("Abri o chrome e fechei o telegram").
- **Protocolos da Defesa Civil:** "o que é o sistema de comando de incidentes?", "quais equipamentos o brigadista usa?". Quem responde é um modelo especialista (RAG + LoRA sobre 9 manuais e normas de incêndio), que cita a fonte ("Fonte: Apostila do Brigadista, página 49") e diz "não consta" quando a resposta não está nos documentos, em vez de inventar.
- **Conversa:** responde perguntas no jeito da personalidade e lembra o que foi dito na conversa atual.
- **Interrupção:** fale por cima e ele para de falar.
- **Janelas:**
  - **Bolinha (em espera):** fica no canto da tela com o nome do assistente. O anel mostra o estado: cor do assistente normalmente, vermelho com o microfone no mudo, laranja piscando se a IA (Ollama) não responde. Com o mouse por perto, aparecem os botões de configurações, microfone e modo debug (que mostra no cartão uma aba com o raciocínio da IA: o que ela entendeu e decidiu em cada pedido).
  - **Cartão (ativo):** a bolinha cresce para cima e vira um cartão no canto direito, sem cobrir o programa em uso. A resposta aparece junto com a voz, palavra por palavra.
  - **Central:** uma janela só, com abas.
    - *Pastas:* apelidos para as suas pastas ("abre o trabalho"), além das do Acesso Rápido do Windows.
    - *Ajustes:* assistente e voz, modelo de IA.
    - *Ferramentas:* editor de assistentes (cria e edita personalidades sem mexer em código) e skills (tudo o que ele sabe fazer, com um teste de frases; título, descrição e exemplos podem ser editados).
    - Embaixo, o status do sistema ao vivo.

---

## Requisitos

| Item | Observação |
|---|---|
| **Windows 10 ou 11** | Usa recursos do Windows (janelas, botões, o navegador interno WebView2). Não roda em Linux nem macOS. |
| **Python 3.13** | De [python.org](https://www.python.org/downloads/). |
| **Ollama** | O programa que roda a IA localmente: [ollama.com](https://ollama.com/download). |
| **Microfone** | Qualquer um. |
| **Placa de vídeo NVIDIA** (recomendada, com o driver atualizado) | Necessária para as perguntas sobre os protocolos da Defesa Civil (veja a tabela abaixo). Sem ela, a voz, os comandos e a conversa funcionam pelo processador, mais devagar. |
| **WebView2 Runtime** | Já vem no Windows 11 e com o Edge. No Windows 10, se a janela não abrir, instale-o pelo site da Microsoft. |

**Espaço em disco:** ~18 GB: bibliotecas Python ~6 GB (o torch com CUDA é a maior parte), modelos do Merlin ~9 GB e modelo do Ollama ~2,5 GB.

### Requisitos para testar

O Merlin abre e funciona em qualquer PC com Windows. O que depende do computador é **o que funciona e com que rapidez**:

| PC de quem testa | Voz (Whisper) | Comandos e conversa (`qwen3:4b-instruct`) | Perguntas sobre os protocolos (especialista) |
|---|---|---|---|
| **Sem placa NVIDIA** (escritório, notebook comum) | ✅ Usa sozinho o modelo `small` no processador | ✅ Funciona, mais devagar: 1,4 s por pedido e 1 a 3 s por resposta, medidos num processador rápido (num de escritório, deve levar de 2 a 4 vezes mais) | ❌ **Não carrega.** Ele responde "Não consegui carregar o modelo da Defesa Civil", sem travar o resto |
| **NVIDIA com 6 a 8 GB** | ✅ Na placa | ✅ Se faltar espaço na placa, o Ollama põe parte do modelo no processador | ⚠️ Deve carregar (ocupa ~3,7 GB em 4 bits), mas a placa fica no limite. Não foi testado |
| **NVIDIA com 12 GB ou mais** | ✅ | ✅ 0,4 s por pedido | ✅ 3 a 12 s por resposta (a primeira, ~14 s). Tudo junto ocupa 10,3 GB da placa |

- **O especialista exige:** placa NVIDIA a partir da série RTX 20, com o driver atualizado (CUDA 13.2 ou mais novo). As GTX 10xx e mais antigas não servem. Num processador sem placa, cada resposta levou ~2 minutos, o que não serve para conversa por voz.
- **A parte de infraestrutura não depende de nada disso.** O painel de alertas com Prometheus e Grafana ([Guia de reprodução](#5-guia-de-reprodução)) roda em qualquer PC com Docker, sem placa de vídeo.
- **Na Defesa Civil, a ideia é a IA ficar num servidor interno.** Os computadores das pessoas só rodam o Merlin e o reconhecimento de voz no processador. Veja a [Estimativa de custo](#4-estimativa-de-custo).

---

## O que vem no repositório e o que você baixa

### Já está no repositório

| O quê | Onde |
|---|---|
| Código do assistente | `main.py`, `merlin/` |
| Páginas das janelas, sons de ativação e do alarme, esfera | `recursos/` |
| O assistente original, Merlin (não pode ser excluído; "Restaurar original" volta para ele) | `recursos/assistentes_padrao/*.json` |
| **Vozes do Piper** em português (Faber, Cadu, Jeff; ~63 MB cada) | `vozes/*.onnx` |
| Ferramentas (baixar modelos, avaliar a IA, gerar sons) | `ferramentas/` |
| Testes automáticos | `tests/` |
| Ajustes dos assistentes originais | `assistentes_citizentech/*.json` |
| Ajustes das habilidades | `skills/*.json` |
| Amostras de áudio usadas para comparar as vozes do mago (não são necessárias para rodar) | `amostras_mago/` |

### Você baixa de fora

| O quê | Tamanho | Como |
|---|---|---|
| Python 3.13 | – | instalador do python.org |
| Bibliotecas Python (inclui o torch com CUDA e o pacote do especialista) | ~6 GB | `pip install -r requirements.txt` |
| Ollama + o modelo `qwen3:4b-instruct` | ~2,5 GB | instalador do Ollama + `ollama pull` |
| Modelos de reconhecimento de voz (Whisper) | ~2,1 GB | `ferramentas\baixar_modelos.py` → pasta `modelos/` |
| Modelo especialista da Defesa Civil (Qwen2.5-3B, modelo de busca e adaptador LoRA) | ~7 GB | `ferramentas\baixar_modelos.py` → pasta `modelos/huggingface/` |

### Criado no seu PC durante o uso (fora do git)

| Pasta | Conteúdo |
|---|---|
| `.venv/` | o ambiente Python com as bibliotecas |
| `modelos/` | modelos do Whisper e do especialista da Defesa Civil |
| `registros/` | o raciocínio da IA, um arquivo por dia, apagado após 30 dias |
| `merlin_config.json` | suas preferências (assistente, voz, modelo e apelidos de pastas) |

---

## Instalação

Num terminal (PowerShell), na pasta do projeto:

```powershell
# 1. Ambiente Python e bibliotecas (o pacote do especialista vem de um repositório com nomes de arquivo longos)
git config --global core.longpaths true
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Modelos de reconhecimento de voz e o especialista da Defesa Civil (~9 GB, vão para modelos\)
.venv\Scripts\python.exe ferramentas\baixar_modelos.py

# 3. IA local: instale o Ollama (ollama.com) e baixe o modelo padrão
ollama pull qwen3:4b-instruct
```

O modelo padrão é o `qwen3:4b-instruct`. Deixe o Ollama aberto enquanto usa o assistente.

### Trocar o modelo de IA

Baixe outro modelo com `ollama pull` e selecione-o em **Central → Inteligência**. Medidos com as 52 frases de `ferramentas/frases_avaliacao.py`:

| Modelo | Acertos | Por pedido | Observação |
|---|---|---|---|
| `qwen3:4b-instruct` | 47/52 | 0,5 s | **O padrão.** Cabe na placa junto com o especialista (10,3 GB no total) |
| `qwen3:8b` | 41/44 (avaliação anterior, sem a skill de protocolos) | 0,6 s sozinho; 1,4 s ao lado do especialista | Ao lado do especialista, metade dele vai para o processador numa placa de 16 GB |
| `qwen3:4b` | 49/52 | 0,4 s | **Não use.** Essa tag baixa o Qwen3-4B-Thinking, que pensa antes de cada resposta: 11 a 24 s por resposta de conversa |

Quanto menor o modelo, maior a chance de errar ao entender pedidos.

---

## Como usar

```powershell
.venv\Scripts\python.exe main.py
```

Ao abrir, ele calibra o microfone (2 s), carrega os modelos e fica em espera: uma bolinha no canto da tela.

| Diga | O que acontece |
|---|---|
| "**Merlin**" (ou o nome do assistente escolhido) | ativa e cumprimenta |
| "Merlin, abre o spotify" | ativa e abre o programa |
| "fecha o chrome e abre o spotify" | faz as duas tarefas |
| "abre a pasta downloads" | abre a pasta |
| "qual a capital da França?" | responde |
| "o que é um aceiro?" | responde pelos protocolos da Defesa Civil, citando a fonte |
| "abre as suas configurações" | abre a Central |
| "valeu, pode ir" / "pode desligar" | volta para a espera (a bolinha) |

**Outros comportamentos:**
- **Inatividade:** depois de 30 s parado, ele volta sozinho para a espera.
- **Clique:** clicar na bolinha também o ativa.
- **Botões:** na bolinha, passe o mouse para ver os botões. No cartão, ficam no alto: recolher, microfone e Central.

---

## Como funciona

```
microfone
  → detector de voz (Silero)          percebe quando alguém fala e quando parou
  → Whisper (placa de vídeo)          transcreve a frase
  → tem o nome do assistente?         se não tiver e ele estiver em espera, a frase é descartada
  → IA (Ollama): divide as tarefas    "abre o chrome e fecha o telegram" → duas tarefas
  → IA (Ollama): entende cada uma     qual habilidade e qual alvo; regras do código corrigem a IA
  → busca nos protocolos              se a IA achou que é conversa, mas a pergunta é parecida com um trecho dos
                                      manuais, quem responde é o especialista da Defesa Civil
  → habilidades executam              abrir e fechar programa, abrir pasta, consultar protocolo, conversar...
  → resposta única                    "Abri o chrome e fechei o telegram"
  → voz (Piper)                       toca enquanto o texto aparece na janela
```

### Estrutura do código

| Pasta | Responsabilidade |
|---|---|
| `merlin/audio/` | microfone, detector de voz, segmentação das frases, transcrição (Whisper) |
| `merlin/ia/` | conversa com o Ollama: intenções, divisão de tarefas, confirmações, conversa, sugestão de assistentes; e o especialista da Defesa Civil (`especialista.py`) |
| `merlin/habilidades/` | **uma habilidade por arquivo**: descrição e exemplos para a IA, regras, e qual ação executar |
| `merlin/acoes/` | o que é feito no Windows: janelas, programas, pastas, navegador |
| `merlin/personalidades/` | carrega os assistentes (todos em .json): os originais de `recursos/assistentes_padrao/` e os da pasta `assistentes_citizentech/` |
| `merlin/voz/` | síntese (Piper), efeitos, reprodução e interrupção |
| `merlin/nucleo/` | o fluxo de cada pedido, sessão, memória da conversa, raciocínio |
| `merlin/interface/` | janelas: a principal (bolinha e cartão) e a Central (ajustes, editor, habilidades) |
| `merlin/config.py` | ajustes técnicos (tempos, limites, caminhos) |
| `main.py` | monta as peças e liga umas nas outras |

### Personalizar

- **Assistentes:** pela aba **Editor** da Central. Lá você define nome, palavras de chamada, voz, aparência, quem ele é, como ele fala, frases prontas e expressões típicas. A IA local pode sugerir o resto a partir de "Quem ele é". Todos os assistentes são arquivos .json no mesmo formato: o original (Merlin) em `recursos/assistentes_padrao/`, e os seus e os ajustes do original em `assistentes_citizentech/`.
- **Habilidades:** crie um arquivo em `merlin/habilidades/` (veja um vizinho como modelo) e a ação em `merlin/acoes/`. Ela entra sozinha no que a IA lê e nas ações, e aparece na aba Skills da Central, onde você pode ajustar o título, a descrição e os exemplos (ficam em `skills/*.json`).
- **Ajustes técnicos:** em `merlin/config.py`, por exemplo a pausa que encerra uma frase (`PAUSA_FIM_FRASE`) e o tempo de inatividade (`TEMPO_INATIVIDADE`).

---

## Privacidade

- **Tudo roda no seu PC:** reconhecimento de voz, IA e síntese de voz. O assistente só usa a internet para **baixar** modelos e bibliotecas e quando um programa pedido não está instalado (aí ele pesquisa o nome no navegador).
- **Em espera, o microfone fica aberto:** ele transcreve o que é falado perto apenas para procurar o nome do assistente, e o que não tem o nome é descartado.
- **O que fica salvo no disco:**
  - `registros/`: o raciocínio de cada pedido, apagado após 30 dias;
  - `merlin_config.json` e `assistentes_citizentech/`: as suas preferências.

---

## Desenvolvimento

```powershell
# Testes automáticos (não usam microfone nem a IA)
.venv\Scripts\python.exe -m unittest discover -s tests -t .

# Precisão da IA ao entender pedidos (usa o Ollama de verdade)
.venv\Scripts\python.exe ferramentas\avaliar_classificador.py qwen3:4b-instruct
```

Ao criar uma habilidade, acrescente frases dela em `ferramentas/frases_avaliacao.py` e rode a avaliação antes e depois.

---

## Problemas comuns

| Sintoma | O que verificar |
|---|---|
| "Não consegui falar com o meu cérebro" | O Ollama está aberto? O modelo escolhido foi baixado (`ollama list`)? |
| "Não consegui carregar o modelo da Defesa Civil" | Tem placa NVIDIA da série RTX 20 ou mais nova, com o driver atualizado? Veja [Requisitos para testar](#requisitos-para-testar). O motivo exato aparece no terminal, na linha `[ESPECIALISTA]`. |
| "Ainda estou carregando os protocolos" | Normal logo depois de abrir: o especialista carrega em segundo plano por 10 a 25 s. |
| A resposta demora muito ou vem com um texto em inglês antes | O modelo escolhido é o `qwen3:4b`, a versão que pensa antes de responder. Troque para o `qwen3:4b-instruct` em Central → Inteligência. |
| `pip install` falha com "Filename too long" | Rode `git config --global core.longpaths true` e repita. |
| A janela não abre | WebView2 Runtime instalado? |
| Reconhecimento lento | Sem placa NVIDIA, ele usa o modelo `small` no processador. Confira se `modelos\large-v3-turbo` existe. |
| Não reage ao nome | O anel da bolinha está vermelho? É o mudo: passe o mouse e clique no microfone. Senão, fale o nome do assistente escolhido na Central e veja as palavras de chamada no Editor. |
| Aviso de `flash-attn` ou `torchaudio` no terminal | Inofensivo. |

---
---

# Infraestrutura, DevSecOps e Observabilidade

O Merlin é um app de desktop para Windows (janela, microfone, voz, automação do sistema) e não roda em contêiner. O que vai para a infraestrutura é o **painel de alertas de focos de calor**: a mesma página da aba Alertas da Central (`recursos/alertas.html`), servida por HTTP, com o robô **FIRMS Monitor** consultando a NASA na busca automática. O painel mostra os focos de calor e as áreas dos incêndios no mapa, com o risco de cada um.

| Módulo | O que foi feito | Arquivos |
|---|---|---|
| **1. Contêiner** | Imagem multi-stage em `python:3.13-alpine` (77 MB), usuário sem privilégios, sem segredos, sem pip; `docker compose up` sobe o painel e a observabilidade | [Dockerfile](Dockerfile), [.dockerignore](.dockerignore), [docker-compose.yml](docker-compose.yml), [.env.example](.env.example), [merlin/web/](merlin/web/) |
| **2. IaC** | Terraform com o provider Docker: a mesma pilha, com portas só em loopback e bloqueio de portas de administração | [terraform/](terraform/) |
| **3. Esteira** | GitHub Actions: Gitleaks, Semgrep e Trivy em paralelo; deploy por Terraform só se os três passarem | [.github/workflows/devsecops.yml](.github/workflows/devsecops.yml), [scripts/demo_gitleaks_falha.sh](scripts/demo_gitleaks_falha.sh) |
| **4. Observabilidade** | Prometheus, Grafana e cAdvisor; dashboard das 4 métricas de ouro; alerta de CPU acima de 80% | [observability/](observability/), [merlin/web/metricas.py](merlin/web/metricas.py) |

## 1. Diagrama da arquitetura

### Esteira CI/CD (a cada push na `main`)

```mermaid
flowchart LR
    dev["Desenvolvedor<br/>git push"] --> gh["GitHub<br/>branch main"]
    gh --> gl["Job 1 · Gitleaks<br/>segredos no histórico inteiro"]
    gh --> sg["Job 2 · Semgrep<br/>SAST: Python, Dockerfile,<br/>Terraform, Actions"]
    gh --> bd["Job 3 · docker build"] --> tv["Trivy<br/>falha em CRITICAL/HIGH"]
    tv --> art[("imagem aprovada<br/>painel.tar")]
    gl --> ok{"os três<br/>passaram?"}
    sg --> ok
    tv --> ok
    ok -- "não" --> stop["deploy bloqueado"]
    ok -- "sim" --> dp["Job 4 · Deploy"]
    sec[("GitHub Secrets<br/>FIRMS_MAP_KEY<br/>GRAFANA_ADMIN_PASSWORD<br/>MAPTILER_KEY")] -. "TF_VAR_*" .-> dp
    art --> dp
    dp --> tf["terraform init (lock) → validate<br/>→ plan (política de portas) → apply"]
    tf --> smoke["teste de fumaça<br/>painel · Prometheus · Grafana"]
```

Num pull request para a `main`, rodam as três verificações, sem deploy. As GitHub Actions são fixadas pelo hash do commit, e o token da esteira só tem permissão de leitura.

### Infraestrutura (docker compose ou Terraform)

```mermaid
flowchart LR
    subgraph host["Computador local ou executor da esteira"]
        user["Navegador<br/>operador da Defesa Civil"]
        subgraph rede["Rede Docker isolada: monitoramento"]
            painel["painel<br/>python:3.13-alpine · appuser<br/>/ · /api · /healthz · /metrics"]
            cadvisor["cAdvisor<br/>CPU e memória dos contêineres"]
            prom["Prometheus<br/>retenção 15 dias"]
            graf["Grafana<br/>dashboard + alerta CPU > 80%"]
        end
        vol1[("volume painel-dados<br/>CSV de ocorrências<br/>última consulta")]
        vol2[("volume prometheus-dados")]
        vol3[("volume grafana-dados")]
    end
    nasa["NASA FIRMS API<br/>focos de calor"]
    maptiler["MapTiler / OpenStreetMap<br/>fundo do mapa"]

    user -- "127.0.0.1:8080" --> painel
    user -- "127.0.0.1:3001" --> graf
    user -- "127.0.0.1:9090" --> prom
    painel -- "HTTPS" --> nasa
    user -- "HTTPS (imagens do mapa)" --> maptiler
    prom -- "coleta /metrics" --> painel
    prom -- "coleta" --> cadvisor
    graf -- "consulta" --> prom
    painel --- vol1
    prom --- vol2
    graf --- vol3
```

- **Portas:** só em `127.0.0.1`; nada fica aberto para a rede. O cAdvisor nem é publicado. Nenhuma porta de administração (SSH 22, RDP 3389, Docker 2375/2376, WinRM 5985/5986, VNC 5900, Telnet 23) pode ser publicada: o Terraform recusa no `plan`.
- **Contêineres:** sistema de arquivos só leitura (painel), `cap_drop: ALL`, `no-new-privileges`, limites de CPU e memória, logs com rotação (3 × 10 MB).
- **Painel sem login:** abre no perfil **operador** (só vê). O perfil administrador, que muda a busca automática, é ligado por variável de ambiente. A API aceita só uma lista fixa de funções e um cabeçalho próprio, o que barra chamadas vindas de outros sites. As respostas trazem CSP, `X-Frame-Options: DENY` e `nosniff`.

### Observabilidade: as 4 métricas de ouro

| Métrica | De onde vem | Consulta (PromQL) |
|---|---|---|
| **Latência** | painel, `/metrics` (histograma) | `histogram_quantile(0.95, sum by (le) (rate(painel_http_request_duration_seconds_bucket[5m])))` |
| **Tráfego** | painel, `/metrics` | `sum(rate(painel_http_requests_total[5m]))` |
| **Erros** | painel, `/metrics` | taxa de respostas 4xx/5xx e `painel_alertas_buscas_total{resultado="erro"}` (falhas na NASA) |
| **Saturação** | cAdvisor | `rate(container_cpu_usage_seconds_total[1m])` e `container_memory_working_set_bytes / container_spec_memory_limit_bytes` |

O dashboard **"Merlin CitizenTech · Métricas de Ouro"** e a regra **"CPU acima de 80%"** sobem sozinhos com o Grafana (provisionamento em [observability/grafana/provisioning/](observability/grafana/provisioning/)). A regra exportada pelo próprio Grafana está em [observability/grafana/exportado/](observability/grafana/exportado/alerta-cpu-acima-de-80.yaml).

## 2. Matriz de responsabilidade compartilhada

Hoje a infraestrutura é local (Docker no computador da Defesa Civil, ou no executor do GitHub Actions). A última coluna mostra como a divisão muda se ela for para a nuvem (AWS EC2, por exemplo).

| Camada | Provedor | Nós (código e equipe) | Na nuvem (EC2) |
|---|---|---|---|
| **Hardware, rede física, energia** | Dono do computador / Microsoft (executores do GitHub) | – | AWS |
| **Sistema operacional do host** | Microsoft (Windows) / GitHub (Ubuntu dos executores) | Manter o Windows e o Docker Desktop atualizados | **Nós** (atualizações do Linux da EC2) |
| **Motor de contêiner** | Docker (Docker Desktop / Engine) | Configuração: rede isolada, portas em loopback | Nós |
| **Imagens base** (`python:3.13-alpine`, Prometheus, Grafana, cAdvisor) | Mantenedores das imagens oficiais | Fixar versões, `apk upgrade`, scan com Trivy a cada push | Nós |
| **Imagem do painel** | – | Multi-stage, `appuser`, sem pip, sem segredos, só leitura | Nós |
| **Código da aplicação** | – | SAST (Semgrep), testes, cabeçalhos de segurança, validação de entradas | Nós |
| **Dependências Python** | Mantenedores dos pacotes (PyPI) | Versões fixas em `requirements-painel.txt`; Trivy acusa vulnerabilidades | Nós |
| **Segredos** | GitHub (cofre dos Secrets, mascarados nos logs) | Nunca no Git ou na imagem (Gitleaks barra); `.env` e `*.tfvars` no `.gitignore`; trocar as chaves se vazarem | AWS Secrets Manager (opcional) |
| **Infraestrutura como código** | HashiCorp (Terraform) e o provider Docker | Política de portas, lock do provider com hash, estado fora do Git | Nós + *security groups* da AWS |
| **Esteira CI/CD** | GitHub (executores, isolamento entre execuções) | Actions fixadas por hash, token só leitura, deploy só da `main` | Igual |
| **Dados de focos de calor** | NASA FIRMS (disponibilidade e qualidade) | Tratar falhas da API (contadas na métrica de erros), não depender de um único dado | Igual |
| **Mapa** | MapTiler / OpenStreetMap | Conferir a chave antes de usar; cair para o OpenStreetMap se ela falhar | Igual |
| **Monitoramento e alertas** | Grafana Labs, Prometheus (software) | Dashboard, regra de alerta, atender o alerta | Igual |
| **Acesso de pessoas** | – | Senha forte do Grafana (12+ caracteres), painel no perfil operador, portas só locais | IAM da AWS + VPN |

## 3. Mapeamento LGPD

**Resumo:** o painel de alertas **não trata dados pessoais de cidadãos**. Os focos de calor são coordenadas de pixels de satélite, dados públicos da NASA, e não identificam pessoas. Os dados pessoais do projeto estão no **Merlin desktop** (voz e preferências de quem o usa), que fica só no computador, e na **conta de administrador do Grafana**.

### Onde cada dado fica e como é protegido

| Dado | É pessoal? | Onde fica | Proteção | Retenção |
|---|---|---|---|---|
| Focos de calor (latitude, longitude, FRP, satélite, horário) | Não (dado público da NASA) | Volume `painel-dados`: `dados/incendio/ocorrencias.csv` e `dados/alertas/ultima_consulta.json` | Só o usuário `appuser` grava; o resto do contêiner é só leitura; acesso pela porta local | O CSV acumula as ocorrências (histórico para a Defesa Civil); a última consulta é substituída a cada busca |
| Chaves da NASA e do MapTiler, senha do Grafana | Não pessoais, mas **segredos** | `.env` (local) e GitHub Secrets (esteira) | Fora do Git (`.gitignore`) e da imagem (`.dockerignore`); Gitleaks barra commits com chaves; Secrets mascarados nos logs | Até serem trocadas |
| Estado do Terraform | Contém os segredos em texto puro | `terraform/terraform.tfstate` (local) | Fora do Git (`.gitignore`); na esteira, some com o executor | Até o próximo `apply`/`destroy` |
| Conta de administrador do Grafana (usuário, sessões) | **Sim** (identifica quem administra) | Volume `grafana-dados` | Senha forte obrigatória, cadastro de novos usuários desligado, sem acesso anônimo, cookie `SameSite=strict`, porta local | Enquanto o volume existir |
| Métricas (latência, tráfego, CPU) | Não (nenhum IP ou usuário vira rótulo) | Volume `prometheus-dados` | Rede interna do Docker; porta local | 15 dias |
| Logs dos contêineres | Não no nível INFO (o IP de quem acessa só aparece no nível DEBUG) | Docker, `json-file` | Rotação: 3 arquivos de 10 MB por contêiner | Até a rotação |
| **Merlin desktop:** áudio do microfone | **Sim** | Só na memória, transcrito no próprio PC | Nada sai do computador; frases sem o nome do assistente são descartadas | Não é gravado |
| **Merlin desktop:** raciocínio da IA (o que a pessoa pediu) | **Sim** | `registros/` | Fora do Git; só no PC | Apagado após 30 dias |
| **Merlin desktop:** amostras de voz clonada | **Sim, dado biométrico (sensível, art. 5º, II)** | `vozes/clonadas/` | Fora do Git; só no PC; usar só com consentimento expresso de quem tem a voz | Até a pessoa apagar |
| **Merlin desktop:** preferências (caminhos de pastas) | Sim (podem conter nomes) | `merlin_config.json`, `assistentes/rick.json` | Fora do Git; só no PC | Até a pessoa apagar |

### Princípios aplicados

- **Minimização (art. 6º, III):** o painel não coleta nada de quem o acessa (sem login, sem cookies próprios, sem IP nas métricas).
- **Segurança (art. 46):** segredos fora do código, contêineres sem privilégios, portas só locais, esteira que barra vazamentos e vulnerabilidades.
- **Prevenção (art. 6º, VIII):** o Gitleaks impede que uma chave chegue ao repositório, e o Trivy, que uma vulnerabilidade conhecida chegue à produção.
- **Base legal:** os focos de calor apoiam a execução de políticas públicas pela Defesa Civil (art. 7º, III, e art. 23). As amostras de voz clonada exigem consentimento específico e destacado (art. 11, I). *A validação jurídica fica com o encarregado de dados (DPO) do órgão.*
- **Direitos do titular (art. 18):** para apagar os dados do Merlin desktop, basta apagar `registros/`, `vozes/clonadas/` e `merlin_config.json`. Para a conta do Grafana, Administration → Users.
- **Se uma chave vazar:** trocá-la na NASA, no MapTiler ou no Grafana, atualizar o `.env` e os GitHub Secrets, e reescrever o histórico se ela chegou a ser commitada.

## 4. Estimativa de custo

O custo calculado aqui é o da **hospedagem**. Cada parte do sistema fica num lugar:

| Parte | Onde roda | Entra no custo? |
|---|---|---|
| IA: Ollama com `qwen3:4b-instruct` e o especialista da Defesa Civil | Servidor hospedado | **Sim** |
| Painel de alertas + Prometheus, Grafana e cAdvisor | Servidor hospedado | **Sim** |
| Merlin com reconhecimento de voz (Whisper), voz (Piper) e controle das janelas | Computadores que a Defesa Civil já tem | Não |

Os computadores falam com o Ollama pela variável `OLLAMA_HOST`, que a biblioteca do Ollama já lê. Por exemplo: `setx OLLAMA_HOST http://ia.defesacivil.interno:11434`. Para essa parte, não precisa mudar o código.

**Ainda falta para o especialista:** hoje ele roda dentro do Merlin, em cada computador. Para ir para o servidor, falta subir a API que o próprio pacote traz (`defesacivil_llm/api.py`, rotas `/perguntar` e `/saude`) e fazer o Merlin chamá-la em vez de carregar o modelo.

O provedor considerado é a AWS em São Paulo (`sa-east-1`). Assim os dados ficam no Brasil, e a distância até os computadores é menor.

As referências da conta:
- **Preços:** [API pública de preços da AWS](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/region_index.json), a mesma da [AWS Pricing Calculator](https://calculator.aws/), na tabela de 14/11/2026.
- **Câmbio:** dólar a **R$ 5,56**, fechamento PTAX de 11/11/2026.
- **Impostos:** não estão incluídos. Preços e câmbio mudam, então refaça a conta antes de contratar.

### O que cada servidor precisa

| Servidor | Necessidade | Máquina escolhida |
|---|---|---|
| IA | Uma placa de vídeo com pelo menos 8 GB, de preferência 12 GB ou mais. Medido: o `qwen3:4b-instruct` ocupa 3,5 GB da placa, e o especialista em 4 bits, 3,7 GB; os dois juntos dão ~7,2 GB. Só no processador, o especialista levou ~2 minutos por resposta | **`g4dn.xlarge`**: 4 vCPU, 16 GB de RAM e NVIDIA T4 de 16 GB. É a máquina com placa de vídeo mais barata em São Paulo |
| Painel e observabilidade | ~175 MB de RAM e ~0,3% de um núcleo somando os 4 contêineres (medido com `docker stats`). Disco de 1,6 GB para as imagens + ~0,3 GB para 15 dias de métricas. Fica ligado 24 h, porque a busca da NASA roda de hora em hora | **`t3.small`**: 2 vCPU e 2 GB de RAM, com folga |

### Servidor da IA (`g4dn.xlarge`)

| Item | Preço unitário | 24 h, sob demanda | 24 h, reservada por 1 ano | Só no expediente: 12 h × 22 dias úteis = 264 h |
|---|---|---|---|---|
| Máquina | US$ 0,894/h (reservada: US$ 0,610/h) | US$ 652,62 | US$ 445,30 | US$ 236,02 |
| Disco EBS gp3 de 50 GB (sistema, driver NVIDIA e modelo) | US$ 0,152/GB-mês, cobrado mesmo com a máquina desligada | US$ 7,60 | US$ 7,60 | US$ 7,60 |
| IP fixo (Elastic IP) | US$ 0,005/h, cobrado mesmo com a máquina desligada | US$ 3,65 | US$ 3,65 | US$ 3,65 |
| Saída de dados | US$ 0,15/GB. Cada resposta tem poucos KB, então o volume cabe nos 100 GB/mês gratuitos | US$ 0,00 | US$ 0,00 | US$ 0,00 |
| **Total** | | **US$ 663,87 ≈ R$ 3.691** | **US$ 456,55 ≈ R$ 2.538** | **US$ 247,27 ≈ R$ 1.375** |

No modo de expediente, a máquina liga e desliga sozinha por um agendamento (EventBridge Scheduler), sem custo nesse volume. A reserva de 1 ano não compensa nesse modo, porque cobra as 730 h do mês mesmo com a máquina desligada.

### Servidor do painel (`t3.small`, 24 h)

| Item | Preço unitário | Sob demanda | Reservada por 1 ano |
|---|---|---|---|
| Máquina | US$ 0,0336/h (reservada: US$ 0,0193/h) | US$ 24,53 | US$ 14,09 |
| Disco EBS gp3 de 20 GB | US$ 0,152/GB-mês | US$ 3,04 | US$ 3,04 |
| IP público | US$ 0,005/h | US$ 3,65 | US$ 3,65 |
| Backup (snapshot de ~2 GB) | US$ 0,068/GB-mês | US$ 0,14 | US$ 0,14 |
| Saída de dados | ~2 GB/mês (página de 300 KB + resultado de 735 KB por abertura), dentro dos 100 GB gratuitos | US$ 0,00 | US$ 0,00 |
| **Total** | | **US$ 31,36 ≈ R$ 174** | **US$ 20,92 ≈ R$ 116** |

Se a IA ficar ligada 24 h, o painel pode rodar na própria `g4dn.xlarge`, e a `t3.small` deixa de ser necessária.

### Ligação segura entre os computadores e a IA (opcional, recomendada)

O Ollama não tem senha nem criptografia, e os pedidos levam o que as pessoas falaram. A regra mínima, sem custo, é que o firewall da AWS (security group) só aceite a porta 11434 vindo do IP público da Defesa Civil.

Para criptografar o caminho, use uma VPN entre a rede da Defesa Civil e a AWS (Site-to-Site VPN):

| Item | Preço unitário | Por mês |
|---|---|---|
| Conexão VPN | US$ 0,05/h × 730 h | US$ 36,50 ≈ **R$ 203** |

### Resumo

| Cenário | Por mês | Por ano |
|---|---|---|
| **Recomendado:** IA só no expediente (sob demanda) + painel 24 h (`t3.small` reservada) | **≈ R$ 1.491** | ≈ R$ 17.894 |
| Recomendado + VPN | ≈ R$ 1.694 | ≈ R$ 20.329 |
| Tudo 24 h numa `g4dn.xlarge` reservada por 1 ano | ≈ R$ 2.538 | ≈ R$ 30.461 |
| Tudo 24 h numa `g4dn.xlarge` sob demanda | ≈ R$ 3.691 | ≈ R$ 44.293 |

Ficam de fora da conta porque custam R$ 0:

| Item | Por que é gratuito |
|---|---|
| GitHub Actions | O repositório é público, e repositórios públicos não pagam minutos. Se ficar privado, o plano Free inclui 2.000 min/mês. Cada execução da esteira gasta 4 minutos cobráveis, o que dá ~500 execuções |
| API NASA FIRMS | Gratuita até 5.000 consultas a cada 10 min. A busca automática faz 1 por hora |
| MapTiler | Plano gratuito de 100 mil pedidos de imagens/mês. Os mapas vão direto do MapTiler para o navegador. Sem a chave, o painel usa o OpenStreetMap |
| Ollama, Docker Engine, Prometheus, Grafana OSS, cAdvisor, Terraform, Gitleaks, Semgrep, Trivy | Software livre |

## 5. Guia de reprodução

### Pré-requisitos

| Ferramenta | Para quê | Instalação no Windows |
|---|---|---|
| Git (com o Git Bash) | Clonar e rodar os scripts | `winget install Git.Git` |
| Docker Desktop | Rodar a pilha | `winget install Docker.DockerDesktop` |
| Terraform 1.6 ou mais novo | Só para o caminho com Terraform | `winget install Hashicorp.Terraform` |
| Chave da API FIRMS (gratuita) | Buscar os focos de calor | [firms.modaps.eosdis.nasa.gov/api/map_key](https://firms.modaps.eosdis.nasa.gov/api/map_key/) |

No Linux ou macOS, os comandos são os mesmos (troque `copy` por `cp`).

### Passo 1: clonar e configurar

```powershell
git clone https://github.com/lucassperanzini/Merlin-CitizenTech.git
cd Merlin-CitizenTech
copy .env.example .env
```

No `.env`, preencha pelo menos:
- `FIRMS_MAP_KEY`: a chave da NASA;
- `GRAFANA_ADMIN_PASSWORD`: uma senha com 12 caracteres ou mais.

O `.env` nunca vai para o Git nem para a imagem.

### Passo 2 (caminho A): subir com o Docker Compose

```powershell
docker compose up -d --build
docker compose ps
```

Em cerca de 1 minuto, todos ficam `Up` e o painel, `healthy`:

| Serviço | Endereço | Acesso |
|---|---|---|
| Painel de alertas | http://127.0.0.1:8080 | sem login (perfil operador) |
| Grafana | http://127.0.0.1:3001 | `admin` e a senha do `.env` |
| Prometheus | http://127.0.0.1:9090 | sem login |

As portas mudam no `.env` (`PAINEL_PORTA_HOST`, `GRAFANA_PORTA_HOST`, `PROMETHEUS_PORTA_HOST`). O Grafana usa a 3001 porque a 3000 costuma estar ocupada (Open WebUI, por exemplo).

Para parar: `docker compose down`. Para apagar também os dados: `docker compose down -v`.

### Passo 2 (caminho B): subir com o Terraform

Use um caminho **ou** o outro: os dois usam as mesmas portas. Antes, `docker compose down`.

```powershell
docker build -t merlin-painel-alertas:local .
cd terraform
copy terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
terraform output
```

No `terraform.tfvars`, preencha `firms_map_key` e `grafana_admin_password`. A linha `docker_host` do modelo já vem para o Windows; no Linux ou macOS, apague-a.

Para desfazer: `terraform destroy`.

### Passo 3: testar

**Testes automáticos do painel** (servidor, métricas e áreas dos incêndios), num Python qualquer, sem instalar nada no computador:

```powershell
docker run --rm -v "${PWD}:/src:ro" -w /src python:3.13-alpine sh -c "pip install -q -r requirements-painel.txt && python -m unittest tests.test_painel_web tests.test_manchas"
```

São 21 testes. A suíte completa (`python -m unittest discover -s tests`) precisa do ambiente do Merlin desktop: veja [Instalação](#instalação).

**Política de portas do Terraform** (cada um destes deve ser recusado):

```powershell
cd terraform
terraform plan -var endereco_publicacao=0.0.0.0
terraform plan -var 'portas={painel=22,prometheus=9090,grafana=3001}'
```

**Métricas de ouro e alerta** (no Git Bash, com a pilha rodando):

```bash
scripts/gerar_trafego.sh 120   # tráfego normal + erros 404/403: enche os gráficos de latência, tráfego e erros
scripts/teste_alerta_cpu.sh    # 1 núcleo ocupado por 3 min: o alerta vai de Normal a Pending e Firing
```

Acompanhe em: Grafana → Dashboards → Merlin CitizenTech → **Métricas de Ouro**, e em Alerting → Alert rules → **CPU acima de 80%**.

**Esteira e demonstração do Gitleaks:**

1. Cadastre os segredos no GitHub, em Settings → Secrets and variables → Actions:
   - `FIRMS_MAP_KEY` (obrigatório);
   - `GRAFANA_ADMIN_PASSWORD` (obrigatório);
   - `MAPTILER_KEY` (opcional).
2. Para pedir aprovação manual antes do deploy: Settings → Environments → `producao` → Required reviewers.
3. Um push na `main` roda a esteira: os 4 jobs devem ficar verdes.
4. Para ver o Gitleaks barrar um vazamento (no Git Bash, com a árvore de trabalho limpa):

   ```bash
   scripts/demo_gitleaks_falha.sh                  # cria uma branch com credenciais FALSAS e mostra o bloqueio
   git push -u origin demo/gitleaks-falha-<data>   # o nome aparece na saída do script
   ```

   Abra um pull request dessa branch para a `main`: o job **1. Secret scanning (Gitleaks)** fica vermelho e o deploy não roda. **Não faça o merge.** Depois, limpe:

   ```bash
   scripts/demo_gitleaks_falha.sh --limpar
   git push origin --delete demo/gitleaks-falha-<data>
   ```
