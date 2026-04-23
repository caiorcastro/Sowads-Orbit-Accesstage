# Sowads Orbit AI — CLAUDE.md
# Leia este arquivo INTEIRO antes de qualquer ação no projeto.

## O que é este projeto

Motor de conteúdo SEO/AIO para a Sowads Agência. Gera artigos HTML otimizados para WordPress em escala, copies sociais por rede e exporta eventos para o backend Sowads. Produto interno chamado **Orbit AI v3**.

## Provedor de IA — REGRA FIXA

**Sempre OpenRouter.** Nunca usar Gemini direto, nem qualquer outra API.

```
Endpoint : https://openrouter.ai/api/v1/chat/completions
Modelo   : google/gemini-2.5-flash
Fallback : --fallback_model moonshotai/kimi-k2.6
Chave    : OPENROUTER_API_KEY no .env
Headers  : HTTP-Referer: https://sowads.com.br
           X-Title: Sowads Orbit AI Content Engine
```

## Scripts — o que cada um faz

| Script | Input | Output | Observações |
|--------|-------|--------|-------------|
| `run_lotes.sh` | — | CSVs em `output_csv_batches_v2/` | NÃO publica — só gera |
| `orbit_content_engine.py` | CSV de temas | CSV de artigos com métricas | Motor principal |
| `orbit_qa_validator.py` | HTML | score 0-100 + issues | Usado internamente pelo engine |
| `orbit_media_indexer.py` | — | `relatorios/media_index.json` | Indexa biblioteca WP |
| `orbit_monitor.py` | log file | terminal em tempo real | ETA, scores, imagens |
| `orbit_publisher.py` | CSV de artigos | posts no WP | Sempre `--test_one` antes de `--all` |
| `orbit_social_agent.py` | CSVs de artigos | TXTs por rede + events CSV | Usa OpenRouter; aceita draft e published |
| `orbit_topic_creator.py` | tema livre | CSV de temas | Brainstorm de pautas |
| `orbit_optimizer.py/_v2/_parallel` | CSV | CSV otimizado | AIO em lote |
| `bing_index_now.py` | URLs | push IndexNow | Indexação forçada Bing |
| `check_models*.py` / `get_models_list.py` | — | lista | Utilitários — listar modelos |

## Diretórios de saída

```
output_csv_batches_v2/     ← artigos gerados (1 CSV por lote)
output_social_copies/      ← TXTs de copies por rede (linkedin/, instagram/, facebook/)
output_sowads_events/      ← CSVs de eventos para o backend Sowads (1 por run do social agent)
relatorios/                ← relatórios Markdown + media_index.json
briefings/                 ← pesquisas por vertical (injetadas no prompt automaticamente)
regras_geracao/            ← schema_orbit_ai_v1.json (regras de brand e compliance)
```

## .env — variáveis necessárias

```env
OPENROUTER_API_KEY=sk-or-v1-...
WORDPRESS_URL=https://sowads.com.br
WORDPRESS_USER=caio
WORDPRESS_PASSWORD=...          # app password do WP, não a senha real
BING_INDEXNOW_KEY=

# Backend Sowads / Social
SOWADS_ORG_ID=0-DUMMY-0
IG_ACCOUNT_ID=DUMMY-IG-00000000000
FB_PAGE_ID=DUMMY-FB-00000000000
LI_ACCOUNT_ID=DUMMY-LI-00000000000
TT_ACCOUNT_ID=DUMMY-TT-00000000000
```

## Pipeline completo — passo a passo

```bash
# 1. GERAR artigos (nunca publica automaticamente)
./run_lotes.sh

# 2. GERAR copies sociais + events CSV para o backend
python3 orbit_social_agent.py --count 40
# → salva TXTs em output_social_copies/{rede}/
# → salva orbitai_events_{org}_{ts}.csv em output_sowads_events/

# 3. VALIDAR 1 artigo antes de publicar
python3 orbit_publisher.py \
  --wp_url https://sowads.com.br --wp_user caio --wp_pass "..." \
  --input_dir output_csv_batches_v2 --test_one
# Verificar no WP: imagem destacada presente? Conteúdo OK? Sem código no final?

# 4. PUBLICAR lote completo (só após validar --test_one)
python3 orbit_publisher.py ... --all

# 5. INDEXAR no Bing (opcional, após publicação)
python3 bing_index_now.py
```

## Sistema de Briefings

Pasta `briefings/` — arquivos `.md` com dados reais além do corte da IA.

**Formato obrigatório da primeira linha:**
```
# Palavras-chave para detecção: palavra1, palavra2, palavra3
```

