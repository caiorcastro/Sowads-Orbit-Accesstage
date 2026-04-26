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
  articles/      CSVs de artigos gerados
  social/        TXTs de copies por rede
  events/        CSVs de eventos para backend Sowads
  reports/       relatórios + media_index.json
```

## Provedor de IA — REGRA FIXA

**Sempre OpenRouter. Nunca outra API sem aprovação explícita.**

```
Endpoint : https://openrouter.ai/api/v1/chat/completions
Modelo   : deepseek/deepseek-v4-pro
Chave    : OPENROUTER_API_KEY no .env
```

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
# 1. GERAR artigos (nunca publica automaticamente)
./run_lotes.sh

# 2. GERAR copies sociais + events CSV
python3 engine/social_agent.py --count 40

# 3. VALIDAR 1 artigo antes de publicar
python3 engine/publisher.py --test_one
# Verificar no WP: imagem destacada, conteúdo, categoria, sem código no final

# 4. PUBLICAR lote (só após validar --test_one)
python3 engine/publisher.py --all

# 5. INDEXAR no Bing (opcional)
python3 tools/bing_indexnow.py

# Monitorar progresso em tempo real
python3 tools/monitor.py
```

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
9. **CSVs nomeados com stem do input** — nunca sobrescrever entre lotes
10. **Sem referências numéricas obrigatórias** — compliance Accesstage

## Regras de comportamento

- Ler arquivos reais antes de agir — nunca inventar estado
- `git status` antes de qualquer edição de pipeline
- Nunca sobrescrever CSVs sem confirmar
- Fixes em posts publicados: XML-RPC `wp.editPost` com regex — nunca regenerar
- Ao final de sessão com mudanças: atualizar CLAUDE.md + ORBIT_MASTER.md + commit + push

## Pendências do cliente

- Documentação técnica oficial dos produtos (PDF/links) — a receber
- Restrições específicas de claims técnicos — a receber
- Campanhas ativas + calendário promocional — a receber
- Credenciais reais em `client/credentials.env` — a preencher
