#!/usr/bin/env python3
"""
benchmark.py — Teste comparativo de modelos de IA para geração de artigos SEO.

Completamente desacoplado do pipeline principal. Não modifica nenhum arquivo de produção.

Uso:
  python3 tools/benchmark.py
  python3 tools/benchmark.py --workers 3
  python3 tools/benchmark.py --models gemini-flash,deepseek-flash,qwen3
  python3 tools/benchmark.py --topics "Tema 1" "Tema 2" "Tema 3"

Saída:
  output/testes/<model_slug>/artigo_01.html
  output/testes/<model_slug>/artigo_02.html
  output/testes/<model_slug>/artigo_03.html
  output/testes/<model_slug>/resultado.json
  output/testes/relatorio.html       ← comparativo visual de todos os modelos
"""
import os, sys, re, json, time, threading, argparse, unicodedata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("Instale requests: pip install requests")
    sys.exit(1)

# ── Caminhos (independentes do engine) ──────────────────────────────────────
_HERE     = os.path.dirname(os.path.abspath(__file__))
BASE_DIR  = os.path.dirname(_HERE)
OUT_DIR   = os.path.join(BASE_DIR, "output", "testes")
CLIENT    = os.path.join(BASE_DIR, "client")
ENV_FILE  = os.path.join(BASE_DIR, ".env")

OPENROUTER_URL  = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_SITE = "https://accesstage.com.br"
OPENROUTER_APP  = "Sowads Orbit Benchmark"
MAX_WALL_SECS   = 240   # hard limit por chamada

# ── Modelos para testar ──────────────────────────────────────────────────────
# Chave = alias curto (--models na CLI), valor = ID completo OpenRouter
ALL_MODELS = {
    # Google — série 3.x (2026)
    "gemini-3.1-pro":         "google/gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite":  "google/gemini-3.1-flash-lite-preview",
    "gemini-3-flash":         "google/gemini-3-flash-preview",
    # Google — série 2.x
    "gemini-2.5-pro":         "google/gemini-2.5-pro",
    "gemini-2.5-flash":       "google/gemini-2.5-flash",
    "gemini-2.5-flash-lite":  "google/gemini-2.5-flash-lite",
    "gemini-2.0-flash":       "google/gemini-2.0-flash-001",
    "gemini-2.0-flash-lite":  "google/gemini-2.0-flash-lite-001",
    # Anthropic
    "claude-opus-4.7":        "anthropic/claude-opus-4.7",
    "claude-opus-4.6":        "anthropic/claude-opus-4.6",
    "claude-sonnet-4.6":      "anthropic/claude-sonnet-4.6",
    "claude-sonnet-4.5":      "anthropic/claude-sonnet-4.5",
    "claude-sonnet-4":        "anthropic/claude-sonnet-4",
    "claude-opus-4":          "anthropic/claude-opus-4",
    "claude-haiku-4.5":       "anthropic/claude-haiku-4.5",
    "claude-3.5-haiku":       "anthropic/claude-3.5-haiku",
    # OpenAI — GPT-5.x (versões recentes 2026)
    "gpt-5.5":                "openai/gpt-5.5",
    "gpt-5.4":                "openai/gpt-5.4",
    "gpt-5.4-mini":           "openai/gpt-5.4-mini",
    "gpt-5.4-nano":           "openai/gpt-5.4-nano",
    "gpt-5.2":                "openai/gpt-5.2",
    "gpt-5.1":                "openai/gpt-5.1",
    # OpenAI — GPT-5 base
    "gpt-5-chat":             "openai/gpt-5-chat",
    "gpt-5-mini":             "openai/gpt-5-mini",
    "gpt-5-nano":             "openai/gpt-5-nano",
    # OpenAI — reasoning
    "o4-mini":                "openai/o4-mini",
    "o3":                     "openai/o3",
    "o3-mini":                "openai/o3-mini",
    # OpenAI — GPT-4o
    "gpt-4o":                 "openai/gpt-4o",
    "gpt-4o-mini":            "openai/gpt-4o-mini",
    # Meta Llama 4
    "llama-4-maverick":       "meta-llama/llama-4-maverick",
    "llama-4-scout":          "meta-llama/llama-4-scout",
    "llama-3.3-70b":          "meta-llama/llama-3.3-70b-instruct",
    # DeepSeek
    "deepseek-v4-pro":        "deepseek/deepseek-v4-pro",
    "deepseek-v4-flash":      "deepseek/deepseek-v4-flash",
    "deepseek-r1-0528":       "deepseek/deepseek-r1-0528",
    "deepseek-r1":            "deepseek/deepseek-r1",
    "deepseek-v3":            "deepseek/deepseek-chat-v3-0324",
    # Qwen
    "qwen3-235b":             "qwen/qwen3-235b-a22b-2507",
    "qwen3-32b":              "qwen/qwen3-32b",
    "qwq-32b":                "qwen/qwq-32b",
    # Outros
    "kimi-k2":                "moonshotai/kimi-k2",
    "minimax-m1":             "minimax/minimax-m1",
    "mimo-v2-flash":          "xiaomi/mimo-v2-flash",
    "mimo-v2.5-pro":          "xiaomi/mimo-v2.5-pro",
    "mistral-large":          "mistralai/mistral-large",
}