O engine detecta por keyword do tema e injeta os primeiros 800 chars no prompt. **Zero código** para nova vertical — só criar o arquivo `.md`.

**Briefings existentes:** `turismo.md`, `auto.md`

## Sistema de Imagens

Reutiliza imagens **já existentes** na biblioteca WP — nunca gera, nunca sobe nova.

- Match: Jaccard (palavras do tema vs. nome do arquivo), peso 80%
- Completude do grupo (blog + linkedin + ig + fb?), peso 20%
- Penalidade por repetição: `use_count 0→1.0 | 1→0.5 | 2→0.25 | 3+→0.10`
- Índice em: `relatorios/media_index.json`

## Events CSV — formato do backend Sowads

O `orbit_social_agent.py` gera automaticamente após cada run:

```
output_sowads_events/orbitai_events_{SOWADS_ORG_ID}_{unix_ts}.csv
```

Colunas: `org_id, source_event_id, event_source, event_type, event_version, event_request_timestamp, payload, status`

- 1 artigo = 4 linhas (ig, fb, li, tt)
- `status: pending` sempre
- `payload`: JSON com rede, account_id, primary_text (hook+copy+cta+hashtags), link WP, media URL `[BIBLIOTECA]filename.jpg`

## Mapeamento de categorias CSV → WordPress

```python
CATEGORY_CSV_TO_WP = {
    "SEO & AIO":               "SEO e AI-SEO",
    "Conteúdo":                "Conteúdo em Escala",
    "Estratégia e Performance": "Estratégia e Performance",
    "Mídia Paga":              "Mídia Paga",
    "Data e Analytics":        "Dados e Analytics",
}
```

A categoria vem do CSV de temas (`category` column) e é preservada até o WP. Nunca usar detecção por keyword.

## QA Scoring — thresholds atuais

| Condição | Penalidade |
|----------|-----------|
| Word count < 700 | -15 |
| Word count > 1.500 | -5 |
| Word count > 1.800 | -12 |
| Word count > 2.000 | -25 (falha → self-heal) |
| FAQ ausente | -20 |
| H1 no conteúdo | -10 (WP renderiza o título como H1) |
| JSON-LD / `<script>` | stripped via código, não penaliza |

## Invariantes que NUNCA devem ser quebrados

1. **OpenRouter sempre** — nunca Gemini direto ou outra API sem aprovação
2. **Compliance Orbit AI ↔ Meta Ads** — produtos independentes, zero causalidade
3. **Zero hyperlinks, `<img>`, `<figure>` ou JSON-LD** no conteúdo dos artigos
4. **FAQ HTML puro** com `<section class="faq-section">` + `<h2>` + `<h3>` + `<p>`
5. **Sem H1 no conteúdo** — WordPress renderiza o título do post como H1
6. **Score QA ≥ 80/100** com self-healing até 2x
7. **Publicação SEMPRE manual** — `--test_one` → verificar WP → `--all`
8. **Imagens sempre da biblioteca WP** — nunca gerar ou subir nova
9. **Asteriscos `**texto**` removidos** via código em `parse_response()` — modelo não deve gerar markdown bold em HTML
10. **CSVs nomeados com stem do arquivo de input** — nunca sobrescrever entre lotes

## Adicionando nova vertical

1. Pesquise o mercado e crie `briefings/<vertical>.md` com linha de keywords
2. Crie CSV em `output_csv_batches_v2/lote_<vertical>_temas.csv` com colunas: `topic_pt, vertical, category`
3. Adicione lote no `run_lotes.sh` seguindo o padrão existente
4. Zero mudança de código

**Verticais implementadas:** turismo, automotivo
**Sugeridas (prospects Sowads):** saúde/clínicas, imóveis, educação, financeiro, varejo/e-commerce, jurídico, franquias, agro

## Regras de comportamento para o assistente de IA

- **Sempre ler os arquivos reais antes de agir** — nunca inventar estado
- **Verificar com `git status`** antes de qualquer edição de pipeline
- **Nunca sobrescrever CSVs existentes** sem confirmar com o usuário
- **Antes de publicar lotes**: confirmar que `--test_one` foi rodado e validado
- **Invariantes estruturais** (sem JSON-LD, sem H1, sem asteriscos) devem ser garantidos via código, não só via prompt
- **Não automatizar publicação** mesmo que o usuário peça "publique tudo" — sempre `--test_one` primeiro com confirmação explícita
- **Fixes de conteúdo em posts já publicados**: usar XML-RPC `wp.editPost` com regex, nunca regenerar
- **Categorias**: sempre vêm do CSV de temas — nunca inferir por keyword
