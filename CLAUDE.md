# Sowads Orbit AI — CLAUDE.md

## O que é este projeto

Motor de conteúdo SEO/AIO para a Sowads Agência. Gera artigos HTML otimizados para WordPress em escala, com copies sociais e indexação automática. Produto interno chamado **Orbit AI**.

## Scripts e responsabilidades

| Script | Responsabilidade |
|--------|-----------------|
| `orbit_content_engine.py` | Motor principal: geração de artigos HTML (OpenRouter + briefings) |
| `orbit_topic_creator.py` | Brainstorm de temas via Gemini |
| `orbit_qa_validator.py` | Score de qualidade 0-100 |
| `orbit_publisher.py` | Publicação no WordPress via XML-RPC |
| `orbit_media_indexer.py` | Indexação e matching de imagens da biblioteca WP |
| `orbit_monitor.py` | Monitor de progresso em tempo real (terminal) |
| `orbit_social_agent.py` | Copies para LinkedIn, Instagram, Facebook |
| `orbit_optimizer.py` / `_v2.py` / `_parallel.py` | Otimização AIO em lote |
| `bing_index_now.py` | Indexação forçada no Bing |
| `run_lotes.sh` | Pipeline: gera lotes → salva CSVs (NÃO publica automaticamente) |

## Provedor de IA

**OpenRouter** (`https://openrouter.ai/api/v1/chat/completions`) — compatível com API OpenAI.

- Modelo primário: `google/gemini-2.5-flash`
- Modelo fallback: `--fallback_model` (ex: `moonshotai/kimi-k2.6`)
- Chave: `OPENROUTER_API_KEY` no `.env` ou `--openrouter_key` na CLI
- Headers obrigatórios: `HTTP-Referer: https://sowads.com.br`, `X-Title: Sowads Orbit AI Content Engine`

## Sistema de Briefings

Pasta `briefings/` contém arquivos `.md` com dados atualizados além do corte da IA.

**Formato obrigatório:**
```
# Palavras-chave para detecção: palavra1, palavra2, palavra3

[conteúdo de pesquisa aqui]
```

**Como funciona:** O engine detecta palavras do tema no arquivo `.md`, injeta os primeiros 800 palavras no prompt automaticamente. Nenhuma mudança de código necessária para adicionar novos briefings.

**Para novas verticais:** basta criar `briefings/<vertical>.md` com a linha de keywords — zero código.

**Briefings existentes:**
- `briefings/turismo.md` — SGE/AI Overviews no travel, CVC, OTAs, zero-click 2026
- `briefings/auto.md` — EVs no Brasil, montadoras chinesas, SGE automotivo, schema markup

## Sistema de Imagens (orbit_media_indexer.py)

Reutiliza imagens **já existentes** na biblioteca do WordPress — sem geração, sem upload.

**Scoring de matching:**
- Similaridade Jaccard entre palavras do tema e palavras no nome do arquivo de imagem (peso 80%)
- Completude do grupo (tem blog + linkedin + instagram + facebook?) (peso 20%)
- Penalidade por repetição: `use_count=0→1.0`, `1→0.5`, `2→0.25`, `3+→0.10`

**Persistência:** `relatorios/media_index.json` — guarda `use_count` e `assigned_to` entre runs.

**Colunas CSV de saída:** `img_blog`, `img_linkedin`, `img_instagram`, `img_facebook`, `img_tiktok`

**Padrão de nomes dos arquivos WP:** `{Prefix}_{N}_{type}_{topic-slug}_{hash}.jpg`
Tipos: `wp`=blog, `li`=linkedin, `ig`=instagram, `fb`=facebook, `tt`=tiktok

## Pipeline de publicação — OBRIGATÓRIO SEGUIR

**O `run_lotes.sh` NÃO publica mais automaticamente.** Publicação automática foi removida por causar problemas de indexação.

**Fluxo correto sempre:**
```bash
# 1. Gerar artigos
./run_lotes.sh

# 2. Validar 1 artigo antes de publicar o lote
python3 orbit_publisher.py \
  --wp_url "https://sowads.com.br" \
  --wp_user "caio" \
  --wp_pass "..." \
  --input_dir "output_csv_batches_v2" \
  --test_one

# 3. Verificar no WordPress se o artigo tem imagem destacada e conteúdo OK
# 4. Só então publicar o lote completo
python3 orbit_publisher.py ... --all
```

**O publisher seta a imagem destacada automaticamente** via `get_media_id_by_url` + `set_post_thumbnail` XML-RPC. O print mostra `🖼️` se setou ou `⚠️ sem imagem` se falhou.

