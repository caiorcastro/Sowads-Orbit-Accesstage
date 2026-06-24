# Sistema de Benchmark e Auditoria de Modelos de IA
## Sowads Orbit — Como funciona, como usar, resultados do último teste

---

## O que é e para que serve

O Orbit tem um sistema de dois estágios para escolher qual modelo de IA usar em produção para cada cliente. Em vez de confiar em benchmarks genéricos da internet, a gente roda os modelos com o briefing real do cliente, nos temas reais do cliente, e avalia com o mesmo HTML que iria para o WordPress.

O resultado é uma nota objetiva por modelo — qualidade editorial, SEO semântico, velocidade e custo — que sustenta a escolha do modelo padrão e dos modelos alternativos por caso de uso.

---

## Os dois arquivos

### `tools/benchmark.py` — Geração dos artigos de teste

Roda cada modelo candidate com 3 tópicos fixos e coleta:
- HTML do artigo gerado (com template real do blog do cliente)
- Score QA técnico (estrutura HTML: FAQ, word count, H1, hyperlinks, tabela)
- Velocidade por artigo (segundos)
- Tokens consumidos e custo em USD
- Meta title e meta description

Saída: `output/testes/<model_id>/artigo_01.html`, `artigo_02.html`, `artigo_03.html` + `resultado.json`

**Como rodar:**
```bash
# Todos os modelos (sequencial, seguro)
python3 tools/benchmark.py

# Modelos específicos
python3 tools/benchmark.py --models gemini-flash,claude-sonnet-4.6,gpt-5.4-mini

# Com paralelismo (cuidado com rate limits)
python3 tools/benchmark.py --workers 3
```

### `tools/auditor.py` — Avaliação semântica dos artigos

Lê os HTMLs gerados pelo benchmark e pede para um modelo avaliador (Gemini 2.5 Pro) analisar cada artigo como três personas simultâneas:

| Persona | Peso | O que avalia |
|---|---|---|
| Gerente de Marketing | 35% | Tom consultivo, CTA, menção à marca, aberturas template vs. originais |
| CFO/Tesoureiro (humano) | 35% | Profundidade real, português-BR fluido, transmite autoridade |
| Especialista SEO/Crawler | 30% | Hierarquia de headings, FAQ schema, entidades semânticas, word count |

Os modelos são **anonimizados** durante a avaliação (Modelo A, B, C...) para eliminar viés do avaliador. O nome real é revelado só no relatório final.

Saída:
- `output/audit/relatorio_auditoria.html` — relatório visual completo com podium, tabela comparativa, cards por modelo
- `output/audit/relatorio_auditoria.md` — mesmo conteúdo em Markdown
- `output/audit/avaliacoes_parciais.json` — notas brutas (permite `--resume` se cair no meio)
- `output/audit/mapeamento_modelos.json` — mapa anonimato → modelo real

**Como rodar (após o benchmark):**
```bash
python3 tools/auditor.py

# Retomar avaliação interrompida
python3 tools/auditor.py --resume

# Limitar a N modelos (para testes rápidos)
python3 tools/auditor.py --limit 5
```

---

## Fluxo completo

```
benchmark.py  →  output/testes/<model>/resultado.json + artigos HTML
     ↓
auditor.py    →  lê os HTMLs, avalia com Gemini 2.5 Pro (anônimo)
     ↓
relatorio_auditoria.html  →  ranking + recomendações por caso de uso
```

---

## Resultado do último teste (maio/2026)

**25 modelos testados | 3 artigos por modelo | Avaliador: Gemini 2.5 Pro**

Tópicos de teste (mesmos para todos):
1. Centralização e Controle: Os Pilares de um Software Financeiro Eficiente
2. Van Bancária e Padrão CNAB: Segurança e Agilidade na Troca de Arquivos Financeiros
3. Cash Pooling: Maximizando a Eficiência da Tesouraria e a Centralização de Recursos

### Ranking completo — 25 modelos

