#!/usr/bin/env python3
"""
auditor.py — Auditoria semântica e SEO dos artigos gerados no benchmark.

Usa Gemini 2.5 Pro como avaliador imparcial de conteúdo B2B financeiro.
Os modelos são anonimizados (Modelo A, B, C...) durante a avaliação.
Não modifica nenhum arquivo de produção do Orbit.

Uso:
  python3 tools/auditor.py
  python3 tools/auditor.py --phases fase1,fase2,fase3
  python3 tools/auditor.py --model "openai/gpt-4o"   # avaliador alternativo

Saída:
  output/audit/relatorio_auditoria.html
  output/audit/relatorio_auditoria.md
  output/audit/mapeamento_modelos.json   (revela A→modelo real ao final)
"""
import os, sys, re, json, time, random, threading, argparse
from datetime import datetime

try:
    import requests
except ImportError:
    print("Instale requests: pip install requests"); sys.exit(1)

_HERE      = os.path.dirname(os.path.abspath(__file__))
BASE_DIR   = os.path.dirname(_HERE)
TESTES_DIR = os.path.join(BASE_DIR, "output", "testes")
OUT_DIR    = os.path.join(BASE_DIR, "output", "audit")
ENV_FILE   = os.path.join(BASE_DIR, ".env")

OPENROUTER_URL  = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_SITE = "https://accesstage.com.br"
OPENROUTER_APP  = "Sowads Orbit Auditor"
EVALUATOR_MODEL = "google/gemini-2.5-pro"
MAX_WALL_SECS   = 360   # 6 min — avaliação de 3 artigos pode ser longa

LABELS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

_lock = threading.Lock()
def tprint(*a, **k):
    with _lock:
        print(*a, **k, flush=True)


