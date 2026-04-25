# Sowads Orbit — Accesstage · Documento Mestre
> Referência operacional completa. Atualizar ao final de cada sessão de trabalho.

---

## 1. O que é este projeto

Motor de conteúdo SEO/AIO da Sowads para o cliente **Accesstage**.
Gera artigos HTML otimizados para WordPress, copies sociais por rede e events CSV para o backend Sowads.

**Cliente:** Accesstage — plataforma financeira B2B
**Produto do cliente:** Veragi — gestão financeira, antecipação de recebíveis, cash pooling, integrações bancárias
**Repositório:** caiorcastro/Sowads-Orbit-Accesstage

---

## 2. Provedor de IA

**Sempre OpenRouter. Nunca API direta.**

```
Endpoint : https://openrouter.ai/api/v1/chat/completions
Modelo   : deepseek/deepseek-v4-pro
Fallback : --fallback_model configurável
Chave    : OPENROUTER_API_KEY no .env
```

---

## 3. Estrutura de arquivos

```
engine/
  content_engine.py   motor principal
  publisher.py        publicação WP via XML-RPC
  social_agent.py     copies por rede + events CSV
  media_indexer.py    indexa biblioteca WP
  qa_validator.py     score QA + self-healing
  topic_creator.py    brainstorm de temas

tools/
  monitor.py          monitor de progresso em tempo real
  optimizer.py        otimização AIO em lote
  bing_indexnow.py    push IndexNow Bing
  check_models.py     lista modelos OpenRouter

config/
  schema_orbit_ai_v1.json   regras técnicas SEO/AIO/HTML

client/
  diretrizes.md        compliance, produtos, tom, checklist Accesstage
  credentials.env      WP + redes sociais (gitignored)

briefings/             pesquisas de mercado por vertical
output/                tudo que sai (gitignored)
  articles/            CSVs de artigos
  social/              TXTs de copies
  events/              CSVs de eventos backend
  reports/             relatórios + media_index.json
```

---

## 4. Variáveis de ambiente

**`.env`** (raiz — gitignored):
```env
OPENROUTER_API_KEY=sk-or-v1-...
BING_INDEXNOW_KEY=
```

**`client/credentials.env`** (gitignored):
```env
WORDPRESS_URL=
WORDPRESS_USER=
WORDPRESS_PASSWORD=
SOWADS_ORG_ID=
IG_ACCOUNT_ID=
FB_PAGE_ID=
LI_ACCOUNT_ID=
TT_ACCOUNT_ID=
```

---

## 5. Pipeline completo

```
Temas CSV → content_engine → output/articles/
                │
                ├── social_agent → output/social/ + output/events/
                │
                └── publisher → WordPress (draft → revisão → publish)
                                    │
                                    └── bing_indexnow → Bing
```

### Passo 1 — Gerar artigos
```bash
./run_lotes.sh
# ou lote específico:
python3 engine/content_engine.py \
  --model "deepseek/deepseek-v4-pro" \
  --csv_input "output/articles/lote_<vertical>_temas.csv"
```

### Passo 2 — Gerar copies + events CSV
```bash
python3 engine/social_agent.py --count 40
python3 engine/social_agent.py --wp_post_id 12345  # artigo específico
```

### Passo 3 — Validar 1 antes de publicar
```bash
python3 engine/publisher.py --test_one
```
Verificar no WP: imagem destacada, conteúdo, categoria, sem código no final.

### Passo 4 — Publicar lote
```bash
python3 engine/publisher.py --all
```

### Passo 5 — Bing (opcional)
```bash
python3 tools/bing_indexnow.py
```

---

## 6. Sistema de Briefings

Pasta `briefings/` — arquivos `.md` com dados de mercado injetados automaticamente no prompt.

**Formato obrigatório da primeira linha:**
```
# Palavras-chave para detecção: palavra1, palavra2, palavra3
```

Zero código para nova vertical — só criar o arquivo.

---

## 7. Sistema de Imagens

Reutiliza imagens **já existentes** na biblioteca WP. Nunca gera nem sobe imagem nova.

- Match: Jaccard (palavras do tema vs. nome do arquivo), peso 80%
- Completude do grupo (blog + li + ig + fb), peso 20%
- Penalidade por repetição: `use_count 0→1.0 | 1→0.5 | 2→0.25 | 3+→0.10`
- Índice persistido em: `output/reports/media_index.json`

Regenerar índice:
```bash
python3 engine/media_indexer.py
```

---

## 8. Formato dos CSVs

### Input (temas)
```csv
topic_pt,vertical,category
"Conciliação Bancária via CNAB","fintech","SEO & AIO"
```

### Output (artigos gerados)
`{input_stem}_batch{n}_artigos_{a}_a_{b}.csv`

Colunas principais: `unique_import_id`, `post_title`, `post_content`, `meta_title`, `meta_description`, `suggested_category`, `qa_score`, `heal_retries`, `img_blog`, `img_linkedin`, `img_instagram`, `img_facebook`, `img_tiktok`, `wp_post_id`, `post_status`

---

## 9. QA Score

| Condição | Penalidade |
|---|---|
| FAQ ausente | -20 |
| Hyperlinks no conteúdo | -15 |
| Word count < 700 | -15 |
| H1 no conteúdo | -10 |
| Word count > 1.800 | -12 |
| Word count > 2.000 | -25 → self-heal |

**Mínimo para publicação: 80/100.** Self-healing automático até 2 tentativas.

---

## 10. Mapeamento de categorias

```python
CATEGORY_CSV_TO_WP = {
    "SEO & AIO":               "SEO e AI-SEO",
    "Conteúdo":                "Conteúdo em Escala",
    "Estratégia e Performance": "Estratégia e Performance",
    "Mídia Paga":              "Mídia Paga",
    "Data e Analytics":        "Dados e Analytics",
}
```
Categorias sempre do CSV de temas — nunca inferidas por keyword.

---

## 11. Invariantes

| # | Regra |
|---|---|
| 1 | OpenRouter sempre — nunca API direta |
| 2 | Zero hyperlinks, `<img>`, `<figure>` ou JSON-LD no conteúdo |
| 3 | Sem H1 no conteúdo — WP usa o título como H1 |
| 4 | FAQ HTML puro com `<section class="faq-section">` |
| 5 | Sem `**asteriscos**` — removidos via código |
| 6 | Categorias do CSV — nunca inferir |
| 7 | Imagens da biblioteca WP — nunca gerar ou subir |
| 8 | Publicação manual — `--test_one` → revisar → `--all` |
| 9 | CSVs nomeados com stem do input — nunca sobrescrever |
| 10 | Sem referências numéricas obrigatórias — compliance Accesstage |

---

## 12. Comandos úteis

```bash
# Ver modelos disponíveis no OpenRouter
python3 tools/check_models.py

# Regenerar índice de imagens da biblioteca WP
python3 engine/media_indexer.py

# Monitorar progresso em tempo real
python3 tools/monitor.py

# Listar rascunhos no WP
python3 engine/publisher.py --list

# Validar artigos já gerados
python3 engine/qa_validator.py --path "output/articles/*.csv"
```

---

## 13. Documentos do cliente

| Arquivo | Conteúdo |
|---|---|
| `client/diretrizes.md` | Guia operacional: compliance, termos proibidos, produtos Veragi, clusters SEO, checklist |
| `client/credentials.env` | Credenciais WP + redes sociais (gitignored) |

Mais documentos do cliente chegam em `client/` conforme o projeto evolui.