| # | Modelo | Geral | Editorial | SEO | Velocidade | Custo/art | Palavras |
|---|--------|-------|-----------|-----|------------|-----------|---------|
| 🥇 | `anthropic/claude-opus-4.7` | **9.1/10** | 9.4 | 8.5 | 47s | $0.131 | 1455w |
| 🥈 | `anthropic/claude-sonnet-4.6` | **8.9/10** | 9.3 | 8.0 | 58s | $0.056 | 1390w |
| 🥉 | `openai/gpt-5.4-mini` | **8.8/10** | 8.5 | 9.5 | 16s | $0.013 | 1479w |
| 4 | `deepseek/deepseek-v4-flash` | 7.8/10 | 8.0 | 7.3 | 64s | $0.002 | 1426w |
| 5 | `xiaomi/mimo-v2.5-pro` | 7.7/10 | 8.2 | 6.5 | 78s | $0.021 | 1207w |
| 6 | `anthropic/claude-sonnet-4` | 7.6/10 | 7.8 | 7.5 | 36s | $0.049 | 1151w |
| 7 | `openai/gpt-5-nano` | 7.5/10 | 7.8 | 6.5 | 44s | $0.003 | 1412w |
| 8 | `xiaomi/mimo-v2-flash` | 7.4/10 | 7.5 | 7.2 | 29s | $0.001 | 1203w |
| 9 | `google/gemini-3-flash-preview` | 7.3/10 | 8.6 | 6.2 | 14s | $0.007 | 1269w |
| 10 | `google/gemini-2.0-flash-001` | 7.3/10 | 7.5 | 7.0 | 12s | $0.001 | 1093w |
| 11 | `google/gemini-2.5-pro` | 7.2/10 | 8.0 | 5.0 | 59s | — | — |
| 12 | `openai/gpt-5.4` | 7.2/10 | 7.8 | 5.0 | 68s | — | — |
| 13 | `openai/gpt-5.5` | 6.9/10 | 8.7 | 3.0 | 61s | — | — |
| 14 | `google/gemini-2.5-flash` | 6.9/10 | 7.6 | 5.5 | 74s | — | — |
| 15 | `qwen/qwen3-235b-a22b-2507` | 6.8/10 | 6.6 | 7.5 | 63s | — | — |
| 16 | `google/gemini-3.1-flash-lite-preview` | 6.7/10 | 7.8 | 3.5 | 64s | — | — |
| 17 | `openai/gpt-5-mini` | 6.1/10 | 6.5 | 5.2 | 68s | — | — |
| 18 | `openai/gpt-5-chat` | 5.8/10 | 7.2 | 2.0 | 63s | — | — |
| 19 | `google/gemini-2.5-flash-lite` | 5.6/10 | 5.9 | 4.3 | 65s | — | — |
| 20 | `google/gemini-3.1-pro-preview` | 5.5/10 | 5.8 | 5.2 | 68s | — | — |
| 21 | `deepseek/deepseek-chat-v3-0324` | 4.7/10 | 4.8 | 4.7 | 71s | — | — |
| 22 | `google/gemini-2.0-flash-lite-001` | 3.9/10 | 4.3 | 3.0 | 63s | — | — |
| 23 | `meta-llama/llama-4-scout` | 3.1/10 | 2.8 | 4.2 | 77s | — | — |
| 24 | `anthropic/claude-3.5-haiku` | 2.8/10 | 2.5 | 3.5 | 68s | — | — |
| 25 | `meta-llama/llama-4-maverick` | 2.6/10 | 2.1 | 4.0 | 56s | — | — |

### Top 10 — análise por caso de uso