PRICING = {
    # Google 3.x
    "google/gemini-3.1-pro-preview":        (2.00,  12.00),
    "google/gemini-3.1-flash-lite-preview": (0.25,   1.50),
    "google/gemini-3-flash-preview":        (0.50,   3.00),
    # Google 2.x
    "google/gemini-2.5-pro":                (1.25,  10.00),
    "google/gemini-2.5-flash":              (0.30,   2.50),
    "google/gemini-2.5-flash-lite":         (0.10,   0.40),
    "google/gemini-2.0-flash-001":          (0.10,   0.40),
    "google/gemini-2.0-flash-lite-001":     (0.075,  0.30),
    # Anthropic
    "anthropic/claude-opus-4.7":            (5.00,  25.00),
    "anthropic/claude-opus-4.6":            (5.00,  25.00),
    "anthropic/claude-sonnet-4.6":          (3.00,  15.00),
    "anthropic/claude-sonnet-4.5":          (3.00,  15.00),
    "anthropic/claude-sonnet-4":            (3.00,  15.00),
    "anthropic/claude-opus-4":              (15.00, 75.00),
    "anthropic/claude-haiku-4.5":           (1.00,   5.00),
    "anthropic/claude-3.5-haiku":           (0.80,   4.00),
    # OpenAI GPT-5.x
    "openai/gpt-5.5":                       (5.00,  30.00),
    "openai/gpt-5.4":                       (2.50,  15.00),
    "openai/gpt-5.4-mini":                  (0.75,   4.50),
    "openai/gpt-5.4-nano":                  (0.20,   1.25),
    "openai/gpt-5.2":                       (1.75,  14.00),
    "openai/gpt-5.1":                       (1.25,  10.00),
    "openai/gpt-5-chat":                    (1.25,  10.00),
    "openai/gpt-5-mini":                    (0.25,   2.00),
    "openai/gpt-5-nano":                    (0.05,   0.40),
    # OpenAI reasoning
    "openai/o4-mini":                       (1.10,   4.40),
    "openai/o3":                            (2.00,   8.00),
    "openai/o3-mini":                       (1.10,   4.40),
    # OpenAI GPT-4o
    "openai/gpt-4o":                        (2.50,  10.00),
    "openai/gpt-4o-mini":                   (0.15,   0.60),
    # Meta
    "meta-llama/llama-4-maverick":          (0.15,   0.60),
    "meta-llama/llama-4-scout":             (0.08,   0.30),
    "meta-llama/llama-3.3-70b-instruct":    (0.10,   0.32),
    # DeepSeek
    "deepseek/deepseek-v4-pro":             (0.435,  0.87),
    "deepseek/deepseek-v4-flash":           (0.14,   0.28),
    "deepseek/deepseek-r1-0528":            (0.50,   2.15),
    "deepseek/deepseek-r1":                 (0.70,   2.50),
    "deepseek/deepseek-chat-v3-0324":       (0.20,   0.77),
    # Qwen
    "qwen/qwen3-235b-a22b-2507":            (0.071,  0.10),
    "qwen/qwen3-32b":                       (0.08,   0.24),
    "qwen/qwq-32b":                         (0.15,   0.58),
    # Outros
    "moonshotai/kimi-k2":                   (0.57,   2.30),
    "minimax/minimax-m1":                   (0.40,   2.20),
    "xiaomi/mimo-v2-flash":                 (0.09,   0.29),
    "xiaomi/mimo-v2.5-pro":                 (1.00,   3.00),
    "mistralai/mistral-large":              (2.00,   6.00),
}

