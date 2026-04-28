# Sowads Orbit — Accesstage · CLAUDE.md
# Leia este arquivo INTEIRO antes de qualquer ação no projeto.

## O que é este projeto

Motor de conteúdo SEO/AIO da Sowads configurado para o cliente **Accesstage**.
Gera artigos HTML para WordPress, copies sociais por rede e events CSV para o backend Sowads.
Cliente: Accesstage — produto principal: **Plataforma Veragi** (fintech B2B).

## Estrutura de pastas

```
engine/          ← pipeline principal
  content_engine.py   motor: prompt → OpenRouter → QA → CSV
  publisher.py        publica no WP via XML-RPC
  social_agent.py     copies por rede + events CSV
  media_indexer.py    indexa biblioteca WP, match temático Jaccard
  qa_validator.py     score 0-100 + self-healing
  topic_creator.py    brainstorm de temas

tools/           ← utilitários
  monitor.py          monitor em tempo real
  optimizer.py        otimização AIO em lote
  bing_indexnow.py    push IndexNow para Bing
  check_models.py     lista modelos disponíveis
  preview_generator.py  gera HTML mock do blog p/ aprovação do cliente
  merge_retry.py      mescla CSV de retry no batch principal

config/          ← regras técnicas de SEO/AIO/estrutura HTML (sem marca, sem cliente)
  schema_orbit_ai_v1.json   SEO técnico puro — Sowads/produtos removidos

client/          ← documentos do cliente (versionados, exceto credentials)
  briefing_cliente.md  briefing original enviado pela Accesstage
  guia_agente.md       tom, keywords obrigatórias, blacklist, argumentos por módulo
  dossie_produtos.md   referência técnica completa de todos os módulos Veragi
  diretrizes.md        guia operacional: compliance, SEO, checklist
  credentials.env      NUNCA commitado: WP + redes sociais

briefings/       ← pesquisas de mercado por vertical (injetadas no prompt)
output/          ← tudo que sai (gitignored)
  articles/      CSVs de artigos gerados + CSVs de retry
  social/        TXTs de copies por rede
  events/        CSVs de eventos para backend Sowads
  reports/       relatórios + media_index.json
  preview/       HTML mock do blog para aprovação (index.html + artigos)
```

## Provedor de IA — REGRA FIXA

**Sempre OpenRouter. Nunca outra API sem aprovação explícita.**

```
Endpoint       : https://openrouter.ai/api/v1/chat/completions
Chave          : OPENROUTER_API_KEY no .env

Modelo padrão  : google/gemini-2.5-flash       (~15s/artigo, $0.30/$2.50 por M tokens)
Fallback padrão: google/gemini-2.5-flash-lite   (~8s/artigo,  $0.10/$0.40 por M tokens)
Qualidade max  : anthropic/claude-opus-4.7       (~40s/artigo — usar apenas com --model explícito)
```

### Comparativo de modelos testados (benchmark Sowads Orbit × Accesstage, abr/2026)

| Modelo | Vel. média | Input/M | Output/M | Notas |
|---|---|---|---|---|
| `google/gemini-2.5-flash` | ~15s | $0.30 | $2.50 | Padrão — rápido, score 100 |
| `google/gemini-2.5-flash-lite` | ~8s | $0.10 | $0.40 | Volume alto, muito barato |
| `anthropic/claude-opus-4.7` | ~40s | $15.00 | $75.00 | Qualidade editorial máxima, 100/100 QA; custo alto para lote |
| `deepseek/deepseek-v4-pro` | ~170s | $0.44 | $0.87 | Qualidade alta, lento, risco de hang |
| `deepseek/deepseek-chat-v3-0324` | ~40s | $0.20 | $0.77 | Custo-benefício DeepSeek |

**Aviso de timeout:** DeepSeek usa streaming chunked — o `timeout=90` do requests não funciona.
O engine usa wall-clock thread de 240s como hard limit. Não reduzir esse valor.

### Benchmark completo — 25 modelos auditados
Relatório de auditoria semântica gerado em `tools/auditor.py` (avaliador: `google/gemini-2.5-pro`).
Relatório publicado (noindex): https://caiorcastro.github.io/orbit-audit-accesstage-abr26/
10 artigos de prova reais com opus 4.7 — todos 100/100 QA: `output/articles/lote_veragi_claude-opus-4-7_batch1_artigos_1_a_10.csv`
Preview dos artigos (noindex): https://sowads-orbit.web.app

## Sistema de Contexto do Cliente

A cada geração, o motor injeta dois blocos vindos de `client/`:

**`load_client_compliance()`** — lê `client/guia_agente.md` inteiro.
Injeta no prompt: tom de voz, banco de keywords obrigatórias, blacklist completa, argumentos de venda por módulo.

**`load_product_context(topic)`** — lê `client/dossie_produtos.md` e extrai a seção mais relevante ao tema:

| Marcador  | Keywords detectadas                                              |
|-----------|------------------------------------------------------------------|
| `### 1.1` | contas a pagar, pagamento, comprovante, autorização              |
| `### 1.2` | tesouraria, extrato, saldo, multibanco, tarifas, tesoureiro      |
| `### 1.3` | crédito, antecipação, recebíveis, risco sacado, capital de giro  |
| `### 1.4` | analytics, dados preditivos, relatório, dashboard, planejamento  |
| `## 2.`   | edi, api, open finance, van bancária, cnab, integração bancária  |
| `## 3.`   | cash pooling                                                     |