| Modelo | Cenário ideal | Por quê |
|--------|--------------|---------|
| `claude-opus-4.7` | **Conteúdo flagship / pillar** | Nota mais alta em editorial (9.4). Use quando a qualidade justifica o custo ($0.13/art). |
| `claude-sonnet-4.6` | **Qualidade alta viável** | 8.9/10 com custo 4x menor que o opus. Melhor custo-benefício de alta qualidade. |
| `gpt-5.4-mini` | **Padrão de produção** | 8.8/10 + SEO líder (9.5) + 16s/artigo + $0.013/art. Melhor equilíbrio geral. |
| `deepseek-v4-flash` | **Alto volume / budget** | 7.8/10 com $0.002/art — o mais barato com nota aceitável. Para lotes de 300+. |
| `mimo-v2.5-pro` | **Editorial consistente** | Editorial 8.2 com custo médio. Bom para clientes que priorizam fluência. |
| `claude-sonnet-4` | **Qualidade Anthropic econômica** | 7.6/10 com bom SEO (7.5). Opção quando sonnet-4.6 está indisponível. |
| `gpt-5-nano` | **Volume rápido OpenAI** | 7.5/10 com $0.003/art e 44s. Melhor custo-benefício OpenAI para volume. |
| `mimo-v2-flash` | **Ultra baixo custo** | 7.4/10 com $0.001/art e 29s. Xiaomi surpreendeu. Bom para pré-geração/rascunhos. |
| `gemini-3-flash-preview` | **Velocidade + editorial** | Editorial 8.6 com apenas 14s/art. O mais rápido com qualidade editorial alta. |
| `gemini-2.0-flash-001` | **Velocidade + custo mínimo** | 7.3/10 com 12s/art e $0.001/art. O mais veloz entre os top 10. |

### Notas importantes sobre os resultados

**Surpresas positivas:**
- `gpt-5.4-mini` superou modelos muito mais caros — SEO 9.5 é o melhor de toda a lista
- Xiaomi (`mimo-v2-flash` e `mimo-v2.5-pro`) apareceu no top 10, desconhecido antes do teste
- `gemini-3-flash-preview` tem editorial 8.6 com velocidade de 14s — melhor velocidade/editorial

**Surpresas negativas:**
- `gemini-2.5-flash` (modelo padrão atual) ficou em 14º com 6.9/10 — superado por vários concorrentes
- `gemini-2.5-pro` ficou em 11º apesar do preço alto — SEO 5.0 é fraco
- `llama-4-maverick` e `llama-4-scout` reprovaram (abaixo de 4.0)
- `claude-3.5-haiku` reprovado com 2.8/10 — não adequado para esse tipo de conteúdo

**Problemas sistêmicos identificados pelo auditor:**
- Aberturas "template" aparecem em quase todos os modelos (frases como "No cenário atual...")
- FAQ sem `<section class="faq-section">` correto em vários modelos médios
- Modelos OpenAI GPT-5.x têm SEO fraco consistentemente (exceção: gpt-5.4-mini)
- DeepSeek e Qwen produzem português aceitável mas com cacoetes de tradução

---

## Como adaptar para um novo cliente

Para rodar o benchmark em um cliente novo, os únicos arquivos que mudam são:

1. **`client/guia_agente.md`** — tom, keywords, blacklist do cliente
2. **`client/dossie_produtos.md`** — referência técnica dos produtos
3. **`BENCHMARK_TOPICS`** em `benchmark.py` — 3 tópicos representativos do nicho

O sistema de avaliação (`auditor.py`) é independente de cliente — as personas e critérios são universais para conteúdo B2B.

---

## Onde ficam os arquivos de resultado

```
output/
  testes/
    <model_id>/
      artigo_01.html       ← artigo com template real do blog
      artigo_02.html
      artigo_03.html
      resultado.json       ← métricas brutas: score, tokens, custo, tempo
  audit/
    relatorio_auditoria.html   ← relatório visual completo
    relatorio_auditoria.md     ← mesma coisa em markdown
    avaliacoes_parciais.json   ← notas brutas por modelo (permite --resume)
    mapeamento_modelos.json    ← mapa anônimo → modelo real
```

O relatório publicado do teste Accesstage (abr/2026) está em:
`https://caiorcastro.github.io/orbit-audit-accesstage-abr26/`
