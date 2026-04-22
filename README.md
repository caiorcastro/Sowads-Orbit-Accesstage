<div align="center">

```
 ██████╗ ██████╗ ██████╗ ██╗████████╗     █████╗ ██╗
██╔═══██╗██╔══██╗██╔══██╗██║╚══██╔══╝    ██╔══██╗██║
██║   ██║██████╔╝██████╔╝██║   ██║       ███████║██║
██║   ██║██╔══██╗██╔══██╗██║   ██║       ██╔══██║██║
╚██████╔╝██║  ██║██████╔╝██║   ██║       ██║  ██║██║
 ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═╝   ╚═╝       ╚═╝  ╚═╝╚═╝
```

**Motor de Conteúdo SEO/AIO em Escala — Sowads Agência**

![Versão](https://img.shields.io/badge/versão-3.0-FFB300?style=for-the-badge)
![Provedor IA](https://img.shields.io/badge/IA-OpenRouter%20%7C%20Gemini%202.5%20Flash-4285F4?style=for-the-badge&logo=google)
![WordPress](https://img.shields.io/badge/WordPress-XML--RPC-21759B?style=for-the-badge&logo=wordpress)
![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python)
![Status](https://img.shields.io/badge/status-produção-00C851?style=for-the-badge)

*Gera artigos HTML otimizados para AIO/SEO, distribui imagens da biblioteca WordPress por canal e publica como rascunho — com validação obrigatória antes de qualquer lote ir ao ar.*

</div>

---

## O que é o Orbit AI v3

O **Orbit AI** é o motor de conteúdo interno da Sowads. Ele combina:

- **OpenRouter + Gemini 2.5 Flash** para geração de artigos HTML editorial-grade
- **Sistema de briefings** — pesquisas reais enviadas pelo time são injetadas automaticamente no prompt por detecção de keywords
- **Matching de imagens** — reusa a biblioteca do WordPress sem gerar nem subir nada novo, com score de similaridade e penalidade por repetição
- **Self-healing** — artigos com score QA abaixo de 80/100 são reescritos automaticamente (até 2x)
- **Publisher com validação manual** — sempre testa 1 artigo antes de publicar o lote

### O que mudou na v3

| Feature | v2 | v3 |
|---|---|---|
| Provedor IA | Google Generative AI SDK | OpenRouter (multi-modelo) |
| Briefings | Não existia | `.md` com keyword detection automática |
| Imagens | Não existia | Matching Jaccard + penalidade por repetição |
| JSON-LD no conteúdo | Gerado automaticamente | Removido — stripped via código |
| Word count | 1.200–2.500 palavras | 700–1.400 no prompt (resulta em 1.500–1.900) |
| Publicação | Automática no pipeline | Manual obrigatória — `--test_one` antes de `--all` |
| Imagem destacada | Não setava | Set automático via XML-RPC após publicação |
| Monitor | Não existia | `orbit_monitor.py` com ETA, scores, heals em tempo real |
| Nome de CSV | Sobrescrevia | Inclui stem do lote — nunca sobrescreve |

---

## Arquitetura do Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     ORBIT AI v3 — PIPELINE                      │
└─────────────────────────────────────────────────────────────────┘

  [1] PESQUISA          [2] TEMAS              [3] GERAÇÃO
  briefings/*.md   →   lote_*_temas.csv   →   orbit_content_engine.py
  (você envia)         (topic_pt, vertical,    ↓ OpenRouter Gemini 2.5 Flash
                        category)              ↓ Briefing injection automática
                                               ↓ Self-healing QA (até 2x)
                                               ↓ Image matching (Jaccard)
                                               ↓ output_csv_batches_v2/

  [4] VALIDAÇÃO         [5] PUBLICAÇÃO         [6] DISTRIBUIÇÃO
  orbit_publisher.py →  orbit_publisher.py →   orbit_social_agent.py
  --test_one            --all                  (copies LinkedIn/IG/FB/TT)
  (conferir no WP)      (lote completo)
                        ↓ Featured image set
                        ↓ Categoria detectada
                        ↓ Meta SEO (Yoast + RankMath)
```

---

## Estrutura de arquivos

```
Sowads-v2-local/
│
├── orbit_content_engine.py   # Motor principal — gera artigos
├── orbit_qa_validator.py     # Validação de qualidade 0-100
├── orbit_publisher.py        # Publicação WP com imagem destacada
├── orbit_media_indexer.py    # Indexação e matching de imagens WP
├── orbit_monitor.py          # Monitor de progresso em tempo real
├── orbit_social_agent.py     # Copies para redes sociais
├── orbit_topic_creator.py    # Brainstorm de temas via IA
├── orbit_optimizer_v2.py     # Otimização AIO em lote
├── bing_index_now.py         # Push IndexNow para Bing
├── run_lotes.sh              # Pipeline sequencial (só geração)
│
├── briefings/                # Pesquisas enviadas pelo time
│   ├── turismo.md
│   ├── auto.md
│   └── <nova_vertical>.md   # Adicione aqui — zero código
│
├── regras_geracao/
│   └── schema_orbit_ai_v1.json  # Brand, compliance, regras SEO/AIO
│
├── output_csv_batches_v2/    # Artigos gerados + URLs de imagem
│   ├── lote_auto_temas.csv
│   ├── lote_turismo_temas.csv
│   └── lote_auto_batch1_artigos_1_a_20.csv  # Output gerado
│
├── output_social_copies/     # Copies por rede social
├── relatorios/               # Relatórios Markdown + media_index.json
└── .env                      # Credenciais (não commitado)
```

---

## Configuração inicial

### 1. Instalar dependências

```bash
pip install openai requests pandas python-dotenv xmlrpc
```

### 2. Criar `.env`

```env
OPENROUTER_API_KEY=sk-or-v1-...
WORDPRESS_URL=https://sowads.com.br
WORDPRESS_USER=caio
WORDPRESS_PASSWORD=xxxx xxxx xxxx xxxx   # App Password — não a senha real
BING_INDEXNOW_KEY=...
```

> **App Password WordPress:** Painel WP → Usuários → Seu Perfil → Application Passwords → gerar nova.

---

## Sistema de Briefings (pesquisas)

Os briefings são **pesquisas reais enviadas pelo time** — dados de mercado, estudos, notícias, dados de clientes — que ficam além do corte de conhecimento da IA.

### Como criar um briefing

1. Crie o arquivo `briefings/<vertical>.md`
2. A **primeira linha** deve ser a lista de keywords de detecção:

```markdown
# Palavras-chave para detecção: turismo, viagem, hotel, agência de viagem, destino, roteiro

## Contexto de mercado 2026

O turismo brasileiro registrou crescimento de 18% no segmento de viagens domésticas...
[coloque aqui toda a sua pesquisa — sem limite de tamanho, injeta até 800 palavras]
```

3. O engine detecta automaticamente se o tema bate com as keywords e injeta os primeiros **800 palavras** no prompt como bloco de contexto.
4. **Nenhuma mudança de código necessária.** Apenas crie o arquivo.

### Briefings existentes

| Arquivo | Vertical | Keywords principais |
|---|---|---|
| `briefings/turismo.md` | Turismo | turismo, viagem, hotel, OTA, CVC |
| `briefings/auto.md` | Automotivo | automotivo, carro, EV, montadora, elétrico |

### Adicionando nova vertical via briefing

```bash
# Exemplo: vertical de saúde
cat > briefings/saude.md << 'EOF'
# Palavras-chave para detecção: saúde, clínica, médico, plano de saúde, telemedicina, hospital

[cole aqui sua pesquisa de mercado]
EOF
```

Pronto. Próximo lote com temas de saúde vai usar o briefing automaticamente.

---

## Criando o CSV de temas

O CSV de entrada define os artigos a serem gerados. Salve em `output_csv_batches_v2/`.

### Formato obrigatório

```csv
topic_pt,vertical,category
"Título completo do artigo em PT-BR",vertical,categoria
```

### Colunas

| Coluna | Obrigatório | Valores aceitos | Exemplo |
|---|---|---|---|
| `topic_pt` | ✅ | Qualquer string | `"AIO para Lançamentos: Como aparecer no ChatGPT"` |
| `vertical` | ✅ | turismo, automotivo, saude, imoveis, ... | `automotivo` |
| `category` | ✅ | SEO & AIO, Conteúdo, Estratégia e Performance, Mídia Paga | `SEO & AIO` |

### Exemplo completo

```csv
topic_pt,vertical,category
"AIO para Lançamentos Automotivos: Como garantir que as IAs recomendem seu modelo",automotivo,SEO & AIO
"GEO e a Jornada do Test-Drive: Usando geolocalização para atrair compradores",automotivo,SEO & AIO
"Schema Markup para Inventário de Veículos: Preços e estoque em tempo real no Google",automotivo,SEO & AIO
```

### Categorias WordPress disponíveis

| Categoria CSV | Categoria WP |
|---|---|
| `SEO & AIO` | SEO e AI-SEO |
| `Conteúdo` | Conteúdo em Escala |
| `Estratégia e Performance` | Estratégia e Performance |
| `Mídia Paga` | Mídia Paga |
| `Data e Analytics` | Dados e Analytics |

---

## Gerando artigos

### Comando básico

```bash
python3 orbit_content_engine.py \
  --model "google/gemini-2.5-flash" \
  --wp_url "https://sowads.com.br" \
  --wp_user "caio" \
  --wp_pass "SUA_APP_PASSWORD" \
  --csv_input "output_csv_batches_v2/lote_auto_temas.csv"
```

### Parâmetros disponíveis

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `--model` | ✅ | Modelo principal (ex: `google/gemini-2.5-flash`) |
| `--csv_input` | ✅ | Caminho para o CSV de temas |
| `--wp_url` | Recomendado | URL do WordPress — necessário para indexar imagens |
| `--wp_user` | Recomendado | Usuário WordPress |
| `--wp_pass` | Recomendado | App Password WordPress |
| `--fallback_model` | Opcional | Modelo de fallback em caso de erro (ex: `moonshotai/kimi-k2.6`) |
| `--openrouter_key` | Opcional | Chave OpenRouter (default: `OPENROUTER_API_KEY` do `.env`) |

### Pipeline completo com múltiplos lotes

```bash
./run_lotes.sh
```

O `run_lotes.sh` roda os lotes sequencialmente e **NÃO publica automaticamente** — publicação é sempre manual.

### Acompanhar em tempo real

Em outro terminal, enquanto o pipeline roda:

```bash
python3 orbit_monitor.py --log relatorios/run_v3_auto.log
```

O monitor exibe progresso, score QA médio, ETA, self-healing, briefings e imagens matched.

---

## Output gerado

Cada lote gera um CSV em `output_csv_batches_v2/` com o nome `{lote}_batch{n}_artigos_{start}_a_{end}.csv`.

### Colunas de saída

| Coluna | Descrição |
|---|---|
| `post_title` | Título do artigo |
| `post_content` | HTML completo do artigo |
| `post_status` | `draft` → `published` após publicação |
| `meta_title` | Meta title SEO (máx 60 chars) |
| `meta_description` | Meta description SEO (máx 155 chars) |
| `qa_score` | Score QA 0-100 |
| `heal_retries` | Quantas correções automáticas foram feitas |
| `img_blog` | URL da imagem para post WordPress (16:9) |
| `img_linkedin` | URL da imagem para LinkedIn (3:2) |
| `img_instagram` | URL da imagem para Instagram (4:5) |
| `img_facebook` | URL da imagem para Facebook |
| `img_tiktok` | URL da imagem para TikTok (9:16) |
| `wp_post_id` | ID do post WP (preenchido após publicação) |
| `published_at` | Timestamp da publicação |

---

## Publicando no WordPress

### ⚠️ Regra fixa: sempre validar 1 artigo antes do lote

```bash
# PASSO 1 — Publicar 1 artigo para validação
python3 orbit_publisher.py \
  --wp_url "https://sowads.com.br" \
  --wp_user "caio" \
  --wp_pass "SUA_APP_PASSWORD" \
  --input_dir "output_csv_batches_v2" \
  --test_one

# PASSO 2 — Abrir no WordPress e conferir:
#   ✅ Imagem destacada aparece no painel lateral
#   ✅ Sem código <script> ou JSON-LD no final
#   ✅ FAQ com visual em caixa (fundo cinza, bordas)
#   ✅ Word count 1.500–1.900 palavras
#   ✅ Compliance OK

# PASSO 3 — Publicar o lote completo
python3 orbit_publisher.py \
  --wp_url "https://sowads.com.br" \
  --wp_user "caio" \
  --wp_pass "SUA_APP_PASSWORD" \
  --input_dir "output_csv_batches_v2" \
  --all
```

### O que o publisher faz

1. Lê todos os CSVs em `output_csv_batches_v2/` com status `draft`
2. Detecta a categoria automaticamente por keywords do título/conteúdo
3. Publica via XML-RPC como rascunho (ou `--publish` para publicar direto)
4. Seta a **imagem destacada** via `get_media_id_by_url` + `set_post_thumbnail` XML-RPC
5. Injeta meta SEO no Yoast e RankMath
6. Marca `published` no CSV e gera relatório em `relatorios/report_publicacao_*.md`

### Saída do publisher

```
[1/20] AIO para Lançamentos Automotivos...  [Estratégia e Performance]  OK (ID: 32235) 🖼️
[2/20] GEO e a Jornada do Test-Drive...     [Estratégia e Performance]  OK (ID: 32237) 🖼️
[3/20] Estrutura Semântica...               [SEO e AI-SEO]              OK (ID: 32239) ⚠️ sem imagem
```

`🖼️` = imagem setada | `⚠️ sem imagem` = URL não encontrada na biblioteca WP

---

## Copies para redes sociais

```bash
python3 orbit_social_agent.py \
  --input "output_csv_batches_v2/lote_auto_batch1_artigos_1_a_20.csv" \
  --output_dir "output_social_copies/"
```

### O que é gerado por artigo

| Canal | Tom | Formato |
|---|---|---|
| LinkedIn | Autoridade e dados | Post longo com hashtags profissionais |
| Instagram | Engajamento visual | Caption curta + 5 hashtags de nicho |
| Facebook | Alcance e compartilhamento | Post médio conversacional |
| TikTok | Vídeo curto educativo | Script 30–60s com gancho inicial |

As URLs de imagem por canal já vêm do CSV — passe para a equipe de design/social junto com o copy.

---

## Sistema de imagens

As imagens são **reutilizadas da biblioteca WordPress existente** — nunca geradas, nunca uploadadas.

### Como funciona o matching

O engine busca todos os itens da biblioteca WP, agrupa por prefixo e calcula:
- **Jaccard similarity** entre palavras do tema e topic-slug da imagem — peso 80%
- **Completude do grupo** (tem todos os canais?) — peso 20%
- **Penalidade por repetição:** `use_count=0 → 1.0x | 1 → 0.5x | 2 → 0.25x | 3+ → 0.10x`

### Padrão de nomenclatura

```
{Prefix}_{N}_{type}_{topic-slug}_{hash}.jpg

Exemplos:
  Orbit_1_wp_como-usar-ia-no-seo_a1b2c3.jpg    → blog 16:9
  Orbit_1_li_como-usar-ia-no-seo_a1b2c3.jpg    → LinkedIn
  Orbit_1_ig_como-usar-ia-no-seo_a1b2c3.jpg    → Instagram
```

**Tipos reconhecidos:** `wp`/`blog` → post | `li` → LinkedIn | `ig` → Instagram | `fb` → Facebook | `tt` → TikTok | `meta` → 4:5 (substitui ig+fb)

---

## Sistema de qualidade (QA)

Score 0–100. Abaixo de 80 dispara self-healing (até 2x).

| Checagem | Penalidade | Critério |
|---|---|---|
| `<article lang="pt-BR">` | -10 | Obrigatório |
| FAQ `faq-section` | -10 | ≥5 perguntas e respostas |
| Tabela HTML | -10 | `<table>` com `<thead>` e `<tbody>` |
| H2 mínimo | -10 | Pelo menos 2 |
| H3 mínimo | -5 | Pelo menos 3 |
| Referências numéricas | -5 | Mínimo 3 (%, R$, anos) |
| Hyperlinks proibidos | -15 | Nenhum `<a href>` |
| Word count <700 | -15 | Muito curto |
| Word count 1.500–1.800 | -5 | Aviso |
| Word count 1.800–2.000 | -12 | Aviso forte |
| Word count >2.000 | -25 | Reprovado — trigger self-heal |
| Keyword density fora | -10 | Range 0.5%–4.0% |

---

## Compliance — regras invioláveis

1. **Independência de produtos:** Orbit AI ≠ Meta Ads. Nunca sugerir que anúncios melhoram ranqueamento orgânico.
2. **Zero hyperlinks** no corpo. CTAs apenas em `<strong>`.
3. **Zero JSON-LD / `<script>`** — stripped via código.
4. **PT-BR naturalizado** — sem anglicismos desnecessários.
5. **Sem promessas garantidas** — linguagem de possibilidade.

---

## Adicionando nova vertical — zero código

```bash
# 1. Criar briefing com pesquisa real
echo "# Palavras-chave para detecção: saúde, clínica, médico, plano" > briefings/saude.md
echo "" >> briefings/saude.md
echo "[cole aqui sua pesquisa]" >> briefings/saude.md

# 2. Criar CSV de temas
cat > output_csv_batches_v2/lote_saude_temas.csv << 'EOF'
topic_pt,vertical,category
"AIO para Clínicas: Como aparecer no ChatGPT quando pacientes buscam especialistas",saude,SEO & AIO
EOF

# 3. Adicionar bloco no run_lotes.sh (copie o padrão existente)

# 4. Rodar
./run_lotes.sh
```

### Próximas verticais sugeridas

| Vertical | Keywords-chave |
|---|---|
| Saúde/Clínicas | saúde, clínica, médico, plano, telemedicina |
| Imóveis | imóveis, construtora, lançamento, incorporadora |
| Educação | educação, curso, faculdade, EAD, vestibular |
| Financeiro | fintech, banco, crédito, investimento, seguros |
| Varejo/E-commerce | loja, e-commerce, marketplace, varejo |
| Jurídico | advocacia, jurídico, lei, contrato, LGPD |
| Franquias | franquia, expansão, franqueado |
| Agro | agro, agronegócio, fazenda, produção rural |

---

## Monitoramento

```bash
# Monitor em tempo real
python3 orbit_monitor.py --log relatorios/run_v3_auto.log

# Ver relatório de produção
cat relatorios/report_producao_*.md | tail -100

# Ver relatório de publicação
cat relatorios/report_publicacao_*.md

# Status dos CSVs gerados
python3 -c "
import pandas as pd, glob
for f in glob.glob('output_csv_batches_v2/lote_*batch*.csv'):
    df = pd.read_csv(f)
    pub = (df['post_status']=='published').sum()
    img = df['img_blog'].notna().sum()
    sc = df['qa_score'].mean()
    print(f'{f.split(\"/\")[-1]}: {len(df)} artigos | pub={pub} | img={img} | score={sc:.0f}')
"
```

---

## Troubleshooting

| Problema | Causa | Solução |
|---|---|---|
| `400 Bad Request` OpenRouter | Nome de modelo errado | Verificar com `/api/v1/models` |
| `⚠️ sem imagem` no publisher | URL não encontrada na lib WP | Checar nomenclatura na biblioteca |
| Score QA 65 sem melhorar | Word count >2.000 ou FAQ sem `faq-section` | Ver HTML gerado |
| CSV sobrescrito | Bug — nome duplicado | Na v3 o nome inclui stem do lote |
| JSON-LD no artigo | Regressão | Verificar `parse_response()` |

---

<div align="center">

**Orbit AI v3** — Sowads Agência, 2026 · Produto interno — não distribuir

</div>