## Configuração central

`regras_geracao/schema_orbit_ai_v1.json` — brand, compliance, regras SEO/AIO, formato de output.

## Invariantes que NUNCA devem ser quebrados

1. **Compliance de produto:** Orbit AI (SEO/AIO) e Meta Ads são independentes. Nenhum artigo pode sugerir causalidade entre os dois. Para temas de Mídia Paga: tratar canais como paralelos e independentes — anúncios NÃO melhoram ranqueamento orgânico.
2. **Zero hyperlinks** no conteúdo dos artigos. CTA apenas em negrito.
3. **Estrutura HTML obrigatória:** `<article lang="pt-BR">`, H1 ausente no conteúdo (WordPress renderiza o título como H1), H2/H3 hierárquicos, FAQ em HTML puro com `<section class="faq-section">`.
4. **Zero JSON-LD / `<script>`** no conteúdo — removido do prompt e stripped via código no `parse_response`.
5. **Score QA mínimo:** 80/100. Self-healing automático (até 2 tentativas).
6. **PT-BR naturalizado:** termos técnicos em inglês devem ser traduzidos naturalmente.
7. **Word count:** alvo 700–1.400 palavras no prompt (o modelo tende a overshoot ~1.500–1.900). QA penaliza progressivamente: >1.500 → -5, >1.800 → -12, >2.000 → -25 (falha).
8. **Bullets obrigatórios:** listas de etapas, benefícios ou exemplos devem usar `<ul><li>` — reduz word count sem cortar raciocínio.
9. **Publicação manual:** nunca automatizar publicação em `run_lotes.sh`. Sempre `--test_one` primeiro.

## CLI — exemplos de uso

```bash
# Gerar lote com chave via .env
python orbit_content_engine.py \
  --model "google/gemini-2.5-flash" \
  --wp_url "https://sowads.com.br" \
  --wp_user "caio" \
  --wp_pass "..." \
  --csv_input "output_csv_batches_v2/lote_auto_temas.csv"

# Com fallback model
python orbit_content_engine.py \
  --model "google/gemini-2.5-flash" \
  --fallback_model "moonshotai/kimi-k2.6" \
  --csv_input "output_csv_batches_v2/lote_1.csv"

# Publicar 1 artigo para validação
python3 orbit_publisher.py --wp_url ... --wp_user ... --wp_pass ... \
  --input_dir output_csv_batches_v2 --test_one

# Publicar lote completo (só após validar --test_one)
python3 orbit_publisher.py --wp_url ... --wp_user ... --wp_pass ... \
  --input_dir output_csv_batches_v2 --all

# Monitor em tempo real
python3 orbit_monitor.py --log relatorios/run_pipeline.log
```

## Diretórios de saída

```
output_csv_batches_v2/     ← artigos gerados com métricas e URLs de imagem
output_social_copies/      ← copies por rede social
relatorios/                ← CSVs de temas + relatórios Markdown + media_index.json
briefings/                 ← dados de pesquisa por vertical/tema
```

## Credenciais (.env)

```
OPENROUTER_API_KEY=sk-or-v1-...
WORDPRESS_URL=https://sowads.com.br
WORDPRESS_USER=
WORDPRESS_PASSWORD=   # app password, não a senha real
BING_INDEXNOW_KEY=
```

## Adicionando novas verticais

1. Crie `briefings/<vertical>.md` com linha `# Palavras-chave para detecção: kw1, kw2, kw3`
2. Crie CSV em `output_csv_batches_v2/lote_<vertical>_temas.csv` com colunas `topic_pt,vertical,category`
3. Adicione lote no `run_lotes.sh` seguindo o padrão dos lotes existentes
4. Zero mudança de código necessária

**Verticais já implementadas:** turismo, automotivo

**Próximas sugeridas (prospects Sowads):** saúde/clínicas, imóveis/construtoras, educação/cursos, financeiro/fintechs, varejo/e-commerce, advocacia/jurídico, franquias, agro

## Diretrizes para evolução do código

- Não remover self-healing, scoring QA ou elementos visuais (tabelas, listas, FAQ)
- Novos briefings: criar `.md` em `briefings/` com a linha de keywords — sem mexer no código
- Novas etapas do pipeline: input CSV → processamento → output CSV + relatório Markdown
- Logs e relatórios são obrigatórios em toda etapa nova
- Controle de custo: modelo menor para self-healing se necessário; modelo maior apenas sob demanda via `--fallback_model`
- Publicação SEMPRE manual com `--test_one` primeiro — nunca automatizar
