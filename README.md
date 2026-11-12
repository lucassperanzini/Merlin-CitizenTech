# Merlin

Assistente pessoal por voz para Windows, **100% local**: ouve, entende e responde em voz alta e executa tarefas no computador (abrir e fechar programas, pesquisar na internet, clicar em botões). Nada do que você fala sai do seu PC.

Vem com um assistente pronto, o **Merlin** (um mordomo digital, com uma esfera 3D), e você pode criar outros pela própria interface.

---

## O que ele faz

- **Ativação por voz:** diga o nome do assistente ("Merlin, abre o chrome").
- **Modo discreto:** um pedido rápido junto com o nome ("Merlin, abre o spotify") é resolvido sem abrir o cartão: a resposta aparece num balão ao lado da bolinha e ele volta a esperar. Conversas, perguntas de confirmação, erros e respostas longas abrem o cartão.
- **Tarefas no computador:** abrir e fechar programas, pesquisar na internet, clicar em botões de qualquer janela ("dá play", "salva", "clica em cancelar no word"). Antes de clicar em algo perigoso (excluir, pagar, enviar), ele pergunta.
- **Várias tarefas numa frase:** "abre o chrome e fecha o telegram" vira uma resposta só ("Abri o chrome e fechei o telegram").
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
| **Placa de vídeo NVIDIA** (recomendada, com o driver atualizado) | O reconhecimento de voz e a IA ficam mais rápidos nela. Sem placa NVIDIA, tudo roda no processador, com um modelo de voz menor e respostas mais lentas. |
| **WebView2 Runtime** | Já vem no Windows 11 e com o Edge. No Windows 10, se a janela não abrir, instale-o pelo site da Microsoft. |

**Espaço em disco:** ~6 GB na instalação básica.

---

## O que vem no repositório e o que você baixa

### Já está no repositório

| O quê | Onde |
|---|---|
| Código do assistente | `main.py`, `merlin/` |
| Páginas das janelas, sons de ativação, olho e esfera | `recursos/` |
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
| Bibliotecas Python | ~2,5 GB | `pip install -r requirements.txt` |
| Ollama + um modelo de IA | ~5 GB | instalador do Ollama + `ollama pull` |
| Modelos de reconhecimento de voz (Whisper) | ~2,1 GB | `ferramentas\baixar_modelos.py` → pasta `modelos/` |

### Criado no seu PC durante o uso (fora do git)

| Pasta | Conteúdo |
|---|---|
| `.venv/` | o ambiente Python com as bibliotecas |
| `modelos/` | modelos do Whisper |
| `registros/` | o raciocínio da IA, um arquivo por dia, apagado após 30 dias |
| `merlin_config.json` | suas preferências (assistente, voz, modelo e apelidos de pastas) |

---

## Instalação

Num terminal (PowerShell), na pasta do projeto:

```powershell
# 1. Ambiente Python e bibliotecas
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Modelos de reconhecimento de voz (~2,1 GB, vão para modelos\)
.venv\Scripts\python.exe ferramentas\baixar_modelos.py

# 3. IA local: instale o Ollama (ollama.com) e baixe o modelo padrão
ollama pull qwen3:8b
```

O modelo padrão é o `qwen3:8b`. Deixe o Ollama aberto enquanto usa o assistente.

### Se o modelo ficar lento no seu PC

Baixe outro modelo com `ollama pull` e selecione-o em **Central → Inteligência**. Sem essa escolha, o assistente continua procurando o `qwen3:8b`.

| Sua máquina | Modelo | Observação |
|---|---|---|
| Placa com 8 GB ou mais | `qwen3:8b` | O padrão e o mais testado |
| Placa com cerca de 6 GB | `qwen2.5:7b` | Bom para entender pedidos |
| Placa fraca ou só processador | `qwen3:4b` | Menor e mais rápido; não foi testado |
| Muito limitada | `llama3.2` | O mais leve; deve errar mais |

Quanto menor o modelo, maior a chance de errar ao entender pedidos. As memórias indicadas são aproximadas.

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
| "fecha o chrome e pesquisa receita de bolo" | faz as duas tarefas |
| "dá play" / "clica em salvar no word" | clica no botão |
| "qual a capital da França?" | responde |
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
  → habilidades executam              abrir programa, clicar, pesquisar, conversar...
  → resposta única                    "Abri o chrome e fechei o telegram"
  → voz (Piper)                       toca enquanto o texto aparece na janela
```

### Estrutura do código

| Pasta | Responsabilidade |
|---|---|
| `merlin/audio/` | microfone, detector de voz, segmentação das frases, transcrição (Whisper) |
| `merlin/ia/` | conversa com o Ollama: intenções, divisão de tarefas, confirmações, conversa, sugestão de assistentes |
| `merlin/habilidades/` | **uma habilidade por arquivo**: descrição e exemplos para a IA, regras, e qual ação executar |
| `merlin/acoes/` | o que é feito no Windows: janelas, botões, programas, navegador |
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

- **Tudo roda no seu PC:** reconhecimento de voz, IA e síntese de voz. O assistente só usa a internet para **baixar** modelos e bibliotecas e para o que você pedir, como pesquisar ou abrir um site.
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
.venv\Scripts\python.exe ferramentas\avaliar_classificador.py qwen3:8b
```

Ao criar uma habilidade, acrescente frases dela em `ferramentas/frases_avaliacao.py` e rode a avaliação antes e depois.

---

## Problemas comuns

| Sintoma | O que verificar |
|---|---|
| "Não consegui falar com o meu cérebro" | O Ollama está aberto? O modelo escolhido foi baixado (`ollama list`)? |
| A janela não abre | WebView2 Runtime instalado? |
| Reconhecimento lento | Sem placa NVIDIA, ele usa o modelo `small` no processador. Confira se `modelos\large-v3-turbo` existe. |
| Não reage ao nome | O anel da bolinha está vermelho? É o mudo: passe o mouse e clique no microfone. Senão, fale o nome do assistente escolhido na Central e veja as palavras de chamada no Editor. |
| Aviso de `flash-attn` ou `torchaudio` no terminal | Inofensivo. |