# ── .env loader ───────────────────────────────────────────────────────────────
def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ── Limpa HTML para avaliação — mantém estrutura semântica intacta ────────────
def clean_article_html(raw_html: str) -> tuple:
    """
    Retorna (meta_bar: str, clean_html: str).
    meta_bar  : texto da barra de auto-avaliação do engine (QA score, modelo, custo)
    clean_html: HTML com scripts/styles/nav/head removidos, todo o conteúdo preservado
    """
    # 1. Captura a barra de meta-info antes de qualquer remoção
    meta_bar = ""
    meta_match = re.search(
        r'<div[^>]*class=["\'][^"\']*(?:meta-bar|notice-bar|benchmark-notice)[^"\']*["\'][^>]*>(.*?)</div>',
        raw_html, re.DOTALL | re.I)
    if meta_match:
        raw_meta = re.sub(r'<[^>]+>', ' ', meta_match.group(1))
        meta_bar = re.sub(r'\s+', ' ', raw_meta).strip()

    # 2. Remove <head>, scripts, styles, noscript
    html = re.sub(r'<head[^>]*>.*?</head>', '', raw_html, flags=re.DOTALL | re.I)
    html = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.I)

    # 3. Remove elementos de navegação/rodapé que não são conteúdo editorial
    html = re.sub(r'<(nav|footer|header)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.I)

    # 4. Comprime whitespace excessivo mas preserva indentação semântica
    html = re.sub(r'\n{4,}', '\n\n', html)
    html = re.sub(r'[ \t]{2,}', ' ', html)

    return meta_bar.strip(), html.strip()


# ── Coleta artigos de todas as fases ─────────────────────────────────────────
def collect_articles(phases: list) -> dict:
    """
    Retorna dict: model_folder → {
        "model_id": str,
        "articles": [{"topic": str, "text": str, "file": str, "score_qa": int}]
    }
    """
    all_models = {}

    def scan_dir(base, prefix=""):
        if not os.path.isdir(base):
            return
        for folder in sorted(os.listdir(base)):
            full = os.path.join(base, folder)
            if not os.path.isdir(full):
                continue
            res_path = os.path.join(full, "resultado.json")
            if not os.path.exists(res_path):
                continue
            with open(res_path, encoding="utf-8") as f:
                resultado = json.load(f)

            articles = []
            for art in resultado.get("articles", []):
                if not art.get("ok") or not art.get("file"):
                    continue
                html_path = os.path.join(full, art["file"])
                if not os.path.exists(html_path):
                    continue
                with open(html_path, encoding="utf-8") as f:
                    raw_html = f.read()
                meta_bar, clean_html = clean_article_html(raw_html)
                if len(clean_html) < 200:
                    continue
                has_faq_schema = bool(re.search(r'class=["\']faq-section["\']', raw_html))
                has_faq_text   = bool(re.search(r'<h[23][^>]*>\s*(perguntas\s+frequentes|faq)', raw_html, re.I))
                articles.append({
                    "topic":          art.get("topic", ""),
                    "html":           clean_html,
                    "meta_bar":       meta_bar,
                    "file":           art["file"],
                    "score_qa":       art.get("score", 0),
                    "words":          art.get("words", 0),
                    "elapsed":        art.get("elapsed", 0),
                    "cost":           art.get("cost", 0),
                    "tok_in":         art.get("tok_in", 0),
                    "tok_out":        art.get("tok_out", 0),
                    "has_faq_schema": has_faq_schema,
                    "has_faq_text":   has_faq_text,
                })

            if articles:
                key = prefix + folder
                all_models[key] = {
                    "model_id": resultado.get("model_id", folder),
                    "articles": articles,
                }

    # Fase 1 (direto em testes/)
    if "fase1" in phases or not phases:
        scan_dir(TESTES_DIR, prefix="")

    # Fases 2 e 3
    for fase in ["fase2", "fase3"]:
        if fase in phases or not phases:
            scan_dir(os.path.join(TESTES_DIR, fase), prefix=f"{fase}/")

    return all_models


# ── Anonimiza modelos ─────────────────────────────────────────────────────────
def anonymize(models: dict) -> tuple:
    """Retorna (anon_map: {label→folder}, reveal_map: {folder→label})"""
    keys = list(models.keys())
    random.shuffle(keys)
    anon_map    = {LABELS[i]: k for i, k in enumerate(keys)}
    reveal_map  = {k: LABELS[i] for i, k in enumerate(keys)}
    return anon_map, reveal_map


# ── Prompt de avaliação por modelo ───────────────────────────────────────────
SYSTEM_PROMPT = """Você é um auditor sênior de conteúdo B2B financeiro, contratado para uma análise forense de qualidade.
Uma empresa de tecnologia financeira brasileira (plataforma de gestão de tesouraria, contas a pagar, conciliação bancária e cash pooling — produto: Veragi da Accesstage) precisa escolher um modelo de IA para gerar artigos de blog voltados a CFOs e tesoureiros.

Você vai avaliar {n_arts} artigos gerados pelo mesmo modelo de IA, identificado apenas como Modelo {label}.
NÃO tente adivinhar qual empresa de IA criou o modelo. Seja absolutamente rigoroso e específico.

═══════════════════════════════════════════════════
CRITÉRIOS DE AVALIAÇÃO — ANÁLISE FORENSE POR ARTIGO
═══════════════════════════════════════════════════

Para CADA artigo, avalie como 3 personas SIMULTÂNEAS:

▶ PERSONA 1 — GERENTE DE MARKETING (peso: 35%)
  • Tom executivo: linguagem de parceiro consultivo, não de vendedor
  • Aberturas: "Em um cenário corporativo...", "No mundo atual...", "Cada vez mais..." = template = penalize
  • CTA: existe Call to Action claro? É contextual ou genérico?
  • Menção à marca Accesstage/Veragi: aparece de forma natural ou forçada? Aparece nos 3 artigos?
  • Metáforas e imagens mentais: o artigo cria memória ou esquece imediatamente?
  • Erros conceituais: qualquer erro técnico que envergonharia a empresa publicamente

▶ PERSONA 2 — CFO/TESOUREIRO (peso: 35%)
  • Profundidade real: o artigo ensina algo ou apenas repete definições de Wikipedia?
  • Legibilidade: parágrafos curtos, bullets, tabelas comparativas onde cabem?
  • Naturalidade em Português-BR: leitura fluida de brasileiro nativo? Sem construções estranhas?
  • Erros de idioma: palavras em espanhol, inglês sem contexto, concordância verbal errada, ortografia
  • O CFO confiaria nesta empresa após ler? O artigo transmite autoridade real?
  • Profundidade técnica: aborda nuances (ex: Cash Pooling físico vs nocional, CNAB 240 vs 400)?

▶ PERSONA 3 — ESPECIALISTA SEO/CRAWLER (peso: 30%)
  • Word count (informe o número exato contado no HTML): ideal 1200-1800 palavras
  • Hierarquia de headings: H2 para seções principais, H3 subordinados, NUNCA H1 no corpo
  • FAQ obrigatório: `<section class="faq-section">` com `<h3>` por pergunta e `<p>` por resposta
    - FAQ ausente = -20 pontos automático
    - FAQ com `<h2>` no título geral = hierarquia quebrada, penalize
    - FAQ com `<strong>` em vez de `<h3>` = não-semântico, perde featured snippets
    - FAQ com `<dl><dt><dd>` = não-semântico para FAQ, penalize
  • Entidades semânticas: CNAB, EDI, VAN Bancária, API Open Finance, BaaS, SWIFT, BACEN, Cash Pooling
  • Meta description: presente? Vazia? Gerada automaticamente?
  • Hyperlinks no corpo: PROIBIDOS neste pipeline — se encontrar, é erro crítico
  • Imagens/figures no HTML: PROIBIDAS neste pipeline — se encontrar, é erro crítico
  • Abertura originalidade: Google valoriza conteúdo que começa de forma única

CHECKLIST HTML OBRIGATÓRIO (inspecione o HTML real recebido):
  ✓ Não há <h1> no corpo do artigo
  ✓ Não há <img> ou <figure> no corpo
  ✓ Não há hyperlinks <a href> no conteúdo
  ✓ Não há JSON-LD nem <script> no conteúdo
  ✓ FAQ usa <section class="faq-section"> com <h3> por pergunta
  ✓ Tabelas são HTML real (<table><tr><td>) — nunca markdown
  ✓ Não há texto em inglês sem contexto, espanhol ou outros idiomas
  ✓ Sem asteriscos **texto** (markdown não renderizado)

ERROS CONCEITUAIS CRÍTICOS A VERIFICAR (cite o texto exato se encontrar):
  • CNAB: "Centro Nacional de Automação Bancária" — não "Comissão" nem outra definição
  • Cash Pooling físico (Zero Balancing): transfere saldo real entre contas
  • Cash Pooling nocional (Notional Pooling): consolida sem mover fundos fisicamente
  • VAN Bancária: "Value Added Network" — intermediário seguro de troca de arquivos
  • EDI: "Electronic Data Interchange" — não confundir com API

═══════════════════════════════════════════════════
FORMATO DE SAÍDA OBRIGATÓRIO POR ARTIGO
═══════════════════════════════════════════════════

Use EXATAMENTE este formato para cada artigo:

---
MODELO {label} — Artigo [N]: [Título completo]

📊 MÉTRICAS OBJETIVAS:
- Palavras: [número exato contado]
- H2 encontrados: [n] | H3 encontrados: [n]
- FAQ: [✓ schema correto / ⚠ presente mas sem schema / ✗ ausente]
- CTA: [✓ presente — cite 1 linha / ✗ ausente]
- Menção Accesstage/Veragi: [✓ natural / ⚠ forçada / ✗ ausente]
- Meta description: [✓ presente / ✗ ausente / ⚠ vazia]
- Erros HTML: [listar problemas específicos encontrados ou "nenhum"]
- Abertura (cite a frase exata de abertura): "[...]"
- Tipo de abertura: [original / template genérico — especifique qual]

🔍 ANÁLISE POR PERSONA:
Marketing [nota/10]: [2-3 frases. Seja específico. Cite o que funcionou e o que falhou.]
Humano/CFO [nota/10]: [2-3 frases. Profundidade real? Português-BR correto? Ensina algo?]
SEO/Crawler [nota/10]: [2-3 frases. Estrutura HTML, entidades, word count, FAQ, originalidade.]

⚠️ PROBLEMAS ENCONTRADOS (seja cirúrgico — cite o texto ou tag exata):
- [Erro 1: descreva + cite trecho ou tag]
- [Erro 2: ...]
- [ou "Nenhum problema crítico encontrado"]

✅ DESTAQUES POSITIVOS:
- [Ponto 1: o que este artigo faz melhor que a média]
- [Ponto 2: ...]

NOTA FINAL DO ARTIGO: [X.X/10]
---

═══════════════════════════════════════════════════
ANÁLISE DE CONSISTÊNCIA INTRA-MODELO — APÓS OS {n_arts} ARTIGOS
═══════════════════════════════════════════════════

## Padrão de Abertura
- Cite a frase de abertura de cada artigo. São iguais/similares ou distintas?
- O modelo clona estrutura entre artigos ou cria identidade própria para cada tema?

## Consistência de Erros
- Algum erro conceitual, cacoete ou problema HTML se repete nos artigos?
- O modelo degrada em temas mais técnicos (Cash Pooling, CNAB, EDI)?

## Consistência de Qualidade
- Notas por artigo: [X.X / X.X / X.X — alta/média/baixa variação]
- Há artigos outlier (um excelente e outros ruins)? Ou produção uniforme?

## Consistência de Tom e Profundidade
- O tom consultivo se mantém em todos os temas?
- Há algum tema onde o modelo claramente perdeu profundidade ou confiança?

## Aptidão para Escala
- Este modelo pode produzir 50+ artigos sem supervisão com qualidade consistente?
- Quais problemas se repetiriam sistematicamente em produção?

RESUMO FINAL DO MODELO {label}:
- Nota média: [X.X/10]  ← média das notas finais dos artigos
- Nota qualidade editorial: [X.X/10]  ← media Marketing + Humano
- Nota indexação SEO: [X.X/10]  ← nota SEO
- Consistência geral: [alta/média/baixa]
- Português-BR: [fluido / aceitável / problemático]
- HTML: [consistente / com falhas pontuais / problemático]
- Aptidão para escala: [sim / com ressalvas / não]
- Caso de uso ideal: [artigos pillar / artigos regulares / conteúdo técnico / alto volume / não recomendado]
- Maior risco em produção: [descreva o problema que mais apareceria em 50+ artigos]
"""

def build_eval_prompt(label: str, model_data: dict) -> str:
    arts = model_data["articles"]
    n_arts = len(arts)
    system = SYSTEM_PROMPT.replace("{label}", label).replace("{n_arts}", str(n_arts))

    avg_elapsed = sum(a.get("elapsed", 0) for a in arts) / max(n_arts, 1)
    total_cost  = sum(a.get("cost", 0) for a in arts)
    avg_words   = sum(a.get("words", 0) for a in arts) / max(n_arts, 1)
    avg_qa      = sum(a.get("score_qa", 0) for a in arts) / max(n_arts, 1)

    perf_block = (
        f"\n{'='*60}\n"
        f"DADOS DE PERFORMANCE — MODELO {label}\n"
        f"{'='*60}\n"
        f"  Velocidade média por artigo : {avg_elapsed:.0f}s\n"
        f"  Custo total dos {n_arts} artigos  : U${total_cost:.4f}\n"
        f"  Custo médio por artigo      : U${total_cost/max(n_arts,1):.4f}\n"
        f"  Palavras médias por artigo  : {avg_words:.0f}\n"
        f"  Score QA técnico médio      : {avg_qa:.0f}/100\n"
        f"{'='*60}\n\n"
        f"ATENÇÃO: O conteúdo abaixo está em HTML semântico.\n"
        f"Inspecione as tags reais — não apenas o texto visível.\n"
        f"A AUTO-AVALIAÇÃO DO ENGINE (barra no topo de cada artigo) é o QA interno\n"
        f"do pipeline de geração — use como referência, não como nota definitiva.\n\n"
    )

    articles_block = ""
    for i, art in enumerate(arts, 1):
        faq_status = "✓ faq-section schema OK" if art.get("has_faq_schema") else (
                     "⚠ FAQ presente mas SEM <section class=faq-section>" if art.get("has_faq_text") else
                     "✗ FAQ AUSENTE — penalize -20pts no score QA")
        meta = art.get("meta_bar", "")
        header = (
            f"\n\n{'='*60}\n"
            f"ARTIGO {i}: {art['topic']}\n"
            f"  Desempenho: {art.get('elapsed',0):.0f}s | U${art.get('cost',0):.4f} | "
            f"{art.get('words',0)} palavras | QA engine: {art.get('score_qa',0)}/100\n"
            f"  FAQ: {faq_status}\n"
        )
        if meta:
            header += f"  AUTO-AVALIAÇÃO DO ENGINE: {meta}\n"
        header += f"{'='*60}\n\n"
        articles_block += header + art["html"] + "\n"

    return system + perf_block + "\nAVALIE OS ARTIGOS HTML ABAIXO:\n" + articles_block


# ── Chamada API com streaming + wall-clock total ──────────────────────────────
def call_api(prompt: str, model: str, api_key: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer":  OPENROUTER_SITE,
        "X-Title":       OPENROUTER_APP,
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       model,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  8000,
        "temperature": 0.3,   # menor temperatura para avaliação mais consistente
    }
    t0 = time.time()
    r = requests.post(OPENROUTER_URL, headers=headers, json=payload,
                      timeout=(10, 30), stream=True)
    r.raise_for_status()

    chunks = []
    for chunk in r.iter_content(chunk_size=None):
        if time.time() - t0 > MAX_WALL_SECS:
            raise TimeoutError(f"Wall-clock {MAX_WALL_SECS}s atingido")
        if chunk:
            chunks.append(chunk)

    raw  = b"".join(chunks).decode("utf-8", errors="replace")
    data = json.loads(raw)
    if "choices" not in data or not data["choices"]:
        err = data.get("error", {}).get("message", str(data)[:200])
        raise ValueError(f"Sem 'choices': {err}")
    return data["choices"][0]["message"]["content"]


# ── Parser de notas da resposta ───────────────────────────────────────────────
_NUM = r"\*{0,2}([0-9]+(?:[.,][0-9]+)?)\*{0,2}"

def parse_scores(text: str) -> list:
    """Extrai nota final de cada artigo."""
    notes = re.findall(r"NOTA FINAL DO ARTIGO[:\s*]+" + _NUM + r"\s*/\s*10", text, re.I)
    return [float(n.replace(",", ".")) for n in notes]

def parse_avg(text: str) -> float:
    """Extrai nota média — aceita bold markdown **X.X/10** ou plain X.X/10."""
    m = re.search(r"Nota m[eé]dia[:\s*]+" + _NUM + r"\s*/\s*10", text, re.I)
    if m:
        return float(m.group(1).replace(",", "."))
    scores = parse_scores(text)
    return round(sum(scores) / len(scores), 1) if scores else 0.0

def parse_editorial(text: str) -> float:
    """Extrai nota qualidade editorial (Marketing + Humano)."""
    m = re.search(r"Nota qualidade editorial[:\s*]+" + _NUM + r"\s*/\s*10", text, re.I)
    if m:
        return float(m.group(1).replace(",", "."))
    # Fallback: média de Marketing e Humano
    mktg = re.findall(r"Marketing\s*\[?([0-9]+(?:[.,][0-9]+)?)\s*/\s*10", text, re.I)
    human = re.findall(r"Humano[/\w]*\s*\[?([0-9]+(?:[.,][0-9]+)?)\s*/\s*10", text, re.I)
    vals = [float(v.replace(",", ".")) for v in mktg + human]
    return round(sum(vals) / len(vals), 1) if vals else 0.0

def parse_seo(text: str) -> float:
    """Extrai nota indexação SEO."""
    m = re.search(r"Nota indexa[çc][aã]o SEO[:\s*]+" + _NUM + r"\s*/\s*10", text, re.I)
    if m:
        return float(m.group(1).replace(",", "."))
    seo = re.findall(r"SEO[/\w]*\s*\[?([0-9]+(?:[.,][0-9]+)?)\s*/\s*10", text, re.I)
    vals = [float(v.replace(",", ".")) for v in seo]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


# ── Prompt de ranking final ───────────────────────────────────────────────────
def build_ranking_prompt(evaluations: dict, anon_map: dict, all_models: dict) -> str:
    # Tabela de dados objetivos por modelo (custo, velocidade, palavras, QA)
    perf_table = "\nTABELA DE PERFORMANCE OBJETIVA (dados reais de geração):\n"
    perf_table += f"{'Modelo':<12} {'ID real':<45} {'Nota':<6} {'Editorial':<10} {'SEO':<6} {'Vel(s)':<8} {'U$/art':<10} {'Palavras':<10} {'QA'}\n"
    perf_table += "-" * 115 + "\n"

    for label in sorted(evaluations.keys()):
        ev     = evaluations[label]
        folder = anon_map.get(label, "")
        mid    = ev.get("model_id", folder)
        arts   = all_models.get(folder, {}).get("articles", [])
        avg_elapsed = sum(a.get("elapsed", 0) for a in arts) / max(len(arts), 1)
        cost_art    = sum(a.get("cost", 0) for a in arts) / max(len(arts), 1)
        avg_words   = sum(a.get("words", 0) for a in arts) / max(len(arts), 1)
        avg_qa      = sum(a.get("score_qa", 0) for a in arts) / max(len(arts), 1)
        avg   = ev.get("avg_score", 0)
        ed    = ev.get("editorial_score", 0)
        seo   = ev.get("seo_score", 0)
        perf_table += f"Modelo {label:<5} {mid:<45} {avg:<6.1f} {ed:<10.1f} {seo:<6.1f} {avg_elapsed:<8.0f} {cost_art:<10.5f} {avg_words:<10.0f} {avg_qa:.0f}\n"

    summary = ""
    for label, ev in sorted(evaluations.items(), key=lambda x: -x[1].get("avg_score", 0)):
        mid  = ev.get("model_id", "")
        avg  = ev.get("avg_score", 0)
        ed   = ev.get("editorial_score", 0)
        seo  = ev.get("seo_score", 0)
        # Pega só o resumo final da resposta (últimas 800 chars) para não sobrecarregar
        resumo = ev["response"][-800:] if len(ev["response"]) > 800 else ev["response"]
        summary += f"\n--- Modelo {label} ({mid}) | avg {avg}/10 | editorial {ed} | SEO {seo} ---\n{resumo}\n"

    return f"""Você é um diretor de conteúdo & tecnologia de uma fintech B2B (Accesstage — plataforma Veragi para CFOs e tesoureiros).
{len(evaluations)} modelos de IA foram avaliados em condições idênticas por um auditor imparcial.
Você tem acesso às avaliações anônimas E aos dados reais de custo, velocidade e qualidade de cada modelo.

PRINCÍPIO CENTRAL: qualidade editorial importa, mas um modelo inviável para escala (>U$0.04/artigo ou >120s) NÃO pode ser o padrão de produção. Recomendações devem equilibrar QUALIDADE × CUSTO × VELOCIDADE.

{perf_table}

RESUMOS DAS AVALIAÇÕES (do melhor para o pior):
{summary}

Gere um RELATÓRIO EXECUTIVO COMPLETO em Markdown, usando os nomes reais dos modelos, com as seções abaixo:

## Metodologia
Explique brevemente as 3 personas (Marketing, CFO/Humano, SEO) e os critérios de avaliação.
Mencione que todos os modelos foram avaliados com HTML real, mesma régua, mesmos 3 temas.

## Tabela Comparativa Completa
Tabela Markdown com TODOS os modelos, ordenada por nota média, colunas:
| # | Modelo | Qualidade | SEO | Média | Vel(s) | U$/artigo | Palavras | QA |

## Análise Detalhada por Modelo
Para CADA modelo (do melhor ao pior), uma seção com:
### [#]. [nome/id] — [nota]/10
**Métricas:** velocidade, custo/artigo, palavras médias, QA
**Pontos fortes:** (bullet list)
**Pontos fracos:** (bullet list, seja específico — cite erros reais da avaliação)
**Veredito:** 1-2 frases diretas. Se custo for inviável para escala, diga explicitamente.

## Modelos Reprovados
Liste com motivo técnico específico (erros conceituais, word count mínimo, HTML quebrado, etc).

## Recomendações por Caso de Uso
Baseado em qualidade E custo/velocidade combinados:
- **Padrão de produção (volume, lotes 50+):** [modelo + justificativa com custo/vel]
- **Artigos pillar e flagship:** [modelo + custo justificado?]
- **Conteúdo técnico (CNAB, EDI, Cash Pooling):** [modelo]
- **Alto volume / escala máxima (300+/dia):** [modelo + custo/vel]
- **Melhor custo-benefício absoluto:** [modelo — nota × custo × vel]

## Problemas Sistêmicos
Erros que apareceram em múltiplos modelos (aberturas template, FAQ sem schema, etc).
Sugestões de correção via prompt engineering para o pipeline.

## Conclusão Executiva
Máximo 6 frases. Modelo para cada função. Seja direto, sem rodeios.
"""


# ── Markdown → HTML renderer ──────────────────────────────────────────────────
def md_to_html(md: str) -> str:
    """Converte Markdown para HTML legível — suporta headings, bold, italic,
    listas, tabelas, código inline, blocos de código e separadores."""
    import html as html_lib

    lines = md.split("\n")
    out = []
    in_ul = False
    in_ol = False
    in_code = False
    in_table = False
    table_buf = []

    def flush_list():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def flush_table():
        nonlocal in_table, table_buf
        if not table_buf:
            return
        rows = table_buf
        table_buf = []
        in_table = False
        html_rows = []
        header_done = False
        for i, row in enumerate(rows):
            if re.match(r"^\|[-| :]+\|$", row.strip()):
                continue
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if not header_done:
                html_rows.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr></thead><tbody>")
                header_done = True
            else:
                html_rows.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
        if header_done:
            html_rows.append("</tbody>")
        out.append('<div class="tbl-wrap"><table>' + "".join(html_rows) + "</table></div>")

    def inline(text: str) -> str:
        text = html_lib.escape(text)
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text

    i = 0
    while i < len(lines):
        line = lines[i]

        # code fence
        if line.strip().startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                flush_list()
                flush_table()
                lang = line.strip()[3:].strip()
                out.append(f'<pre><code class="lang-{lang}">')
                in_code = True
            i += 1
            continue

        if in_code:
            out.append(html_lib.escape(line))
            i += 1
            continue

        # table detection
        if "|" in line and line.strip().startswith("|"):
            flush_list()
            in_table = True
            table_buf.append(line)
            i += 1
            continue
        elif in_table:
            flush_table()

        # horizontal rule
        if re.match(r"^(\*{3,}|-{3,}|_{3,})\s*$", line.strip()):
            flush_list()
            out.append("<hr>")
            i += 1
            continue

        # headings
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush_list()
            level = len(m.group(1)) + 1  # H2-H5 (H1 reservado ao título do relatório)
            level = min(level, 5)
            slug = re.sub(r"[^a-z0-9]+", "-", m.group(2).lower()).strip("-")
            out.append(f'<h{level} id="{slug}">{inline(m.group(2))}</h{level}>')
            i += 1
            continue

        # ordered list
        m = re.match(r"^\s*(\d+)\.\s+(.*)", line)
        if m:
            flush_list() if in_ul else None
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(m.group(2))}</li>")
            i += 1
            continue

        # unordered list
        m = re.match(r"^\s*[-*•]\s+(.*)", line)
        if m:
            flush_list() if in_ol else None
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(m.group(1))}</li>")
            i += 1
            continue

        flush_list()

        if line.strip() == "":
            out.append("<br>")
        else:
            out.append(f"<p>{inline(line)}</p>")
        i += 1

    flush_list()
    flush_table()
    if in_code:
        out.append("</code></pre>")

    return "\n".join(out)


