# Sowads Orbit AI — Content Engine

Motor de conteudo AIO/SEO com IA para escalar autoridade digital. Gera artigos otimizados para WordPress cruzando necessidades de verticais de negocios com as solucoes da Sowads.

## O que e a Sowads

Agencia de marketing digital especializada em **SEO, AIO e gestao estrategica de midia paga**. Meta Tech Provider.

### Produtos

| Produto | O que faz |
|---|---|
| **Orbit AI** | Inteligencia de conteudo + SEO com IA para autoridade digital e posicionamento organico/AIO |
| **Automacao Meta Ads** | Ferramenta que conecta com bancos de dados e publica campanhas completas com poucos cliques |

> **Importante:** Orbit AI (organico) e Meta Ads (pago) sao produtos complementares mas independentes. Um NAO influencia o outro.

---

## Pipeline

```
1. TOPICOS        -> orbit_topic_creator.py       (gera temas via Gemini)
2. CONTEUDO       -> orbit_content_engine.py       (gera artigos HTML completos)
3. OTIMIZACAO     -> orbit_optimizer_v2.py         (remove JSON-LD, pontua AIO 1-10)
4. VALIDACAO QA   -> orbit_qa_validator.py         (score 0-100 por artigo)
5. DEPLOY         -> CSV -> WordPress All-Import   (manual)
6. INDEXACAO      -> bing_index_now.py             (push IndexNow no Bing)
```

## Arquivos

| Arquivo | Funcao |
|---|---|
| `orbit_content_engine.py` | Gerador principal — Gemini API -> artigos HTML em lotes |
| `orbit_optimizer.py` | Lib de otimizacao (importada pelo v2 e parallel) |
| `orbit_optimizer_v2.py` | Auditor — remove JSON-LD, converte FAQ p/ HTML puro, score AIO |
| `orbit_optimizer_parallel.py` | Otimizacao paralela de multiplos lotes |
| `orbit_qa_validator.py` | Validador QA — score 0-100, flags problemas |
| `orbit_topic_creator.py` | Brainstorm de temas via IA |
| `bing_index_now.py` | Forca indexacao via Bing IndexNow API |
| `check_models.py` | Lista modelos Gemini disponiveis |
| `regras_geracao/schema_orbit_ai_v1.json` | Schema de regras — cerebro do sistema |

## Como usar

### 1. Gerar temas
```bash
python orbit_topic_creator.py --api_key "SUA_CHAVE_GEMINI" --count 10
```

### 2. Gerar artigos
```bash
python orbit_content_engine.py --api_key "SUA_CHAVE_GEMINI" --model "gemini-2.5-flash" --start_batch 1
```

### 3. Otimizar
```bash
python orbit_optimizer_v2.py --api_key "SUA_CHAVE_GEMINI" --model "gemini-2.5-flash"
```

### 4. Validar qualidade
```bash
python orbit_qa_validator.py --path "output_csv_batches_v2/*.csv"
```

### 5. Indexar no Bing
```bash
python bing_index_now.py --api_key "SUA_CHAVE_INDEXNOW" --host "https://www.sowads.com.br" --urls_file urls.txt
```

## Configuracao

- **API Key Gemini:** Passe via `--api_key` ou defina `GEMINI_API_KEY` como variavel de ambiente
- **Schema:** Edite `regras_geracao/schema_orbit_ai_v1.json` para ajustar regras, verticais e brand guidelines

## Tech Stack

- Python 3.x
- Google Gemini API
- Pandas
- Bing IndexNow API

---

Sowads Technology Team | sowads.com.br
