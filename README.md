<div align="center">

```
 ██████╗ ██████╗ ██████╗ ██╗████████╗     █████╗ ██╗
██╔═══██╗██╔══██╗██╔══██╗██║╚══██╔══╝    ██╔══██╗██║
██║   ██║██████╔╝██████╔╝██║   ██║       ███████║██║
██║   ██║██╔══██╗██╔══██╗██║   ██║       ██╔══██║██║
╚██████╔╝██║  ██║██████╔╝██║   ██║       ██║  ██║██║
 ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═╝   ╚═╝       ╚═╝  ╚═╝╚═╝
        Sowads Content Engine v3 — SEO/AIO em escala
```

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![OpenRouter](https://img.shields.io/badge/AI-OpenRouter%20%7C%20Gemini%202.5%20Flash-orange) ![WordPress](https://img.shields.io/badge/CMS-WordPress%20XML--RPC-21759B) ![License](https://img.shields.io/badge/License-Interno%20Sowads-lightgrey)

</div>

Motor de geração, validação e publicação de conteúdo SEO/AIO para WordPress em escala. Gera artigos HTML otimizados, copies sociais por rede (LinkedIn, Instagram, Facebook, TikTok) e exporta eventos para o backend Sowads — tudo via OpenRouter com `google/gemini-2.5-flash`.

---

## Pipeline completo

```
Temas CSV
    │
    ▼
orbit_content_engine.py ──► output_csv_batches_v2/
    │  (artigos HTML + QA score + URLs de imagens)
    │
    ├──► orbit_social_agent.py ──► output_social_copies/{rede}/
    │         │                    output_sowads_events/*.csv  ◄── backend Sowads
    │         │
    ▼         ▼
orbit_publisher.py ──► WordPress (draft → revisão → publish)
    │
    ▼
bing_index_now.py ──► Bing IndexNow
```

---

## Estrutura de arquivos

```
Sowads-v2-local/
├── CLAUDE.md                              # Instruções para IA — leia antes de agir
├── run_lotes.sh                           # Pipeline: gera todos os lotes (não publica)
│
├── orbit_content_engine.py               # Motor de artigos (OpenRouter + briefings + QA)
├── orbit_qa_validator.py                 # Score 0-100: FAQ, word count, estrutura HTML
├── orbit_media_indexer.py                # Matching de imagens da biblioteca WP
├── orbit_monitor.py                      # Monitor em tempo real no terminal
├── orbit_publisher.py                    # Publicação WP via XML-RPC + imagem destacada
├── orbit_social_agent.py                 # Copies por rede + events CSV (OpenRouter)
├── orbit_topic_creator.py                # Brainstorm de temas
├── orbit_optimizer.py / _v2 / _parallel  # Otimização AIO em lote
├── bing_index_now.py                     # Indexação forçada Bing IndexNow
├── check_models*.py / get_models_list.py # Utilitários: listar modelos OpenRouter
│
├── briefings/
│   ├── turismo.md                        # Pesquisa: turismo, OTAs, AI Overviews 2026
│   └── auto.md                           # Pesquisa: EVs Brasil, montadoras chinesas
│
├── regras_geracao/
│   └── schema_orbit_ai_v1.json           # Brand, compliance, regras SEO/AIO
│
├── output_csv_batches_v2/                # Artigos gerados (1 CSV por lote)
├── output_social_copies/                 # TXTs de copies por rede
│   ├── linkedin/
│   ├── instagram/
│   └── facebook/
├── output_sowads_events/                 # CSVs de eventos para o backend Sowads
└── relatorios/                           # Relatórios Markdown + media_index.json
```

---

## Configuração

### Dependências

```bash
pip install pandas requests python-dotenv xmlrpc
```

### Variáveis de ambiente (.env)

```env
# IA — sempre OpenRouter, nunca Gemini direto
OPENROUTER_API_KEY=sk-or-v1-...

# WordPress
WORDPRESS_URL=https://sowads.com.br
WORDPRESS_USER=caio
WORDPRESS_PASSWORD=...       # app password do WP, não a senha real

# Bing
BING_INDEXNOW_KEY=

# Backend Sowads / contas sociais (substituir pelos IDs reais antes de produção)
SOWADS_ORG_ID=0-DUMMY-0
IG_ACCOUNT_ID=DUMMY-IG-00000000000
FB_PAGE_ID=DUMMY-FB-00000000000
LI_ACCOUNT_ID=DUMMY-LI-00000000000
TT_ACCOUNT_ID=DUMMY-TT-00000000000
```

---

## Uso — passo a passo

### 1. Gerar artigos

```bash
./run_lotes.sh
```

Processa todos os lotes e salva CSVs em `output_csv_batches_v2/`. **Nunca publica automaticamente.**

Para rodar um lote específico:

```bash
python3 orbit_content_engine.py \
  --model "google/gemini-2.5-flash" \
  --wp_url "https://sowads.com.br" \
  --wp_user "caio" \
  --wp_pass "..." \
  --csv_input "output_csv_batches_v2/lote_auto_temas.csv"
```

### 2. Gerar copies sociais + events CSV

```bash
python3 orbit_social_agent.py --count 40
```

Gera copies para os N artigos mais recentes (aceita `draft` e `published`). Saída automática:
- `output_social_copies/{rede}/{unique_id}__wp{id}__{rede}.txt`
- `output_sowads_events/orbitai_events_{org}_{ts}.csv`

Para artigo específico:

```bash
python3 orbit_social_agent.py --wp_post_id 32277
```

### 3. Validar e publicar

```bash
# OBRIGATÓRIO: validar 1 artigo primeiro
python3 orbit_publisher.py \
  --wp_url https://sowads.com.br \
  --wp_user caio \
  --wp_pass "..." \
  --input_dir output_csv_batches_v2 \
  --test_one

# Verificar no painel WP: imagem destacada? conteúdo limpo? sem código?

# Só então publicar o lote completo
python3 orbit_publisher.py \
  --wp_url https://sowads.com.br \
  --wp_user caio \
  --wp_pass "..." \
  --input_dir output_csv_batches_v2 \
  --all
```

O publisher seta a imagem destacada automaticamente. Terminal mostra `🖼️` (ok) ou `⚠️ sem imagem` (falhou).

### 4. Indexar no Bing (opcional)

```bash
python3 bing_index_now.py
```

### Monitorar progresso em tempo real

```bash
python3 orbit_monitor.py --log relatorios/run_pipeline.log
```

---

## Formato do CSV de temas (input)

```csv
topic_pt,vertical,category
"AIO para Lançamentos Automotivos","automotivo","SEO & AIO"
"GEO e a Jornada do Test-Drive","automotivo","SEO & AIO"
"Mídia Paga e Autoridade Orgânica","automotivo","Mídia Paga"
```

| Coluna | Obrigatória | Descrição |
|--------|-------------|-----------|
| `topic_pt` | Sim | Tema do artigo em português |
| `vertical` | Não | Usado para matching de briefing e imagens |
| `category` | Sim | Categoria WP — ver mapeamento abaixo |

**Mapeamento de categorias (CSV → WordPress):**

| Valor no CSV | Categoria no WordPress |
|---|---|
| `SEO & AIO` | `SEO e AI-SEO` |
| `Conteúdo` | `Conteúdo em Escala` |
| `Estratégia e Performance` | `Estratégia e Performance` |
| `Mídia Paga` | `Mídia Paga` |
| `Data e Analytics` | `Dados e Analytics` |

---

## Formato do CSV de artigos (output)

Gerado em `output_csv_batches_v2/lote_{vertical}_batch{n}_artigos_{start}_a_{end}.csv`:

| Coluna | Descrição |
|--------|-----------|
| `unique_import_id` | ID único (`Orbit_1`, `Orbit_2`…) |
| `post_title` | Título completo |
| `post_content` | HTML completo (`<article lang="pt-BR">…</article>`) |
| `meta_title` | Meta title SEO (≤ 60 chars) |
| `meta_description` | Meta description (≤ 160 chars) |
| `suggested_category` | Categoria (preservada do CSV de temas) |
| `qa_score` | Score QA 0-100 |
| `heal_retries` | Tentativas de self-healing usadas |
| `img_blog` | URL da imagem blog (WP library) |
| `img_linkedin` | URL da imagem LinkedIn |
| `img_instagram` | URL da imagem Instagram |
| `img_facebook` | URL da imagem Facebook |
| `img_tiktok` | URL da imagem TikTok |
| `wp_post_id` | ID do post após publicação |
| `published_at` | Timestamp da publicação |

---

## Events CSV — formato do backend Sowads

Gerado automaticamente em `output_sowads_events/orbitai_events_{org}_{ts}.csv`:

| Coluna | Valor |
|--------|-------|
| `org_id` | ID da org Sowads (ex: `0-DUMMY-0`) |
| `source_event_id` | `orbitAI_{unique_id}_{rede}_{uuid8}` |
| `event_source` | `orbit_ai` |
| `event_type` | `create_organic_post` |
| `event_version` | `v1` |
| `event_request_timestamp` | Unix timestamp |
| `payload` | JSON com rede, account_id, primary_text, link, media |
| `status` | `pending` |

**1 artigo = 4 linhas** (ig, fb, li, tt). O `primary_text` = hook + copy + cta + hashtags concatenados.

---

## Sistema de Briefings

Pasta `briefings/` contém arquivos `.md` com dados de pesquisa além do corte da IA.

**Criar novo briefing:**

```markdown
# Palavras-chave para detecção: palavra1, palavra2, palavra3

## Contexto de mercado
[dados reais, números, tendências 2026...]
```

O engine detecta automaticamente por keyword do tema e injeta até 800 chars no prompt. **Zero código necessário.**

**Briefings existentes:** `turismo.md`, `auto.md`

---

## Sistema de Imagens

Reutiliza imagens **já existentes** na biblioteca WP (~850 itens). Nunca gera, nunca sobe nova.

**Scoring:**

| Critério | Peso |
|----------|------|
| Jaccard (palavras do tema vs. nome do arquivo) | 80% |
| Completude do grupo (blog + linkedin + ig + fb?) | 20% |
| Penalidade por repetição (`use_count`) | desconto progressivo |

**Penalidade por repetição:** `0→1.0 | 1→0.5 | 2→0.25 | 3+→0.10`

**Padrão de nomes WP:** `{Prefix}_{N}_{type}_{topic-slug}_{hash}.jpg`
Tipos: `wp`=blog, `li`=linkedin, `ig`=instagram, `fb`=facebook, `tt`=tiktok

---

## QA — score e thresholds

| Verificação | Penalidade |
|-------------|-----------|
| FAQ ausente (`faq-section`) | -20 |
| H2/H3 hierárquicos ausentes | -10 |
| Tabelas ou listas ausentes | -5 |
| Referências numéricas ausentes | -5 |
| Word count < 700 | -15 |
| Word count > 1.500 | -5 |
| Word count > 1.800 | -12 |
| Word count > 2.000 | -25 → self-heal automático |
| H1 no conteúdo | -10 |

Self-healing: até 2 tentativas com prompt de correção focado nos issues detectados.

---

## Invariantes — nunca quebrar

| # | Regra |
|---|-------|
| 1 | **OpenRouter sempre** — nunca Gemini direto ou outra API |
| 2 | **Compliance Orbit AI ↔ Meta Ads** — produtos independentes, zero causalidade |
| 3 | **Zero hyperlinks, `<img>`, `<figure>` ou JSON-LD** no conteúdo |
| 4 | **FAQ HTML puro** — `<section class="faq-section">` sem `<script>` |
| 5 | **Sem H1 no conteúdo** — WordPress renderiza o título do post como H1 |
| 6 | **Score QA ≥ 80/100** |
| 7 | **Publicação manual** — sempre `--test_one` antes de `--all` |
| 8 | **Imagens da biblioteca WP** — nunca gerar ou subir nova |
| 9 | **Sem `**asteriscos**`** — stripped via código em `parse_response()` |
| 10 | **Categorias do CSV de temas** — nunca inferir por keyword |

---

## Adicionando nova vertical

1. **Pesquise** o mercado e crie `briefings/<vertical>.md` com a linha de keywords
2. **Crie** `output_csv_batches_v2/lote_<vertical>_temas.csv` com colunas `topic_pt, vertical, category`
3. **Adicione** o lote no `run_lotes.sh` seguindo o padrão existente
4. **Gere**, **valide com `--test_one`**, **publique com `--all`**
5. **Gere copies** com `orbit_social_agent.py --count N`

**Sugeridas (prospects Sowads):** saúde/clínicas, imóveis/construtoras, educação/cursos, financeiro/fintechs, varejo/e-commerce, advocacia/jurídico, franquias, agro

---

## Troubleshooting

| Problema | Causa | Solução |
|----------|-------|---------|
| JSON-LD aparece no artigo | Model ignora instrução | Verificar `parse_response()` — strip via `re.sub` deve estar presente |
| `**asteriscos**` no conteúdo | Model gera markdown | Verificar `parse_response()` — strip de `\*\*` deve estar presente |
| Imagem não aparece no WP | `get_media_id_by_url` falhou | Verificar nome do arquivo na biblioteca WP |
| CSV sobrescrito entre lotes | Nome sem stem do input | Verificar nomeação: deve ser `{input_stem}_batch{n}_artigos_{a}_a_{b}.csv` |
| Categoria errada no WP | Inferência por keyword | Verificar `CATEGORY_CSV_TO_WP` no publisher e coluna `suggested_category` no CSV |
| Events CSV vazio | `_payload` não salvo | Verificar `article["_payload"] = payload` no loop do social agent |
| Social agent falha com JSON | Model retornou texto extra | Retry automático — rodar `--wp_post_id` para artigo específico |

---

## Comandos úteis

```bash
# Listar modelos disponíveis no OpenRouter
python3 get_models_list.py

# Regenerar index de imagens da biblioteca WP
python3 orbit_media_indexer.py

# Corrigir posts já publicados sem regenerar (ex: remover asteriscos)
python3 - <<'EOF'
import xmlrpc.client, re
server = xmlrpc.client.ServerProxy("https://sowads.com.br/xmlrpc.php")
POST_ID = 32307  # substituir
post = server.wp.getPost(1, "caio", "SENHA", POST_ID, ["post_content"])
content = re.sub(r'\*\*(.+?)\*\*', r'\1', post["post_content"], flags=re.DOTALL)
server.wp.editPost(1, "caio", "SENHA", POST_ID, {"post_content": content})
print("OK")
EOF

# Mover posts para rascunho (sem deletar)
python3 - <<'EOF'
import xmlrpc.client
server = xmlrpc.client.ServerProxy("https://sowads.com.br/xmlrpc.php")
for pid in [32195, 32197]:  # lista de IDs
    server.wp.editPost(1, "caio", "SENHA", pid, {"post_status": "draft"})
    print(f"  draft: {pid}")
EOF
```