Se nenhuma keyword bater, injeta os primeiros 2000 chars do dossiê.
Para adicionar novo produto: atualizar `dossie_produtos.md` + acrescentar entry em `MODULE_KEYWORDS`.

---

## Pipeline — passo a passo

```bash
# 1. GERAR artigos + copies sociais + events CSV (tudo de uma vez)
./run_lotes.sh
# run_lotes.sh já chama social_agent --from_csv automaticamente ao final

# 2. GERAR copies/events manualmente (caso queira rodar separado)
python3 engine/social_agent.py --from_csv output/articles/<batch>.csv
# Obs: --from_csv não precisa de wp_post_id — usa DRAFT-N como placeholder

# 3. VALIDAR 1 artigo antes de publicar
python3 engine/publisher.py --test_one
# Verificar no WP: imagem destacada, conteúdo, categoria, sem código no final

# 4. PUBLICAR lote (só após validar --test_one)
python3 engine/publisher.py --all

# 5. INDEXAR no Bing (opcional)
python3 tools/bing_indexnow.py

# Monitorar progresso em tempo real
python3 tools/monitor.py

# Preview HTML para aprovação do cliente
python3 tools/preview_generator.py
# Sobe para Firebase: firebase deploy --only hosting --project sowads-orbit
```

## Firebase — Preview para clientes/parceiros

```
Projeto : sowads-orbit (caiorcastro@gmail.com)
URL     : https://sowads-orbit.web.app  ← noindex, não indexável
Config  : firebase.json + .firebaserc na raiz do repo
Pasta   : output/preview/ (gitignored — redeploy sempre que regenerar)

Deploy  : firebase deploy --only hosting --project sowads-orbit
```

**Regra:** Nunca subir dados de custo/token/velocidade nos previews — são para controle interno.
Os HTMLs de preview são `output/preview/` — não commitados, só deployados no Firebase.

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
A categoria vem sempre do CSV de temas. Nunca inferir por keyword.

## QA Scoring

| Condição | Penalidade |
|---|---|
| FAQ ausente | -20 |
| Hyperlinks no conteúdo | -15 |
| Word count < 700 | -15 |
| H1 no conteúdo | -10 |
| Word count > 1.800 | -12 |
| Word count > 2.000 | -25 → self-heal |

Score mínimo para publicação: **80/100**.

## Invariantes — nunca quebrar

1. **OpenRouter sempre** — nunca API direta
2. **Zero hyperlinks, `<img>`, `<figure>` ou JSON-LD** no conteúdo
3. **Sem H1 no conteúdo** — WordPress usa o título do post como H1
4. **FAQ HTML puro** com `<section class="faq-section">` — sem `<script>`
5. **Sem asteriscos `**texto**`** — removidos via código em `parse_response()`
6. **Categorias do CSV de temas** — nunca inferir
7. **Imagens da biblioteca WP** — nunca gerar ou subir nova
8. **Publicação manual** — `--test_one` → revisar → `--all`
9. **CSVs nomeados com stem do input + model slug** — nunca sobrescrever entre lotes
10. **Sem referências numéricas obrigatórias** — compliance Accesstage
11. **Reports de produção são internos** — nunca expor custo/token/velocidade em previews ou URLs do cliente

## Estado atual do engine (2026-04-27) — não regredir

### content_engine.py
- `call_openrouter()` retorna **3-tupla**: `(text, model, {"tok_in", "tok_out", "elapsed_api"})`
- `MODEL_PRICING` dict + `calc_cost(model, tok_in, tok_out)` → custo em USD
- CSV de artigos inclui colunas: `tok_in`, `tok_out`, `elapsed_s`, `cost_usd`
- Nome do CSV: `{input_stem}_{model_slug}_batch{n}_artigos_{a}_a_{b}.csv`
- `generate_report()`: seção de custo/velocidade, labels sem falso erro (H1 ✅ correto, JSON-LD ✅ correto)
- Colunas `_*` (underscore) não são salvas no CSV de output WP (são internas)

### social_agent.py
- `--from_csv <path>` gera copies + events sem precisar de wp_post_id
- Usa `DRAFT-N` como placeholder de ID e slug para URL
- `run_lotes.sh` chama automaticamente ao final: `python3 engine/social_agent.py --from_csv "$LATEST_CSV"`

## Regras de comportamento

- **Ler CLAUDE.md inteiro antes de qualquer ação** — nunca assumir estado de memória
- Ler arquivos reais antes de agir — nunca inventar estado
- `git status` antes de qualquer edição de pipeline
- Nunca sobrescrever CSVs sem confirmar
- Fixes em posts publicados: XML-RPC `wp.editPost` com regex — nunca regenerar
- Ao final de sessão com mudanças: atualizar CLAUDE.md + commit + push

## Pendências do cliente

- Documentação técnica oficial dos produtos (PDF/links) — a receber
- Restrições específicas de claims técnicos — a receber
- Campanhas ativas + calendário promocional — a receber
- Credenciais reais em `client/credentials.env` — a preencher
