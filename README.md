# Sowads Orbit — Accesstage

Motor de conteúdo SEO/AIO para escalar a autoridade digital da **Accesstage** no segmento financeiro B2B, posicionando a **Plataforma Veragi** como referência técnica em gestão financeira, integrações bancárias e crédito corporativo.

Desenvolvido pela [Sowads](https://sowads.com.br) — agência especializada em SEO, AIO e estratégia de mídia.

---

## O que este projeto faz

Dado um tema, o Sowads Orbit:

1. **Gera artigos HTML** prontos para WordPress, com SEO/AIO incorporado — sem links, sem imagens no conteúdo, sem JSON-LD visível
2. **Valida a qualidade** (score 0–100) e se necessário **corrige automaticamente** (self-healing)
3. **Atribui imagens** da biblioteca existente do WordPress via matching temático (Jaccard)
4. **Gera copies sociais** para LinkedIn, Instagram e Facebook derivados de cada artigo
5. **Exporta o events CSV** no formato do backend Sowads para agendamento de posts
6. **Publica no WordPress** via XML-RPC com imagem destacada e categoria corretas

Tudo isso a partir de um CSV de temas e um briefing de cliente — sem intervenção manual no meio.

---

## Estrutura do projeto

```
Sowads-Orbit-Accesstage/
│
├── client/                             ← Documentos do cliente (versionados)
│   ├── diretrizes.md                   ← Guia operacional: compliance, tom, SEO, produtos
│   ├── credentials.env                 ← NÃO commitado: credenciais do CMS e redes sociais
│   └── [outros docs do cliente].md     ← Briefings adicionais conforme chegarem
│
├── briefings/                          ← Pesquisas de mercado por vertical/assunto
│   └── <vertical>.md                   ← Dados reais injetados automaticamente no prompt
│
├── output_csv_batches_v2/              ← Artigos gerados (1 CSV por lote, gitignored)
├── output_social_copies/               ← TXTs de copies por rede
├── output_sowads_events/               ← CSVs de eventos para o backend Sowads
├── relatorios/                         ← Relatórios de produção + media_index.json
│
├── orbit_content_engine.py             ← Motor principal: prompt → OpenRouter → QA → CSV
├── orbit_qa_validator.py               ← Score 0-100 + self-healing automático
├── orbit_media_indexer.py              ← Indexa biblioteca WP, match temático por Jaccard
├── orbit_publisher.py                  ← Publica no WP via XML-RPC com imagem destacada
├── orbit_social_agent.py               ← Gera copies por rede + events CSV do backend
├── orbit_monitor.py                    ← Monitor em tempo real: ETA, scores, imagens
├── orbit_topic_creator.py              ← Brainstorm de temas via IA
├── orbit_optimizer.py                  ← Otimização AIO em lote
├── bing_index_now.py                   ← Push de URLs para indexação no Bing
├── run_lotes.sh                        ← Pipeline de geração (nunca publica automaticamente)
│
├── regras_geracao/
│   └── schema_orbit_ai_v1.json         ← Regras técnicas de SEO/AIO/estrutura HTML
│
├── .env                                ← Chave OpenRouter (gitignored)
└── .gitignore
```

---

## Pipeline completo

```
[1] Temas CSV  →  [2] Geração  →  [3] QA + Self-heal  →  [4] Social  →  [5] Publicação  →  [6] Bing
```

### Passo 1 — Preparar temas

Crie o CSV em `output_csv_batches_v2/lote_<vertical>_temas.csv`:

```csv
topic_pt,vertical,category
"Gestão de Recebíveis com Open Finance","fintech","SEO & AIO"
"Conciliação Bancária Automatizada via CNAB","fintech","SEO & AIO"
```

| Coluna | Descrição |
|---|---|
| `topic_pt` | Tema do artigo em português |
| `vertical` | Usado para matching de briefing e imagens |
| `category` | Categoria WordPress — deve constar no mapeamento de categorias |

### Passo 2 — Gerar artigos

```bash
# Gerar todos os lotes configurados no run_lotes.sh
./run_lotes.sh

# Ou um lote específico
python3 orbit_content_engine.py \
  --model "deepseek/deepseek-v4-pro" \
  --csv_input "output_csv_batches_v2/lote_fintech_temas.csv"
```

Salva em `output_csv_batches_v2/{stem}_batch{n}_artigos_{a}_a_{b}.csv`. **Nunca publica automaticamente.**

### Passo 3 — Gerar copies sociais + events CSV

```bash
# Gerar para os 40 artigos mais recentes
python3 orbit_social_agent.py --count 40

# Ou um artigo específico pelo ID do post no WordPress
python3 orbit_social_agent.py --wp_post_id 12345
```

Gera:
- `output_social_copies/{rede}/{id}__wp{id}__{rede}.txt`
- `output_sowads_events/orbitai_events_{org}_{ts}.csv`

### Passo 4 — Validar e publicar no WordPress

```bash
# SEMPRE testar 1 artigo primeiro
python3 orbit_publisher.py \
  --wp_url https://site.com.br \
  --wp_user usuario \
  --wp_pass "..." \
  --input_dir output_csv_batches_v2 \
  --test_one

# Verificar manualmente no WP: imagem destacada, conteúdo, categoria
# Só então publicar o lote completo:
python3 orbit_publisher.py ... --all
```

### Passo 5 — Indexar no Bing (opcional)

```bash
python3 bing_index_now.py
```

### Monitorar em tempo real

```bash
python3 orbit_monitor.py --log relatorios/run_pipeline.log
```

---

## Configuração inicial

### 1. Instalar dependências

```bash
pip install requests pandas colorama
```

### 2. Configurar credenciais

Crie `client/credentials.env` (nunca commitado):

```env
WORDPRESS_URL=https://blog.accesstage.com.br
WORDPRESS_USER=usuario
WORDPRESS_PASSWORD=app-password-do-wp

SOWADS_ORG_ID=seu-org-id
IG_ACCOUNT_ID=id-instagram
FB_PAGE_ID=id-facebook
LI_ACCOUNT_ID=id-linkedin
TT_ACCOUNT_ID=id-tiktok
```

Crie `.env` na raiz (nunca commitado):

```env
OPENROUTER_API_KEY=sk-or-v1-...
BING_INDEXNOW_KEY=opcional
```

### 3. Indexar biblioteca de imagens do WordPress

```bash
python3 orbit_media_indexer.py \
  --wp_url https://blog.accesstage.com.br \
  --wp_user usuario \
  --wp_pass "..."
```

Gera `relatorios/media_index.json` — persiste entre runs, rastreia quais imagens já foram usadas.

---

## Sistema de Briefings de Verticais

A pasta `briefings/` contém arquivos `.md` com dados de pesquisa — regulação, tendências de mercado, players, números reais — que vão além do corte de conhecimento da IA.

O engine detecta automaticamente por palavras-chave do tema e injeta os primeiros 800 chars no prompt. **Zero código** para nova vertical — só criar o arquivo:

```markdown
# Palavras-chave para detecção: cnab, edi, integração bancária, van bancária

## Contexto de mercado
[dados reais, regulação, tendências 2025-2026...]
```

---

## QA e Self-Healing

Cada artigo recebe score 0–100 automaticamente antes de ser salvo:

| Condição | Penalidade |
|---|---|
| FAQ ausente | -20 |
| Hyperlinks no conteúdo | -15 |
| Word count < 700 palavras | -15 |
| H1 presente no conteúdo | -10 |
| Word count > 1.800 palavras | -12 |
| Word count > 2.000 palavras | -25 → dispara self-heal |

**Score mínimo para publicação: 80/100.**
Se abaixo de 80, o artigo volta para o modelo com a lista de problemas. Até 2 tentativas automáticas.

---

## Regras estruturais (invariantes)

1. **Modelo sempre via OpenRouter** — `deepseek/deepseek-v4-pro` por padrão
2. **Zero hyperlinks, `<img>`, `<figure>` ou JSON-LD** no conteúdo dos artigos
3. **Sem H1 no conteúdo** — WordPress renderiza o título do post como H1
4. **FAQ em HTML puro** com `<section class="faq-section">` — sem `<script>`
5. **Asteriscos `**texto**` removidos** via código — sem markdown bold em HTML
6. **Categorias sempre do CSV de temas** — nunca inferidas por keyword
7. **Imagens sempre da biblioteca WP** — nunca gerar ou subir nova
8. **Publicação sempre manual** — `--test_one` → revisar → `--all`

---

## Adicionando nova vertical

1. Pesquise o mercado → crie `briefings/<vertical>.md` com a linha de keywords
2. Crie `output_csv_batches_v2/lote_<vertical>_temas.csv` com `topic_pt, vertical, category`
3. Adicione o lote no `run_lotes.sh` seguindo o padrão existente
4. **Zero mudança de código**

---

## Documentos do cliente

| Arquivo | Conteúdo |
|---|---|
| `client/diretrizes.md` | Guia operacional: compliance, termos proibidos, produtos Veragi, SEO, checklist |
| `client/credentials.env` | Credenciais CMS e redes sociais — **gitignored, nunca sobe** |

---

## Modelo de IA

| Parâmetro | Valor |
|---|---|
| Provedor | OpenRouter |
| Modelo padrão | `deepseek/deepseek-v4-pro` |
| Fallback | configurável via `--fallback_model` |
| Endpoint | `https://openrouter.ai/api/v1/chat/completions` |

---

Produzido por **Sowads** · [sowads.com.br](https://sowads.com.br)
