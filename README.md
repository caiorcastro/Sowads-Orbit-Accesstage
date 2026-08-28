# Sowads Orbit — Accesstage

Motor de conteúdo SEO/AIO para escalar a autoridade digital da **Accesstage** no segmento financeiro B2B, posicionando a **Plataforma Veragi** como referência técnica em gestão financeira, integrações bancárias e crédito corporativo.

Desenvolvido pela [Sowads](https://sowads.com.br) — agência especializada em SEO, AIO e estratégia de mídia.

---

## O que este projeto faz

Dado um CSV de temas, o Sowads Orbit:

1. **Gera artigos HTML** prontos para o editor do HubSpot, com SEO/AIO incorporado — sem links, sem imagens no conteúdo, sem JSON-LD
2. **Valida a qualidade** (score 0–100) e **corrige automaticamente** quando necessário (self-healing)
3. **Atribui imagens** da biblioteca existente do WordPress via matching temático (Jaccard)
4. **Gera copies sociais** para LinkedIn, Instagram e Facebook derivados de cada artigo
5. **Exporta events CSV** no formato do backend Sowads para agendamento de posts
6. **Prepara e importa drafts no HubSpot** pelo importador CSV oficial, controlado via Chrome
7. **Gera mockup sites** (preview HTML local) para aprovação do cliente antes de publicar

---

## Estrutura

```
engine/
  content_engine.py     ← motor principal: prompt → OpenRouter → QA → CSV
  publisher.py          ← publica no WP via XML-RPC
  social_agent.py       ← copies por rede + events CSV
  media_indexer.py      ← indexa biblioteca WP, match temático Jaccard
  qa_validator.py       ← score 0-100 + self-healing
  topic_creator.py      ← brainstorm de temas

tools/
  monitor.py            ← monitor em tempo real
  optimizer.py          ← otimização AIO em lote
  bing_indexnow.py      ← push IndexNow para Bing
  check_models.py       ← lista modelos disponíveis no OpenRouter
  preview_generator.py  ← gera HTML mock do blog para aprovação do cliente
  hubspot_browser_import.py ← prepara CSV oficial e controla a importação de drafts no Chrome
  merge_retry.py        ← mescla CSV de retry no batch principal
  benchmark.py          ← benchmark de múltiplos modelos (output/testes/)
  auditor.py            ← auditoria semântica e SEO via LLM avaliador

config/
  schema_orbit_ai_v1.json   ← regras técnicas de SEO/AIO/estrutura HTML

client/                       ← documentos do cliente (versionados)
  briefing_cliente.md         ← briefing original Accesstage
  guia_agente.md              ← tom, keywords obrigatórias, blacklist, argumentos por módulo
  dossie_produtos.md          ← referência técnica completa dos módulos Veragi
  diretrizes.md               ← guia operacional: compliance, SEO, checklist
  credentials.env             ← NUNCA commitado: WP + redes sociais

briefings/              ← pesquisas de mercado por vertical (injetadas no prompt)
output/                 ← tudo que sai (gitignored)
  articles/             ← CSVs de artigos gerados + CSVs de retry
  social/               ← TXTs de copies por rede
  events/               ← CSVs de eventos para backend Sowads
  reports/              ← relatórios de produção + media_index.json
  preview/              ← HTML mock do blog para aprovação (index.html + artigos)
  testes/               ← outputs do benchmark por modelo
  audit/                ← relatórios de auditoria semântica
```

---

## Pipeline rápido

```bash
# 1. Gerar artigos (nunca publica automaticamente)
./run_lotes.sh

# 2. Preview local para aprovação do cliente
python3 tools/preview_generator.py

# 3. Gerar copies sociais + events CSV
python3 engine/social_agent.py --count 40

# 4. Preparar CSV HubSpot com preflight anti-duplicidade
python3 tools/hubspot_browser_import.py --csv output/articles/<batch>.csv

# 5. Abrir o importador oficial no Chrome (para antes da confirmação final)
python3 tools/hubspot_browser_import.py --csv output/articles/<batch>.csv --browser

# 6. Permitir importação como draft (ainda exige digitar IMPORTAR DRAFTS)
python3 tools/hubspot_browser_import.py --csv output/articles/<batch>.csv --browser --commit-drafts

# 7. Indexar no Bing (opcional, apenas depois de publicar)
python3 tools/bing_indexnow.py

# Monitorar progresso em tempo real
python3 tools/monitor.py
```

---

## Modelos disponíveis

| Modelo | Velocidade | Custo/M (in/out) | Uso recomendado |
|---|---|---|---|
| `google/gemini-2.5-flash` | ~15s/art | $0.30 / $2.50 | **Padrão de produção** |
| `google/gemini-2.5-flash-lite` | ~8s/art | $0.10 / $0.40 | Alto volume / budget reduzido |
| `anthropic/claude-opus-4.7` | ~40s/art | $15.00 / $75.00 | Qualidade editorial máxima (artigos flagship) |
| `deepseek/deepseek-chat-v3-0324` | ~40s/art | $0.20 / $0.77 | Custo-benefício intermediário |
| `deepseek/deepseek-v4-pro` | ~170s/art | $0.44 / $0.87 | Qualidade alta, mas lento — risco de timeout |

Benchmarks completos (25 modelos testados): https://caiorcastro.github.io/orbit-audit-accesstage-abr26/

---

## Configuração

### 1. Dependências

```bash
pip install requests pandas colorama playwright pytest beautifulsoup4
```

### 2. Credenciais

`.env` na raiz (gitignored):
```env
OPENROUTER_API_KEY=sk-or-v1-...
BING_INDEXNOW_KEY=opcional
```

O blog da Accesstage é HubSpot, portal `457604`. A automação de drafts usa um perfil
Chrome local persistente em `.hubspot-browser-profile/` (gitignored), sem copiar cookies para
arquivos `.env`. No primeiro `--browser`, faça login interativamente na janela aberta pelo script.
Depois disso, seleção do Blog Accesstage, upload, mapeamento das nove colunas, importação como
rascunho e reconciliação dos títulos/status são automatizados.

### 3. Temas de entrada

CSV em `output/articles/lote_<vertical>_temas.csv`:
```csv
topic_pt,vertical,category
"A Importância da Plataforma de Gestão Financeira","fintech","SEO & AIO"
```

---

## QA Score

| Condição | Penalidade |
|---|---|
| FAQ ausente | -20 |
| Hyperlinks no conteúdo | -15 |
| Word count < 700 | -15 |
| H1 no conteúdo | -10 |
| Word count > 1.800 | -12 |
| Word count > 2.000 | -25 → self-heal |

Score mínimo para publicação: **80/100**. Artigos abaixo de 80 são reprocessados automaticamente (até 2 tentativas).

---

## Benchmark & Auditoria

```bash
# Rodar benchmark em múltiplos modelos
python3 tools/benchmark.py --models gemini-2-flash,gemini-2-5-flash,opus-4-7

# Auditar semanticamente os artigos gerados
python3 tools/auditor.py --resume
```

Relatório de benchmark disponível (não indexável):
**https://caiorcastro.github.io/orbit-audit-accesstage-abr26/**

---

## Sowads Echo — do artigo à voz do líder

Especificação operacional completa: [docs/SOWADS_ECHO.md](docs/SOWADS_ECHO.md). A migração
isolada por cliente para Pages está documentada em
[docs/CLOUDFLARE_PAGES_MIGRATION.md](docs/CLOUDFLARE_PAGES_MIGRATION.md).

Feature de plataforma que faz um líder **"ecoar" o conteúdo publicado da empresa na própria voz**.
Pega um artigo do blog e o transforma num **post autoral de LinkedIn** por **emulação de persona**
(não é resumo — é o líder reagindo ao tema com opinião e voz de dono). Saída: um **DOCX com
1 post por página** (1 post por artigo, 1 prompt por artigo).

```bash
python3 tools/echo.py \
  --csv output/articles/<batch>.csv \
  --url_dir output/accesstage-site/<lote> \
  --url_base https://sowads-orbit.web.app/accesstage/<subpagina> \
  --out output/celso/sowads_echo_<lote>.docx \
  --json_out output/celso/sowads_echo_<lote>.json \
  [--limit N] [--model <id>] [--emoji_mode none|subtle]
```

Como funciona:
- **Persona documentada e configurável** (hoje: Celso Sato, CEO Accesstage) em
  `client/personas/celso_sato.md` e no prompt do `echo.py`.
- **20 ângulos de abertura rotacionados** (tese, erro caro, sinal fraco, decisão de conselho,
  contraste, opinião firme…) para reduzir repetição entre lotes.
- **Voz humana, sem cara de IA**: 1ª pessoa, insight de liderança, técnico traduzido em benefício
  humano, fecho com pergunta e link direto ao artigo. **Cinco hashtags validadas por tema** são
  adicionadas pelo sistema, não deixadas à escolha livre do modelo. Emojis são zero por padrão e
  só podem ser liberados no modo `subtle` (no máximo um, contextual).
- **Modelo padrão:** `anthropic/claude-opus-4.7` (`--model` para trocar). `--limit N` gera uma amostra.
- **Fluxo:** sempre aprovar o **sample** com o cliente antes de gerar o lote inteiro.
- **Preview integrado:** `tools/generate_echo_preview.py` apresenta cada artigo ao lado da sua
  simulação de LinkedIn, em dois pares por linha no desktop. Usa a foto local oficial de Celso
  Sato para que a aprovação tenha contexto visual e continua isolado em uma subpágina do hub.
  Marco atual: `/accesstage/lote3-echo/`.

---

## Invariantes — nunca quebrar

1. **OpenRouter sempre** — nunca API direta
2. **Zero hyperlinks, `<img>`, `<figure>` ou JSON-LD** no conteúdo
3. **Sem H1 no conteúdo** — HubSpot usa o título do post como H1
4. **FAQ HTML puro** com `<section class="faq-section">`
5. **Categorias do CSV de temas** — nunca inferir
6. **Draft-first no HubSpot** — preflight público → CSV oficial → mapear → revisar → importar como drafts
7. **Nunca sobrescrever conteúdo existente** no importador HubSpot

---

Produzido por **Sowads** · [sowads.com.br](https://sowads.com.br)