# ── Extrai seção do ranking_text por título ───────────────────────────────────
def _extract_section(text: str, *titles) -> str:
    for title in titles:
        m = re.search(rf"##\s+{re.escape(title)}(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I)
        if m:
            return m.group(1).strip()
    return ""


# ── Gerador de relatório HTML ─────────────────────────────────────────────────
def generate_html_report(evaluations: dict, ranking_text: str,
                         anon_map: dict, all_models: dict) -> str:
    USD_BRL = 5.0
    now = datetime.now().strftime("%d/%m/%Y às %H:%M")
    sorted_evals = sorted(evaluations.items(), key=lambda x: -x[1].get("avg_score", 0))
    n_models = len(evaluations)
    n_arts_total = sum(len(all_models.get(anon_map.get(l,""),{}).get("articles",[])) for l in evaluations)

    # ── Pré-computa métricas por modelo ─────────────────────────────────────
    def model_metrics(label):
        folder = anon_map.get(label, "")
        ev     = evaluations[label]
        arts   = all_models.get(folder, {}).get("articles", [])
        n      = max(len(arts), 1)
        return {
            "model_id":   ev.get("model_id", folder),
            "avg":        ev.get("avg_score", 0),
            "ed":         ev.get("editorial_score", 0),
            "seo":        ev.get("seo_score", 0),
            "elapsed":    sum(a.get("elapsed", 0) for a in arts) / n,
            "cost":       sum(a.get("cost", 0) for a in arts) / n,
            "words":      sum(a.get("words", 0) for a in arts) / n,
            "qa":         sum(a.get("score_qa", 0) for a in arts) / n,
            "faq_ok":     sum(1 for a in arts if a.get("has_faq_schema")),
            "n_arts":     len(arts),
            "response":   ev.get("response", ""),
        }

    metrics = {label: model_metrics(label) for label in evaluations}

    def badge(val, hi=8, mid=6):
        c = "#16a34a" if val >= hi else "#d97706" if val >= mid else "#dc2626"
        return f'<span class="badge" style="background:{c}">{val:.1f}</span>'

    # ── Identifica modelos por caso de uso ──────────────────────────────────
    viable = [(l, m) for l, m in metrics.items()
              if m["avg"] > 0 and not m["response"].startswith("ERRO")]

    def best(candidates, key, reverse=True):
        return sorted(candidates, key=lambda x: key(x[1]), reverse=reverse)[0]

    top_quality   = best(viable, lambda m: m["avg"])
    top_scale     = best([(l,m) for l,m in viable if m["cost"] < 0.04],
                          lambda m: m["avg"])
    top_seo       = best(viable, lambda m: m["seo"])
    top_budget    = best([(l,m) for l,m in viable if m["avg"] >= 5],
                          lambda m: -(m["cost"]+0.00001))
    top_speed     = best([(l,m) for l,m in viable if m["avg"] >= 6],
                          lambda m: -m["elapsed"])

    def use_card(icon, title, label_m, why, accent="#442357"):
        l, m = label_m
        brl  = m["cost"] * 100 * USD_BRL
        return f"""<div class="use-card" style="border-top:4px solid {accent}">
          <div class="use-icon">{icon}</div>
          <div class="use-title">{title}</div>
          <code class="use-model">{m['model_id']}</code>
          <div class="use-scores">
            <span>{m['avg']:.1f}/10 geral</span>
            <span>{m['elapsed']:.0f}s/art</span>
            <span style="font-weight:700">R${brl:.2f}/100</span>
          </div>
          <p class="use-why">{why}</p>
        </div>"""

    use_cards = (
        use_card("🏆", "Máxima Qualidade", top_quality,
                 "Melhor nota geral. Use para conteúdo flagship, estudos de caso e materiais de alto impacto onde o custo é justificado.", "#7c3aed") +
        use_card("⚡", "Padrão de Produção", top_scale,
                 "Melhor equilíbrio entre qualidade e custo viável para lotes. Pode rodar centenas de artigos sem estourar o budget.", "#16a34a") +
        use_card("📈", "Campeão SEO", top_seo,
                 "Maior nota de SEO: hierarquia de headings, FAQ schema, entidades semânticas e originalidade de abertura.", "#0ea5e9") +
        use_card("🚀", "Ultra Rápido", top_speed,
                 "Menor latência entre os modelos com nota aceitável. Ideal para pipelines com SLA de tempo ou pré-visualizações.", "#f59e0b") +
        use_card("💰", "Menor Custo", top_budget,
                 "Custo por artigo mais baixo entre os modelos com nota mínima aceitável. Ideal para alto volume com budget reduzido.", "#64748b")
    )

    # ── Podium top 3 ────────────────────────────────────────────────────────
    def podium_card(rank, m, height):
        brl = m["cost"] * 100 * USD_BRL
        medal = {1:"🥇",2:"🥈",3:"🥉"}[rank]
        viavel = "✅ Viável p/ escala" if m["cost"] < 0.04 else "⚠️ Custo alto p/ volume"
        return f"""<div class="podium-card" style="height:{height}px;align-self:flex-end">
          <div class="podium-medal">{medal}</div>
          <div class="podium-score">{m['avg']:.1f}</div>
          <div class="podium-label">/ 10</div>
          <code class="podium-model">{m['model_id'].split('/')[-1]}</code>
          <div class="podium-meta">
            <span>{m['elapsed']:.0f}s/art</span>
            <span>R${brl:.2f}/100</span>
          </div>
          <div class="podium-viavel">{viavel}</div>
        </div>"""

    top3 = sorted_evals[:3]
    podium_html = (
        podium_card(2, metrics[top3[1][0]], 200) +
        podium_card(1, metrics[top3[0][0]], 240) +
        podium_card(3, metrics[top3[2][0]], 168)
    )

    # ── Insight: padrão atual vs recomendado ────────────────────────────────
    current_id = "google/gemini-2.5-flash"
    current_m  = next((m for m in metrics.values() if m["model_id"] == current_id), None)
    rec_m      = metrics[top_scale[0]]
    insight_html = ""
    if current_m:
        delta_score = rec_m["avg"] - current_m["avg"]
        delta_cost  = (current_m["cost"] - rec_m["cost"]) * 100 * USD_BRL
        delta_speed = current_m["elapsed"] - rec_m["elapsed"]
        insight_html = f"""
        <div class="insight-box">
          <div class="insight-label">⚠️ SEU MODELO ATUAL vs RECOMENDADO</div>
          <div class="insight-grid">
            <div class="insight-col current">
              <div class="insight-tag">Em uso hoje</div>
              <code>{current_id}</code>
              <div class="insight-big">{current_m['avg']:.1f}<span>/10</span></div>
              <div class="insight-subs">
                <span>{current_m['elapsed']:.0f}s/art</span>
                <span>R${current_m['cost']*100*USD_BRL:.2f}/100 arts</span>
              </div>
            </div>
            <div class="insight-arrow">→</div>
            <div class="insight-col recommended">
              <div class="insight-tag">Recomendado</div>
              <code>{rec_m['model_id']}</code>
              <div class="insight-big">{rec_m['avg']:.1f}<span>/10</span></div>
              <div class="insight-subs">
                <span>{rec_m['elapsed']:.0f}s/art</span>
                <span>R${rec_m['cost']*100*USD_BRL:.2f}/100 arts</span>
              </div>
            </div>
            <div class="insight-delta">
              <div class="delta-item {'gain' if delta_score>0 else 'loss'}">
                {'▲' if delta_score>0 else '▼'} {abs(delta_score):.1f} pts na nota
              </div>
              <div class="delta-item {'gain' if delta_cost>0 else 'loss'}">
                {'R$'+f'{abs(delta_cost):.2f}' + ' mais barato' if delta_cost>0 else 'R$'+f'{abs(delta_cost):.2f}'+' mais caro'} / 100 arts
              </div>
              <div class="delta-item {'gain' if delta_speed>0 else 'loss'}">
                {'▲ '+f'{abs(delta_speed):.0f}s mais rápido' if delta_speed>0 else '▼ '+f'{abs(delta_speed):.0f}s mais lento'} / art
              </div>
            </div>
          </div>
        </div>"""

    # ── Problemas sistêmicos ─────────────────────────────────────────────────
    prob_md = _extract_section(ranking_text, "Problemas Sistêmicos", "Problemas sistêmicos",
                               "Problemas Recorrentes", "Padrões de Falha")
    prob_html = md_to_html(prob_md) if prob_md else "<p>Ver avaliações individuais abaixo.</p>"

    # ── Conclusão executiva ──────────────────────────────────────────────────
    conc_md = _extract_section(ranking_text, "Conclusão Executiva", "Conclusão", "Conclusão executiva")
    conc_html = md_to_html(conc_md) if conc_md else ""

    # ── Tabela de ranking ────────────────────────────────────────────────────
    rows = ""
    for rank, (label, ev) in enumerate(sorted_evals, 1):
        m       = metrics[label]
        brl_100 = m["cost"] * 100 * USD_BRL
        spd_c   = "#16a34a" if m["elapsed"] < 20 else "#d97706" if m["elapsed"] < 60 else "#dc2626"
        cost_c  = "#16a34a" if m["cost"] < 0.01 else "#d97706" if m["cost"] < 0.04 else "#dc2626"
        brl_c   = "#16a34a" if brl_100 < 5 else "#d97706" if brl_100 < 20 else "#dc2626"
        faq_c   = "#16a34a" if m["faq_ok"] == m["n_arts"] else "#d97706" if m["faq_ok"] > 0 else "#dc2626"
        medal   = {1:"🥇",2:"🥈",3:"🥉"}.get(rank, f"#{rank}")
        rows += f"""<tr>
          <td class="rank">{medal}</td>
          <td><code class="model-id">{m['model_id']}</code></td>
          <td>{badge(m['avg'])}</td>
          <td>{badge(m['ed'])}</td>
          <td>{badge(m['seo'])}</td>
          <td><span style="color:{spd_c};font-weight:600">{m['elapsed']:.0f}s</span></td>
          <td><span style="color:{cost_c};font-weight:600">U${m['cost']:.5f}</span></td>
          <td><span style="color:{brl_c};font-weight:700">R${brl_100:.2f}</span></td>
          <td>{m['words']:.0f}</td>
          <td>{m['qa']:.0f}</td>
          <td><span style="color:{faq_c};font-weight:600">{m['faq_ok']}/{m['n_arts']}</span></td>
        </tr>"""

    # ── Cards de avaliação individual ────────────────────────────────────────
    cards = ""
    for rank, (label, ev) in enumerate(sorted_evals, 1):
        m        = metrics[label]
        brl_card = m["cost"] * 100 * USD_BRL
        border   = "#16a34a" if m["avg"] >= 8 else "#d97706" if m["avg"] >= 6 else "#dc2626"
        resp_ok  = not m["response"].startswith("ERRO")
        body_html = md_to_html(m["response"]) if resp_ok else f'<p class="err">Erro na avaliação: {m["response"]}</p>'
        slug = m["model_id"].replace("/", "_").replace(".", "-")
        cards += f"""
        <div class="card" id="model-{slug}">
          <div class="card-header" style="border-left:5px solid {border}">
            <div class="card-title">
              <span class="rank-num">#{rank}</span>
              <code class="model-id-lg">{m['model_id']}</code>
            </div>
            <div class="scores-row">
              <span class="score-pill" style="background:{border}">{m['avg']:.1f}/10</span>
              <span class="score-meta">✏️ Editorial {m['ed']:.1f}</span>
              <span class="score-meta">📈 SEO {m['seo']:.1f}</span>
              <span class="score-meta">⚡ {m['elapsed']:.0f}s/art</span>
              <span class="score-meta">💵 U${m['cost']:.5f}/art</span>
              <span class="score-meta">💰 R${brl_card:.2f}/100 arts</span>
              <span class="score-meta">📝 {m['words']:.0f} palavras</span>
            </div>
          </div>
          <div class="card-body">{body_html}</div>
        </div>"""

    # ── Top-10 pontos fortes e atenção ───────────────────────────────────────
    def _t10_card(rank, m):
        brl = m["cost"] * 100 * USD_BRL
        if m["avg"] >= 9.0:
            scenario, s_color = "Artigos Premium / Flagship", "#7c3aed"
        elif m["avg"] >= 8.0 and m["cost"] < 0.01:
            scenario, s_color = "Produção em Escala", "#16a34a"
        elif m["avg"] >= 8.0:
            scenario, s_color = "Alta Qualidade", "#2563eb"
        elif m["seo"] >= 8.0:
            scenario, s_color = "Ranqueamento Orgânico", "#0ea5e9"
        elif m["elapsed"] < 15:
            scenario, s_color = "Volume Rápido / Pipeline", "#f59e0b"
        else:
            scenario, s_color = "Alto Volume / Budget", "#64748b"

        strengths = []
        if m["avg"] >= 9:    strengths.append(f"Nota geral excepcional: {m['avg']:.1f}/10")
        elif m["avg"] >= 8:  strengths.append(f"Qualidade editorial alta: {m['avg']:.1f}/10")
        if m["ed"] >= 8.5:   strengths.append(f"Conteúdo fluido e humano (editorial {m['ed']:.1f})")
        if m["seo"] >= 8.5:  strengths.append(f"SEO semântico dominante: {m['seo']:.1f}/10")
        elif m["seo"] >= 7.5: strengths.append(f"SEO acima da média: {m['seo']:.1f}/10")
        if m["elapsed"] < 12:   strengths.append(f"Ultra-rápido: {m['elapsed']:.0f}s por artigo")
        elif m["elapsed"] < 22: strengths.append(f"Velocidade excelente: {m['elapsed']:.0f}s/artigo")
        if brl < 2:   strengths.append(f"Ultra-barato: R${brl:.2f}/100 artigos")
        elif brl < 6: strengths.append(f"Custo ótimo: R${brl:.2f}/100 artigos")
        if m["faq_ok"] == m["n_arts"] and m["n_arts"] > 0:
            strengths.append("FAQ schema 100% correto em todos os artigos")
        if m["qa"] >= 95: strengths.append(f"QA técnico impecável: {m['qa']:.0f}/100")
        if not strengths: strengths.append("Desempenho consistente para o segmento")

        attention = []
        if brl >= 20:   attention.append(f"Custo proibitivo: R${brl:.2f}/100 arts — inviável para lotes")
        elif brl >= 8:  attention.append(f"Custo relevante: R${brl:.2f}/100 arts — monitorar budget")
        if m["elapsed"] >= 60:  attention.append(f"Muito lento: {m['elapsed']:.0f}s/artigo — não usar em volume")
        elif m["elapsed"] >= 35: attention.append(f"Latência moderada: {m['elapsed']:.0f}s/artigo")
        if m["n_arts"] > 0 and m["faq_ok"] == 0:
            attention.append("FAQ schema ausente — prejudica featured snippets")
        elif m["n_arts"] > 0 and m["faq_ok"] < m["n_arts"]:
            attention.append("FAQ schema inconsistente — nem sempre presente")
        if m["avg"] < 7.5: attention.append("Qualidade editorial abaixo do ideal — revisar antes de publicar")
        if m["ed"] < 7:    attention.append("Tendência a cacoetes de IA — humanização necessária")
        if m["seo"] < 7:   attention.append("SEO semântico fraco — estrutura e entidades precisam atenção")
        if not attention: attention.append("Sem pontos críticos de atenção identificados")

        s_li = "\n".join(f'<li><span class="bul">✓</span>{s}</li>' for s in strengths)
        a_li = "\n".join(f'<li><span class="bul">!</span>{a}</li>' for a in attention)
        medal = {1:"🥇",2:"🥈",3:"🥉"}.get(rank, str(rank))
        return f"""<div class="t10-card">
      <div class="t10-head">
        <div class="t10-rank">{medal}</div>
        <div class="t10-name">{m['model_id']}</div>
        <div class="t10-scenario" style="background:{s_color}">{scenario}</div>
      </div>
      <div class="t10-metrics">
        <span class="t10-metric"><strong>{m['avg']:.1f}/10</strong> geral</span>
        <span class="t10-metric"><strong>{m['ed']:.1f}/10</strong> editorial</span>
        <span class="t10-metric"><strong>{m['seo']:.1f}/10</strong> SEO</span>
        <span class="t10-metric"><strong>{m['elapsed']:.0f}s</strong>/artigo</span>
        <span class="t10-metric"><strong>R${brl:.2f}</strong>/100 arts</span>
        <span class="t10-metric"><strong>{m['words']:.0f}</strong> palavras</span>
      </div>
      <div class="t10-body">
        <div class="t10-col strengths">
          <div class="t10-col-title">Pontos Fortes</div>
          <ul>{s_li}</ul>
        </div>
        <div class="t10-col attention">
          <div class="t10-col-title">Pontos de Atenção</div>
          <ul>{a_li}</ul>
        </div>
      </div>
    </div>"""

    top10_html = "\n".join(
        _t10_card(rank, metrics[label])
        for rank, (label, _) in enumerate(sorted_evals[:10], 1)
        if not metrics[label]["response"].startswith("ERRO")
    )

    # ── TOC sidebar ──────────────────────────────────────────────────────────
    toc_items = '<li><a href="#hero">↑ Topo</a></li>'
    toc_items += '<li><a href="#tabela">Tabela comparativa</a></li>'
    toc_items += '<li><a href="#quando-usar">Quando usar cada um</a></li>'
    toc_items += '<li><a href="#top10">Top 10 detalhado</a></li>'
    toc_items += '<li class="toc-sep">— Análise por modelo —</li>'
    for rank, (label, _) in enumerate(sorted_evals, 1):
        m    = metrics[label]
        slug = m["model_id"].replace("/", "_").replace(".", "-")
        dot_c = "#16a34a" if m["avg"] >= 8 else "#d97706" if m["avg"] >= 6 else "#dc2626"
        short = m["model_id"].split("/")[-1]
        toc_items += f'<li><a href="#model-{slug}"><span class="dot" style="background:{dot_c}"></span>{short} <em>{m["avg"]:.1f}</em></a></li>'

    # ── CSS ──────────────────────────────────────────────────────────────────
    CSS = """
:root{--purple:#3b1f5e;--purple2:#6d28d9;--accent:#7c3aed;--bg:#f4f6fb;--card:#fff;--border:#e5e7eb;--text:#1a1a2e;--muted:#6b7280;--green:#16a34a;--amber:#d97706;--red:#dc2626}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);font-size:20px;line-height:1.75}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
code{background:#f3f0f9;color:#5b21b6;padding:1px 6px;border-radius:4px;font-size:.85em;font-family:'Fira Mono',monospace}
pre{background:#1e1b2e;color:#e2e8f0;padding:16px;border-radius:10px;overflow-x:auto;font-size:17px;margin:12px 0}
pre code{background:none;color:inherit;padding:0}
hr{border:none;border-top:1px solid var(--border);margin:24px 0}
strong{color:var(--text)}

/* Layout */
.layout{display:flex;min-height:100vh}
.sidebar{width:270px;min-width:270px;background:var(--purple);color:#fff;padding:20px 0;position:sticky;top:0;height:100vh;overflow-y:auto;flex-shrink:0}
.sidebar-brand{padding:0 16px 16px;font-size:14px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.4);border-bottom:1px solid rgba(255,255,255,.08);margin-bottom:8px}
.sidebar nav ul{list-style:none}
.sidebar nav li a{display:flex;align-items:center;gap:8px;padding:6px 16px;color:rgba(255,255,255,.8);font-size:15px;transition:background .12s;border-radius:0}
.sidebar nav li a:hover{background:rgba(255,255,255,.1);text-decoration:none;color:#fff}
.sidebar nav li a em{margin-left:auto;font-style:normal;font-weight:700;font-size:14px;opacity:.7}
.toc-sep{padding:10px 16px 2px;font-size:13px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.3)}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;display:inline-block}
.main{flex:1;overflow:hidden}

/* PDF button */
.pdf-btn{position:fixed;bottom:28px;right:28px;z-index:999;background:var(--purple);color:#fff;border:none;border-radius:40px;padding:14px 26px;font-size:18px;font-weight:700;cursor:pointer;box-shadow:0 4px 20px rgba(59,31,94,.45);display:flex;align-items:center;gap:8px;transition:background .15s}
.pdf-btn:hover{background:var(--accent)}

/* HERO */
.hero{background:linear-gradient(135deg,#3b1f5e 0%,#1e0a3c 60%,#0f0a1e 100%);color:#fff;padding:64px 56px 56px;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;top:-40%;right:-10%;width:600px;height:600px;background:radial-gradient(circle,rgba(139,92,246,.25) 0%,transparent 70%);pointer-events:none}
.hero-eyebrow{font-size:14px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:rgba(167,139,250,.8);margin-bottom:16px}
.hero-headline{font-size:62px;font-weight:900;line-height:1.1;margin-bottom:8px;background:linear-gradient(135deg,#fff 30%,#c4b5fd);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero-sub{font-size:23px;color:rgba(255,255,255,.6);margin-bottom:40px;max-width:580px}
.hero-stats{display:flex;gap:32px;flex-wrap:wrap;margin-bottom:48px}
.hero-stat .n{font-size:52px;font-weight:900;color:#fff;line-height:1}
.hero-stat .l{font-size:16px;color:rgba(255,255,255,.5);margin-top:4px;text-transform:uppercase;letter-spacing:.06em}

/* Podium */
.podium{display:flex;align-items:flex-end;gap:12px;margin-top:8px}
.podium-card{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:20px 16px;display:flex;flex-direction:column;align-items:center;gap:6px;min-width:180px;backdrop-filter:blur(8px)}
.podium-medal{font-size:36px;line-height:1}
.podium-score{font-size:52px;font-weight:900;color:#fff;line-height:1}
.podium-label{font-size:17px;color:rgba(255,255,255,.5);margin-top:-4px}
.podium-model{font-size:14px;background:rgba(255,255,255,.1);color:#e9d5ff;padding:3px 8px;border-radius:6px;text-align:center;max-width:160px;word-break:break-all}
.podium-meta{display:flex;gap:8px;font-size:14px;color:rgba(255,255,255,.5);flex-wrap:wrap;justify-content:center}
.podium-viavel{font-size:14px;color:rgba(255,255,255,.6);text-align:center;margin-top:2px}

/* Insight box */
.insight-box{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:28px;margin-top:40px}
.insight-label{font-size:14px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#fbbf24;margin-bottom:20px}
.insight-grid{display:flex;align-items:center;gap:24px;flex-wrap:wrap}
.insight-col{flex:1;min-width:180px}
.insight-tag{font-size:13px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px}
.current .insight-tag{color:rgba(255,255,255,.4)}
.recommended .insight-tag{color:#34d399}
.insight-col code{font-size:16px;background:rgba(255,255,255,.1);color:#e9d5ff;display:block;margin-bottom:8px;padding:4px 8px}
.insight-big{font-size:68px;font-weight:900;color:#fff;line-height:1}
.insight-big span{font-size:26px;color:rgba(255,255,255,.4)}
.insight-subs{display:flex;gap:12px;margin-top:6px;font-size:16px;color:rgba(255,255,255,.5)}
.insight-arrow{font-size:42px;color:rgba(255,255,255,.3);flex-shrink:0}
.insight-delta{display:flex;flex-direction:column;gap:10px;padding:16px;background:rgba(0,0,0,.2);border-radius:12px;min-width:160px}
.delta-item{font-size:17px;font-weight:700;padding:4px 0}
.delta-item.gain{color:#34d399}
.delta-item.loss{color:#f87171}

/* Main content */
.content{padding:48px 56px;max-width:1280px}

/* Sections */
section{margin-bottom:60px}
section > h2{font-size:29px;color:var(--purple);font-weight:800;margin-bottom:4px}
.section-sub{font-size:18px;color:var(--muted);margin-bottom:24px}

/* Use case cards */
.use-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.use-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:24px;display:flex;flex-direction:column;gap:8px;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.use-icon{font-size:36px}
.use-title{font-size:14px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.use-model{font-size:16px;word-break:break-all;padding:4px 8px}
.use-scores{display:flex;gap:10px;font-size:16px;color:var(--muted);flex-wrap:wrap}
.use-why{font-size:17px;color:#4b5563;line-height:1.6;margin-top:4px}

/* Top-10 cards */
.top10-grid{display:grid;grid-template-columns:1fr;gap:20px}
.t10-card{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.t10-head{padding:20px 24px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:#fafafa;border-bottom:1px solid var(--border)}
.t10-rank{font-size:22px;font-weight:900;color:#fff;background:var(--purple);border-radius:10px;width:46px;height:46px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.t10-name{font-size:20px;font-weight:700;color:var(--text);flex:1;word-break:break-all}
.t10-scenario{font-size:14px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:5px 14px;border-radius:20px;color:#fff;white-space:nowrap}
.t10-metrics{display:flex;gap:10px;flex-wrap:wrap;padding:14px 24px;background:#fafafa;border-bottom:1px solid var(--border)}
.t10-metric{font-size:17px;color:var(--muted);background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:5px 14px}
.t10-metric strong{color:var(--text)}
.t10-body{display:grid;grid-template-columns:1fr 1fr}
.t10-col{padding:20px 24px}
.t10-col:first-child{border-right:1px solid var(--border)}
.t10-col-title{font-size:14px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin-bottom:12px}
.t10-col.strengths .t10-col-title{color:var(--green)}
.t10-col.attention .t10-col-title{color:var(--amber)}
.t10-col ul{list-style:none;display:flex;flex-direction:column;gap:8px}
.t10-col li{font-size:18px;color:#374151;display:flex;gap:10px;align-items:flex-start;line-height:1.55}
.t10-col li .bul{flex-shrink:0;margin-top:1px;font-weight:800;font-size:17px}
.t10-col.strengths .bul{color:var(--green)}
.t10-col.attention .bul{color:var(--amber)}

/* Table */
.tbl-wrap{overflow-x:auto;border-radius:12px;border:1px solid var(--border);box-shadow:0 2px 12px rgba(0,0,0,.06)}
table{width:100%;border-collapse:collapse;background:var(--card);font-size:17px}
thead{background:var(--purple)}
thead th{color:#fff;padding:14px 16px;text-align:left;font-weight:600;white-space:nowrap;font-size:14px;letter-spacing:.05em;text-transform:uppercase}
tbody tr:nth-child(even){background:#fafafa}
tbody tr:hover{background:#f5f0ff}
td{padding:13px 16px;border-bottom:1px solid var(--border);vertical-align:middle}
.rank{font-size:23px;text-align:center;width:46px}
.model-id{font-size:14px;background:#f3f0f9;color:#5b21b6;white-space:nowrap}
.badge{color:#fff;padding:3px 10px;border-radius:20px;font-weight:700;font-size:16px;white-space:nowrap}
.legend{display:flex;gap:14px;font-size:16px;color:var(--muted);margin-bottom:14px;flex-wrap:wrap;align-items:center}
.legend span{display:flex;align-items:center;gap:5px}
.legend .dot{width:10px;height:10px}
.legend .sep{color:var(--border)}

/* Systemic issues */
.issues-box{background:var(--card);border:1px solid var(--border);border-left:5px solid var(--amber);border-radius:12px;padding:28px}
.issues-box p{margin-bottom:12px;font-size:18px;color:#374151}
.issues-box ul{margin:8px 0 16px 24px}
.issues-box li{margin-bottom:8px;font-size:18px;color:#374151}
.issues-box h3{font-size:20px;font-weight:700;color:var(--purple);margin:20px 0 10px}
.issues-box h3:first-child{margin-top:0}

/* Conclusion */
.conclusion-box{background:linear-gradient(135deg,#f5f3ff,#ede9fe);border:1px solid #c4b5fd;border-radius:14px;padding:28px}
.conclusion-box p{margin-bottom:12px;font-size:20px;color:#3b1f5e}
.conclusion-box strong{color:#4c1d95}

/* Model cards */
.card{background:var(--card);border-radius:14px;border:1px solid var(--border);margin-bottom:20px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.card-header{padding:20px 26px;background:#fafafa;border-bottom:1px solid var(--border)}
.card-title{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.rank-num{font-size:16px;font-weight:800;color:var(--muted)}
.model-id-lg{font-size:18px;font-weight:700;background:#f3f0f9;color:#4c1d95;padding:4px 12px;border-radius:6px}
.scores-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.score-pill{color:#fff;padding:5px 16px;border-radius:20px;font-weight:800;font-size:20px}
.score-meta{font-size:15px;color:var(--muted);background:var(--bg);border:1px solid var(--border);padding:4px 10px;border-radius:12px;white-space:nowrap}
.card-body{padding:26px;font-size:18px;line-height:1.85;color:#374151}
.card-body h2{font-size:20px;color:var(--purple);margin:22px 0 10px;padding-bottom:4px;border-bottom:1px solid var(--border);font-weight:700}
.card-body h2:first-child{margin-top:0}
.card-body h3{font-size:18px;color:var(--text);margin:16px 0 8px;font-weight:700}
.card-body h4{font-size:17px;color:var(--accent);margin:12px 0 6px;font-weight:600}
.card-body p{margin-bottom:12px}
.card-body ul,.card-body ol{margin:8px 0 14px 24px}
.card-body li{margin-bottom:6px}
.card-body .tbl-wrap{margin:12px 0}
.card-body table{font-size:16px}
.err{color:var(--red);font-weight:600}

@media(max-width:960px){
  .hero{padding:40px 24px}
  .hero-headline{font-size:40px}
  .hero-sub{font-size:19px}
  .content{padding:28px 20px}
  .sidebar{display:none}
  .podium{flex-wrap:wrap}
  .insight-grid{flex-direction:column}
  .t10-body{grid-template-columns:1fr}
  .t10-col:first-child{border-right:none;border-bottom:1px solid var(--border)}
  .pdf-btn{bottom:16px;right:16px;font-size:16px;padding:12px 20px}
}

@media print{
  .sidebar,.pdf-btn{display:none!important}
  .layout{display:block}
  .hero{background:#3b1f5e!important;-webkit-print-color-adjust:exact;print-color-adjust:exact;padding:40px 32px}
  .hero-headline{font-size:38px;-webkit-text-fill-color:#fff!important;background:none!important}
  body{font-size:15px}
  .card,.t10-card{break-inside:avoid;page-break-inside:avoid}
  section{page-break-inside:auto}
  .content{padding:24px 32px}
  .podium-card{break-inside:avoid}
}
"""

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Auditoria de Modelos de IA — Sowads Orbit × Accesstage</title>
  <style>{CSS}</style>
</head>
<body>
<div class="layout">

  <aside class="sidebar">
    <div class="sidebar-brand">Orbit Audit</div>
    <nav><ul>{toc_items}</ul></nav>
  </aside>

  <main class="main">

    <!-- ▸ HERO ─────────────────────────────────────────── -->
    <div class="hero" id="hero">
      <div class="hero-eyebrow">Sowads Orbit × Accesstage · Plataforma Veragi · {now}</div>
      <div class="hero-headline">{n_models} modelos.<br>Um veredicto.</div>
      <div class="hero-sub">Avaliação forense de conteúdo B2B financeiro gerado por IA — HTML real, 3 personas, mesma régua para todos.</div>
      <div class="hero-stats">
        <div class="hero-stat"><div class="n">{n_models}</div><div class="l">Modelos testados</div></div>
        <div class="hero-stat"><div class="n">{n_arts_total}</div><div class="l">Artigos avaliados</div></div>
        <div class="hero-stat"><div class="n">3</div><div class="l">Personas por artigo</div></div>
        <div class="hero-stat"><div class="n">{sum(1 for _,m in metrics.items() if m['avg']>=8)}</div><div class="l">Aprovados ≥8.0</div></div>
        <div class="hero-stat"><div class="n">{sum(1 for _,m in metrics.items() if m['avg']<5)}</div><div class="l">Reprovados &lt;5.0</div></div>
      </div>
      <div class="podium">{podium_html}</div>
      {insight_html}
    </div>

    <div class="content">

      <!-- ▸ TABELA ─────────────────────────────────────── -->
      <section id="tabela">
        <h2>Tabela comparativa — {n_models} modelos</h2>
        <div class="section-sub">Visão geral de todos os modelos testados. Verde = excelente, âmbar = aceitável, vermelho = atenção.</div>
        <div class="legend">
          <span><span class="dot" style="background:#16a34a"></span>Nota ≥8</span>
          <span><span class="dot" style="background:#d97706"></span>6–7.9</span>
          <span><span class="dot" style="background:#dc2626"></span>&lt;6</span>
          <span class="sep">|</span>
          <span><span class="dot" style="background:#16a34a"></span>Vel &lt;20s</span>
          <span><span class="dot" style="background:#d97706"></span>20–60s</span>
          <span><span class="dot" style="background:#dc2626"></span>≥60s</span>
          <span class="sep">|</span>
          <span><span class="dot" style="background:#16a34a"></span>R$ &lt;5/100 arts</span>
          <span><span class="dot" style="background:#d97706"></span>R$5–20</span>
          <span><span class="dot" style="background:#dc2626"></span>&gt;R$20</span>
          <em style="color:var(--muted);font-size:14px">(USD 1 = R$5,00)</em>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead>
              <tr><th>#</th><th>Modelo</th><th>Média</th><th>Editorial</th><th>SEO</th>
              <th>Velocidade</th><th>U$/art</th><th>R$/100 arts</th><th>Palavras</th><th>QA</th><th>FAQ</th></tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
      </section>

      <!-- ▸ QUANDO USAR ─────────────────────────────────── -->
      <section id="quando-usar">
        <h2>Quando usar cada um</h2>
        <div class="section-sub">Recomendações por cenário — qualidade editorial + custo + velocidade ponderados juntos, não apenas nota bruta.</div>
        <div class="use-grid">{use_cards}</div>
        {f'<div class="issues-box" style="margin-top:28px"><h3>Conclusão executiva</h3>{conc_html}</div>' if conc_html else ''}
      </section>

      <!-- ▸ TOP 10 DETALHADO ────────────────────────────── -->
      <section id="top10">
        <h2>Top 10 — Pontos fortes e de atenção</h2>
        <div class="section-sub">Para cada um dos 10 melhores modelos: cenário ideal de uso, o que brilha e o que monitorar antes de escalar.</div>
        <div class="top10-grid">{top10_html}</div>
      </section>

      <!-- ▸ PROBLEMAS SISTÊMICOS ────────────────────────── -->
      <section>
        <h2>Problemas sistêmicos detectados</h2>
        <div class="section-sub">Padrões ruins que aparecem em múltiplos modelos — oportunidades de correção via prompt engineering.</div>
        <div class="issues-box">{prob_html}</div>
      </section>

      <!-- ▸ AVALIAÇÕES INDIVIDUAIS ──────────────────────── -->
      <section>
        <h2>Avaliações individuais por modelo</h2>
        <div class="section-sub">Análise forense detalhada — HTML real, erros citados com precisão, consistência intra-modelo.</div>
        {cards}
      </section>

    </div>
  </main>
</div>

<button class="pdf-btn" onclick="window.print()">⬇ Salvar PDF</button>

</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Auditor semântico — Sowads Orbit")
    parser.add_argument("--phases",  default="fase1,fase2,fase3", help="Fases a incluir (default: todas)")
    parser.add_argument("--model",   default=EVALUATOR_MODEL, help=f"Modelo avaliador (default: {EVALUATOR_MODEL})")
    parser.add_argument("--limit",   type=int, default=0, help="Limitar a N modelos (para testes)")
    parser.add_argument("--seed",    type=int, default=42, help="Seed para anonimização reproduzível")
    parser.add_argument("--resume",  action="store_true", help="Retoma avaliações parciais salvas")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERRO: OPENROUTER_API_KEY não encontrada"); sys.exit(1)

    phases = [p.strip() for p in args.phases.split(",")]
    evaluator = args.model

    os.makedirs(OUT_DIR, exist_ok=True)
    random.seed(args.seed)

    print(f"\n{'='*65}")
    print(f"  SOWADS ORBIT — AUDITORIA SEMÂNTICA DE CONTEÚDO")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"  Avaliador: {evaluator}")
    print(f"  Fases: {', '.join(phases)}")
    print(f"{'='*65}\n")

    # Coleta artigos
    all_models = collect_articles(phases)
    if not all_models:
        print("Nenhum artigo encontrado. Verifique output/testes/"); sys.exit(1)

    if args.limit:
        all_models = dict(list(all_models.items())[:args.limit])

    print(f"  Modelos encontrados: {len(all_models)}")
    total_arts = sum(len(m["articles"]) for m in all_models.values())
    print(f"  Artigos encontrados: {total_arts}")

    # Anonimiza
    anon_map, reveal_map = anonymize(all_models)
    print(f"\n  Anonimização (não revelar durante avaliação):")
    for label, folder in sorted(anon_map.items()):
        mid = all_models[folder]["model_id"]
        print(f"    Modelo {label} → {mid}")

    # Salva mapeamento
    mapping = {label: {"folder": folder, "model_id": all_models[folder]["model_id"]}
               for label, folder in anon_map.items()}
    with open(os.path.join(OUT_DIR, "mapeamento_modelos.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    # Carrega avaliações parciais se --resume
    partial_path = os.path.join(OUT_DIR, "avaliacoes_parciais.json")
    evaluations = {}
    if args.resume and os.path.exists(partial_path):
        with open(partial_path, encoding="utf-8") as f:
            evaluations = json.load(f)
        print(f"\n  --resume: {len(evaluations)} avaliações já carregadas")

    # Avalia cada modelo
    for label in sorted(anon_map.keys()):
        if label not in [LABELS[i] for i in range(len(all_models))]:
            continue
        folder     = anon_map[label]
        model_data = all_models[folder]
        n_arts     = len(model_data["articles"])

        if label in evaluations and not evaluations[label]["response"].startswith("ERRO"):
            tprint(f"[{label}] ↩ pulando (já avaliado) — {evaluations[label]['model_id']}")
            continue

        tprint(f"\n[{label}] Avaliando {model_data['model_id']} — {n_arts} artigos")

        prompt  = build_eval_prompt(label, model_data)
        t0 = time.time()
        try:
            response  = call_api(prompt, evaluator, api_key)
            elapsed   = time.time() - t0
            avg       = parse_avg(response)
            editorial = parse_editorial(response)
            seo       = parse_seo(response)
            tprint(f"[{label}] ✓ {elapsed:.0f}s | média: {avg}/10 | editorial: {editorial} | SEO: {seo}")
            evaluations[label] = {
                "model_id":       model_data["model_id"],
                "response":       response,
                "avg_score":      avg,
                "editorial_score": editorial,
                "seo_score":      seo,
                "elapsed":        elapsed,
            }
        except Exception as e:
            elapsed = time.time() - t0
            tprint(f"[{label}] ✗ ERRO em {elapsed:.0f}s: {e}")
            evaluations[label] = {
                "model_id":  model_data["model_id"],
                "response":  f"ERRO: {e}",
                "avg_score": 0,
                "elapsed":   elapsed,
            }

        # Salva parcial após cada modelo
        with open(os.path.join(OUT_DIR, "avaliacoes_parciais.json"), "w", encoding="utf-8") as f:
            json.dump(evaluations, f, ensure_ascii=False, indent=2)

    # Ranking final
    tprint(f"\n{'='*65}")
    tprint("  GERANDO RELATÓRIO EXECUTIVO FINAL...")
    tprint(f"{'='*65}")
    ranking_prompt = build_ranking_prompt(evaluations, anon_map, all_models)
    try:
        ranking_text = call_api(ranking_prompt, evaluator, api_key)
    except Exception as e:
        ranking_text = f"Erro ao gerar ranking: {e}"

    # Gera relatório HTML
    html_report = generate_html_report(evaluations, ranking_text, anon_map, all_models)
    html_path   = os.path.join(OUT_DIR, "relatorio_auditoria.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)

    # Gera markdown — relatório executivo é o conteúdo principal
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    n_models = len(evaluations)
    n_arts_total = sum(len(all_models.get(anon_map.get(l,""),{}).get("articles",[])) for l in evaluations)

    md_header = (
        f"# Auditoria de Conteúdo — Sowads Orbit × Accesstage\n\n"
        f"> Gerado em {now_str} | Avaliador: `{evaluator}` | "
        f"{n_models} modelos | {n_arts_total} artigos avaliados\n\n"
        f"---\n\n"
    )

    # Avaliações individuais detalhadas (apêndice)
    apendice = "\n\n---\n\n# Apêndice — Avaliações Individuais por Modelo\n\n"
    for label, ev in sorted(evaluations.items(), key=lambda x: -x[1].get("avg_score", 0)):
        mid = ev.get("model_id", "")
        avg = ev.get("avg_score", 0)
        folder = anon_map.get(label, "")
        arts   = all_models.get(folder, {}).get("articles", [])
        cost_art    = sum(a.get("cost", 0) for a in arts) / max(len(arts), 1)
        avg_elapsed = sum(a.get("elapsed", 0) for a in arts) / max(len(arts), 1)
        avg_words   = sum(a.get("words", 0) for a in arts) / max(len(arts), 1)
        apendice += (
            f"## {mid} — {avg:.1f}/10\n\n"
            f"**Métricas:** {avg_elapsed:.0f}s/artigo | U${cost_art:.5f}/artigo | {avg_words:.0f} palavras médias\n\n"
            f"{ev['response']}\n\n---\n\n"
        )

    md_path = os.path.join(OUT_DIR, "relatorio_auditoria.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_header + ranking_text + apendice)

    print(f"\n{'='*65}")
    print(f"  AUDITORIA CONCLUÍDA")
    print(f"  HTML:     {html_path}")
    print(f"  Markdown: {md_path}")
    print(f"  Mapa:     {os.path.join(OUT_DIR, 'mapeamento_modelos.json')}")
    print(f"{'='*65}\n")

    print("\nRANKING FINAL:")
    for label, ev in sorted(evaluations.items(), key=lambda x: -x[1].get("avg_score", 0)):
        print(f"  Modelo {label}: {ev['avg_score']:.1f}/10 — {ev['model_id']}")


if __name__ == "__main__":
    main()