# 3 tópicos fixos para benchmark (mesmos para todos os modelos = comparação justa)
BENCHMARK_TOPICS = [
    "Centralização e Controle: Os Pilares de um Software Financeiro Eficiente",
    "Van Bancária e Padrão CNAB: Segurança e Agilidade na Troca de Arquivos Financeiros",
    "Cash Pooling: Maximizando a Eficiência da Tesouraria e a Centralização de Recursos",
]

_lock = threading.Lock()

def tprint(*a, **k):
    with _lock:
        print(*a, **k, flush=True)


# ── .env loader simples ──────────────────────────────────────────────────────
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


# ── Carrega contexto do cliente (guia + dossiê) ──────────────────────────────
def load_guia():
    path = os.path.join(CLIENT, "guia_agente.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""

def load_dossie_excerpt(topic):
    path = os.path.join(CLIENT, "dossie_produtos.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    topic_lower = topic.lower()
    anchors = {
        "### 1.1": ["contas a pagar", "pagamento", "comprovante", "autorização"],
        "### 1.2": ["tesouraria", "extrato", "saldo", "multibanco", "tarifas"],
        "### 1.3": ["crédito", "antecipação", "recebíveis", "risco sacado", "capital de giro"],
        "### 1.4": ["analytics", "dados preditivos", "relatório", "dashboard", "planejamento"],
        "## 2.":   ["edi", "api", "open finance", "van bancária", "cnab", "integração", "baas"],
        "## 3.":   ["cash pooling"],
    }
    best = None
    for anchor, kws in anchors.items():
        if any(kw in topic_lower for kw in kws):
            best = anchor
            break
    if best:
        idx = content.find(best)
        if idx >= 0:
            return content[idx:idx+2000]
    return content[:2000]


# ── Prompt builder ───────────────────────────────────────────────────────────
def build_prompt(topic, guia, dossie):
    ctx_parts = []
    if guia:
        ctx_parts.append(f"### GUIA DO AGENTE (tom, keywords, blacklist)\n{guia[:3500]}")
    if dossie:
        ctx_parts.append(f"### CONTEXTO DO PRODUTO\n{dossie}")
    ctx_block = "\n\n".join(ctx_parts)

    return f"""Você é um especialista em SEO e AIO para o blog da Accesstage (fintech B2B).
Escreva um artigo completo em português brasileiro sobre o tema abaixo.

{ctx_block}

## TEMA DO ARTIGO
{topic}

## REQUISITOS TÉCNICOS OBRIGATÓRIOS
- Estrutura HTML pura: <h2>, <h3>, <p>, <ul>, <li>, <table>, <strong>
- NÃO inclua: <h1>, <img>, <figure>, <a href>, JSON-LD, markdown (** ou ##)
- Word count: 1.100 a 1.500 palavras
- Seção FAQ obrigatória ao final: <section class="faq-section"> com 5 perguntas/respostas
- Inclua pelo menos 1 tabela comparativa relevante
- Tom: técnico, consultivo, direto — voltado para CFOs e tesoureiros B2B
- NÃO cite concorrentes. NÃO use referências numéricas com fontes.
- Meta title (max 60 chars) e meta description (max 160 chars) ao final do artigo, neste formato:
  META_TITLE: ...
  META_DESC: ...

## ANTI-CACOETES DE IA — ESTILO OBRIGATÓRIO
- PROIBIDO usar travessão (—) como recurso estilístico recorrente
- PROIBIDO iniciar parágrafos com: "No entanto,", "Além disso,", "Portanto,", "Vale ressaltar que", "É importante destacar", "Em suma,", "Isso posto,", "Nesse sentido,", "Sendo assim,"
- PROIBIDO aberturas genéricas: "Neste artigo, vamos explorar...", "Neste conteúdo, abordaremos...", "Ao longo deste texto..."
- Varie o comprimento das frases — misture curtas e longas naturalmente
- Use voz ativa preferencialmente
- Conclua seções com argumento concreto, não com resumo do que acabou de ser dito
- Escreva como um especialista humano escreveria: direto, específico, sem floreios artificiais

Escreva APENAS o conteúdo HTML do artigo, começando com <article>."""


# ── QA mínimo (sem dependência do engine) ───────────────────────────────────
def qa_check(html: str) -> dict:
    issues = []
    text   = re.sub(r"<[^>]+>", " ", html)
    words  = len(text.split())

    if words < 700:
        issues.append(f"Word count baixo ({words}w)")
    if words > 2000:
        issues.append(f"Word count alto ({words}w)")
    if re.search(r"<h1", html, re.I):
        issues.append("H1 encontrado no conteúdo")
    if not re.search(r'class=["\']faq-section', html, re.I):
        issues.append("FAQ section ausente")
    if re.search(r"<a\s+href", html, re.I):
        issues.append("Hyperlinks encontrados")
    if re.search(r"\*\*[^*]+\*\*", html):
        issues.append("Markdown ** encontrado")

    h2 = len(re.findall(r"<h2", html, re.I))
    h3 = len(re.findall(r"<h3", html, re.I))
    table = bool(re.search(r"<table", html, re.I))

    penalty = 0
    if words < 700:         penalty += 15
    if words > 2000:        penalty += 25
    if "<h1" in html.lower(): penalty += 10
    if "faq-section" not in html.lower(): penalty += 20
    if re.search(r"<a\s+href", html, re.I): penalty += 15

    score = max(0, 100 - penalty)
    return {
        "score": score, "words": words, "h2": h2, "h3": h3,
        "table": table, "issues": issues
    }


# ── Parser de meta tags ──────────────────────────────────────────────────────
def parse_meta(text: str):
    mt = re.search(r"META_TITLE:\s*(.+)", text)
    md = re.search(r"META_DESC:\s*(.+)", text)
    return (
        mt.group(1).strip() if mt else "",
        md.group(1).strip() if md else ""
    )


# ── Chamada API com wall-clock timeout via streaming ─────────────────────────
def call_api(prompt: str, model: str, api_key: str) -> dict:
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
        "temperature": 0.7,
    }

    t0 = time.time()
    # stream=True + leitura chunk a chunk com verificação de wall-clock total
    # Resolve o bug de modelos que enviam chunks periódicos (DeepSeek, Gemini Pro, Mistral)
    # onde timeout=(10,90) só conta por chunk, nunca dispara total.
    r = requests.post(OPENROUTER_URL, headers=headers, json=payload,
                      timeout=(10, 30), stream=True)
    r.raise_for_status()

    chunks = []
    for chunk in r.iter_content(chunk_size=None):
        if time.time() - t0 > MAX_WALL_SECS:
            raise TimeoutError(f"Wall-clock {MAX_WALL_SECS}s atingido após {time.time()-t0:.0f}s")
        if chunk:
            chunks.append(chunk)

    elapsed = time.time() - t0
    raw = b"".join(chunks).decode("utf-8", errors="replace")

    data = json.loads(raw)
    if "choices" not in data or not data["choices"]:
        err = data.get("error", {}).get("message", str(data)[:100])
        raise ValueError(f"Sem 'choices': {err}")

    text    = data["choices"][0]["message"]["content"]
    usage   = data.get("usage", {})
    tok_in  = usage.get("prompt_tokens",     len(prompt) // 4)
    tok_out = usage.get("completion_tokens", len(text)   // 4)
    return {"text": text, "elapsed": elapsed, "tok_in": tok_in, "tok_out": tok_out}


# ── Custo estimado ───────────────────────────────────────────────────────────
def calc_cost(model_id, tok_in, tok_out):
    p_in, p_out = PRICING.get(model_id, (0, 0))
    return (tok_in / 1_000_000 * p_in) + (tok_out / 1_000_000 * p_out)


# ── Slugify ──────────────────────────────────────────────────────────────────
def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^\w]+", "-", text).strip("-").lower()[:50]


FALLBACK_IMG   = "https://blog.accesstage.com.br/hubfs/ACC_BLOG_CTA-1.png"
TEMPLATE_PATH  = os.path.join(BASE_DIR, "client", "html_template.html")
_template_cache = [None]

def _load_template():
    if _template_cache[0] is None:
        if os.path.exists(TEMPLATE_PATH):
            with open(TEMPLATE_PATH, encoding="utf-8") as f:
                _template_cache[0] = f.read()
        else:
            _template_cache[0] = ""
    return _template_cache[0]


def _reading_time(html):
    words = len(re.sub(r"<[^>]+>", " ", html).split())
    return f"{max(1, round(words / 200))} min."


# ── Salva artigo em HTML com template do blog Accesstage ─────────────────────
def save_article_html(path: str, topic: str, model_id: str, html: str, qa: dict,
                      elapsed: float, tok_in: int, tok_out: int, cost: float,
                      meta_title: str = "", meta_desc: str = ""):
    score_color = "#22c55e" if qa["score"] >= 90 else "#f59e0b" if qa["score"] >= 80 else "#ef4444"
    issues_html = "".join(f"<li style='color:#ef4444'>{i}</li>" for i in qa["issues"]) or "<li style='color:#22c55e'>Sem issues</li>"
    meta_bar = (
        f'<div style="background:#1a0a26;color:#fff;font-family:monospace;font-size:12px;padding:10px 16px;'
        f'display:flex;gap:24px;flex-wrap:wrap;border-bottom:3px solid #dc1668;">'
        f'<span><strong>Modelo:</strong> {model_id}</span>'
        f'<span><strong>QA:</strong> <span style="background:{score_color};color:#fff;padding:1px 8px;border-radius:10px;">'
        f'{qa["score"]}/100</span></span>'
        f'<span><strong>Tempo:</strong> {elapsed:.1f}s</span>'
        f'<span><strong>Tokens:</strong> {tok_in:,} in / {tok_out:,} out</span>'
        f'<span><strong>Custo:</strong> ${cost:.5f}</span>'
        f'<span><strong>Palavras:</strong> {qa["words"]:,}</span>'
        f'<span><strong>Issues:</strong> <ul style="margin:0;padding-left:16px;display:inline">{issues_html}</ul></span>'
        f'</div>'
    )
    notice = (
        f'<div style="background:#442357;color:#fff;text-align:center;padding:10px 16px;font-size:13px;'
        f'font-family:sans-serif;position:sticky;top:0;z-index:9999;">'
        f'<strong>BENCHMARK — {model_id.split("/")[-1]}</strong> &nbsp;|&nbsp; '
        f'Score QA: <span style="background:{score_color};color:#fff;padding:1px 8px;border-radius:10px;">'
        f'{qa["score"]}/100</span> &nbsp;|&nbsp; '
        f'{elapsed:.0f}s &nbsp;|&nbsp; ${cost:.5f} &nbsp;|&nbsp; '
        f'<a href="../relatorio.html" style="color:#db8350;text-decoration:underline;">← Relatório comparativo</a>'
        f'</div>'
    )

    tpl = _load_template()
    if tpl:
        page = tpl
        display_title = meta_title or topic
        # <head>
        page = re.sub(r"(<title>)[^<]*(</title>)", rf"\g<1>{display_title} | Blog Accesstage\g<2>", page, count=1)
        page = re.sub(r'(<meta name="description"\s+content=")[^"]*(")', rf'\g<1>{meta_desc}\g<2>', page, count=1)
        for prop in ["og:title", "twitter:title"]:
            page = re.sub(rf'(<meta (?:property|name)="{prop}"\s+content=")[^"]*(")', rf'\g<1>{display_title}\g<2>', page, count=1)
        for prop in ["og:description", "twitter:description"]:
            page = re.sub(rf'(<meta (?:property|name)="{prop}"\s+content=")[^"]*(")', rf'\g<1>{meta_desc}\g<2>', page, count=1)
        # H1
        page = re.sub(r"(<h1>\s*)[^<]*(</h1>)", rf"\g<1>{topic}\g<2>", page, count=1)
        # Reading time + date
        page = re.sub(r"(<div class=\"post-time\">)[^<]*(</div>)", rf"\g<1>Tempo de leitura: {_reading_time(html)}\g<2>", page, count=1)
        page = re.sub(r'(<div class="post-data">)<span>[^<]*</span>(\s*<span>[^<]*</span>)?(</div>)',
                      rf'\g<1><span>BENCHMARK — {datetime.now().strftime("%d/%m/%Y")}</span>\g<3>', page, count=1)
        # Featured image
        page = re.sub(r'(<div class="post-img">.*?)<img[^>]*>(.*?</div>)',
                      rf'\g<1><img src="{FALLBACK_IMG}" alt="{topic}" class="img-fluid" style="width:100%;height:auto;border-radius:8px;">\g<2>',
                      page, count=1, flags=re.DOTALL)
        # Article body
        page = re.sub(
            r'(<span id="hs_cos_wrapper_post_body"[^>]*>).*?(</span>(?=\s*<div class="post-author">))',
            rf'\g<1>\n{html}\n\g<2>',
            page, count=1, flags=re.DOTALL
        )
        # Remove audio player
        page = re.sub(r'<div id="hs_cos_wrapper_blog_post_audio".*?</div>\s*(?=<span id="hs_cos_wrapper_post_body")',
                      '', page, count=1, flags=re.DOTALL)
        # Inject notice + meta bar after <body>
        page = page.replace("<body>", f"<body>\n{notice}\n{meta_bar}", 1)
    else:
        # Fallback: minimal debug page when template not found
        page = f"""<!doctype html>
<html lang="pt"><head><meta charset="utf-8">
<title>{topic} — {model_id}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:24px;color:#222;line-height:1.6}}
  h2{{color:#442357}} h3{{color:#dc1668}}
  table{{width:100%;border-collapse:collapse;margin:16px 0}}
  th{{background:#442357;color:#fff;padding:8px 12px;text-align:left}}
  td{{padding:8px 12px;border-bottom:1px solid #e5e7eb}}
  .faq-section{{background:#f0f4ff;border-radius:8px;padding:20px;margin-top:24px}}
</style>
</head><body>
{notice}
{meta_bar}
{html}
</body></html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


# ── Gera relatório comparativo HTML ─────────────────────────────────────────
def generate_report(all_results: list):
    # all_results: list of {model_id, model_slug, articles: [{topic, score, elapsed, tok_in, tok_out, cost, words, file}]}
    now = datetime.now().strftime("%d/%m/%Y às %H:%M")

    model_summaries = []
    for mr in all_results:
        arts = [a for a in mr["articles"] if a.get("ok")]
        if not arts:
            continue
        avg_score   = sum(a["score"] for a in arts) / len(arts)
        avg_elapsed = sum(a["elapsed"] for a in arts) / len(arts)
        total_cost  = sum(a["cost"] for a in arts)
        avg_words   = sum(a["words"] for a in arts) / len(arts)
        cost_300    = (total_cost / len(arts)) * 300
        p_in, p_out = PRICING.get(mr["model_id"], (0, 0))
        model_summaries.append({
            **mr,
            "avg_score":   avg_score,
            "avg_elapsed": avg_elapsed,
            "total_cost":  total_cost,
            "cost_300":    cost_300,
            "avg_words":   avg_words,
            "articles":    arts,
            "p_in":        p_in,
            "p_out":       p_out,
        })

    # Sort by avg score desc, then elapsed asc
    model_summaries.sort(key=lambda x: (-x["avg_score"], x["avg_elapsed"]))

    rows = ""
    for ms in model_summaries:
        score_color = "#22c55e" if ms["avg_score"] >= 90 else "#f59e0b" if ms["avg_score"] >= 80 else "#ef4444"
        art_links = " ".join(
            f'<a href="{ms["model_slug"]}/{a["file"]}" style="color:#442357;font-size:12px">Art {i+1} ({a["score"]}/100, {a["elapsed"]:.0f}s)</a>'
            for i, a in enumerate(ms["articles"])
        )
        rows += f"""<tr>
          <td><strong>{ms["model_slug"]}</strong><br><small style="color:#888">{ms["model_id"]}</small></td>
          <td><span style="background:{score_color};color:#fff;padding:2px 10px;border-radius:12px;font-weight:700">{ms["avg_score"]:.0f}/100</span></td>
          <td>{ms["avg_elapsed"]:.1f}s</td>
          <td>${ms["p_in"]:.3f} / ${ms["p_out"]:.3f}</td>
          <td>${ms["total_cost"]:.4f}</td>
          <td>${ms["cost_300"]:.2f}</td>
          <td>{ms["avg_words"]:.0f}w</td>
          <td style="font-size:12px">{art_links}</td>
        </tr>"""

    return f"""<!doctype html>
<html lang="pt"><head><meta charset="utf-8">
<title>Benchmark de Modelos — Sowads Orbit</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{{box-sizing:border-box}}
  body{{font-family:system-ui,sans-serif;background:#f1f6fc;color:#222;margin:0;padding:24px}}
  h1{{color:#442357;margin-bottom:4px}}
  .sub{{color:#888;font-size:14px;margin-bottom:24px}}
  table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
  th{{background:#442357;color:#fff;padding:12px 14px;text-align:left;font-size:13px}}
  td{{padding:12px 14px;border-bottom:1px solid #f0f0f0;vertical-align:top;font-size:13px}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#fafafa}}
  .note{{background:#fff;border-radius:8px;padding:16px;margin-top:20px;font-size:13px;color:#555;border-left:4px solid #442357}}
</style>
</head><body>
<h1>Benchmark de Modelos — Sowads Orbit AI</h1>
<div class="sub">Gerado em {now} | 3 artigos por modelo | Tópicos: Cash Pooling, Van Bancária, Centralização e Controle</div>
<table>
  <thead><tr>
    <th>Modelo</th><th>Score QA (avg)</th><th>Tempo/art</th>
    <th>Preço (in/out /M)</th><th>Custo 3 arts</th>
    <th>Custo 300 arts</th><th>Words (avg)</th><th>Artigos</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="note">
  <strong>Nota:</strong> Score QA avalia estrutura HTML (FAQ, word count, H1, hyperlinks, tabela).
  Não avalia qualidade semântica do conteúdo — leia os artigos individualmente para isso.
  Custo 300 arts é extrapolado a partir da média dos 3 artigos de teste.
</div>
</body></html>"""


# ── Runner principal ─────────────────────────────────────────────────────────
def run_model(model_slug: str, model_id: str, topics: list, api_key: str, guia: str) -> dict:
    # Folder derived from full model ID so name is always unambiguous
    folder_name = model_id.replace("/", "_")
    model_dir = os.path.join(OUT_DIR, folder_name)
    os.makedirs(model_dir, exist_ok=True)

    tprint(f"\n{'='*60}")
    tprint(f"  MODELO: {model_id}  (alias: {model_slug})")
    tprint(f"{'='*60}")

    articles = []
    for i, topic in enumerate(topics, 1):
        pfx = f"[{model_slug}][{i}/{len(topics)}]"
        tprint(f"  {pfx} Tema: {topic[:60]}")
        dossie = load_dossie_excerpt(topic)
        prompt = build_prompt(topic, guia, dossie)

        ctx_info = f"guia ({len(guia):,}c)" if guia else "sem guia"
        if dossie:
            ctx_info += f" | produto ({len(dossie):,}c)"
        tprint(f"  {pfx}[CTX] {ctx_info}")
        tprint(f"  {pfx}[API→] {model_id.split('/')[-1]} | ~{len(prompt):,} chars (~{len(prompt)//4:,} tok)")

        t0 = time.time()
        try:
            res      = call_api(prompt, model_id, api_key)
            elapsed  = res["elapsed"]
            raw_text = res["text"]
            tok_in   = res["tok_in"]
            tok_out  = res["tok_out"]

            tprint(f"  {pfx}[API←] {elapsed:.1f}s | {len(raw_text):,} chars | in:{tok_in} out:{tok_out}")

            # Extrai meta e limpa o texto
            meta_title, meta_desc = parse_meta(raw_text)
            # Remove as linhas de META_ do conteúdo HTML
            html = re.sub(r"META_TITLE:.*", "", raw_text)
            html = re.sub(r"META_DESC:.*",  "", html).strip()

            qa     = qa_check(html)
            cost   = calc_cost(model_id, tok_in, tok_out)

            tprint(f"  {pfx}[QA] {qa['score']}/100 | {qa['words']}w | H2:{qa['h2']} H3:{qa['h3']} | tabela:{'✓' if qa['table'] else '✗'}")
            if qa["issues"]:
                for iss in qa["issues"]:
                    tprint(f"  {pfx}[QA] ⚠ {iss}")
            tprint(f"  {pfx} ✓ Score:{qa['score']}/100 | {elapsed:.0f}s | ${cost:.5f}")

            fname = f"artigo_{i:02d}_{slug(topic)}.html"
            fpath = os.path.join(model_dir, fname)
            save_article_html(fpath, topic, model_id, html, qa, elapsed, tok_in, tok_out, cost, meta_title, meta_desc)

            articles.append({
                "topic": topic, "ok": True, "score": qa["score"],
                "words": qa["words"], "elapsed": elapsed,
                "tok_in": tok_in, "tok_out": tok_out, "cost": cost,
                "meta_title": meta_title, "meta_desc": meta_desc,
                "issues": qa["issues"], "file": fname,
            })

        except Exception as e:
            elapsed = time.time() - t0
            tprint(f"  {pfx} ✗ ERRO em {elapsed:.0f}s: {e}")
            articles.append({"topic": topic, "ok": False, "error": str(e), "elapsed": elapsed,
                             "score": 0, "words": 0, "tok_in": 0, "tok_out": 0, "cost": 0, "issues": [], "file": ""})

    # Salva resultado JSON do modelo
    result = {"model_id": model_id, "model_slug": folder_name, "tested_at": datetime.now().isoformat(), "articles": articles}
    with open(os.path.join(model_dir, "resultado.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    done  = sum(1 for a in articles if a.get("ok"))
    avg_s = sum(a["score"] for a in articles if a.get("ok")) / max(done, 1)
    avg_t = sum(a["elapsed"] for a in articles if a.get("ok")) / max(done, 1)
    tprint(f"  [{folder_name}] CONCLUÍDO: {done}/{len(topics)} artigos | avg score: {avg_s:.0f}/100 | avg tempo: {avg_t:.1f}s")

    return result


def main():
    parser = argparse.ArgumentParser(description="Benchmark de modelos — Sowads Orbit")
    parser.add_argument("--models",  default=None,  help="Modelos a testar, separados por vírgula (ex: gemini-flash,deepseek-v4-flash). Padrão: todos.")
    parser.add_argument("--workers", type=int, default=1, help="Modelos em paralelo (default: 1 — sequencial por segurança)")
    parser.add_argument("--topics",  nargs="*", default=None, help="Tópicos customizados (3 strings)")
    args = parser.parse_args()

    # Carrega API key
    env = load_env()
    api_key = env.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERRO: OPENROUTER_API_KEY não encontrada em .env ou variável de ambiente")
        sys.exit(1)

    # Seleciona modelos
    if args.models:
        chosen_slugs = [m.strip() for m in args.models.split(",")]
        models_to_test = [(s, ALL_MODELS[s]) for s in chosen_slugs if s in ALL_MODELS]
        invalid = [s for s in chosen_slugs if s not in ALL_MODELS]
        if invalid:
            print(f"Modelos inválidos: {invalid}. Disponíveis: {list(ALL_MODELS.keys())}")
    else:
        models_to_test = list(ALL_MODELS.items())

    # Seleciona tópicos
    topics = args.topics if args.topics else BENCHMARK_TOPICS
    topics = topics[:3]  # máximo 3

    os.makedirs(OUT_DIR, exist_ok=True)
    guia = load_guia()

    print(f"\n{'='*60}")
    print(f"  SOWADS ORBIT — BENCHMARK DE MODELOS")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*60}")
    print(f"  Modelos : {len(models_to_test)}")
    print(f"  Tópicos : {len(topics)} por modelo")
    print(f"  Workers : {args.workers} (modelos em paralelo)")
    print(f"  Saída   : {OUT_DIR}")
    print(f"{'='*60}")
    for s, m in models_to_test:
        print(f"  - {s:<22} {m}")
    print()

    all_results = []
    t_total = time.time()

    if args.workers == 1:
        for model_slug, model_id in models_to_test:
            result = run_model(model_slug, model_id, topics, api_key, guia)
            all_results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {
                ex.submit(run_model, slug, mid, topics, api_key, guia): slug
                for slug, mid in models_to_test
            }
            for future in as_completed(futures):
                try:
                    all_results.append(future.result())
                except Exception as e:
                    print(f"Erro no modelo {futures[future]}: {e}")

    # Gera relatório comparativo
    report_html = generate_report(all_results)
    report_path = os.path.join(OUT_DIR, "relatorio.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    elapsed_total = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"  BENCHMARK CONCLUÍDO em {elapsed_total/60:.1f} min")
    print(f"  Relatório: {report_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
