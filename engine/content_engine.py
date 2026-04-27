import os
import sys
import csv
import json
import time
import re
import glob
import argparse
import warnings
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pandas as pd

# Resolve project root so this script works from any CWD
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engine.publisher import CATEGORY_KEYWORDS, FALLBACK_CATEGORY
from engine.media_indexer import load_index, save_index, get_images_for_article

warnings.filterwarnings("ignore")

# --- Configuration ---
RULES_PATH    = os.path.join(BASE_DIR, "config", "schema_orbit_ai_v1.json")
BRIEFINGS_DIR = os.path.join(BASE_DIR, "briefings")
CLIENT_DIR    = os.path.join(BASE_DIR, "client")
OUTPUT_DIR    = os.path.join(BASE_DIR, "output", "articles")
REPORTS_DIR   = os.path.join(BASE_DIR, "output", "reports")
BATCH_SIZE = 20
MAX_RETRIES = 2
MIN_SCORE = 80

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_SITE = "https://sowads.com.br"
OPENROUTER_APP  = "Sowads Orbit AI Content Engine"

# Preços por M tokens (input, output) — atualizar conforme OpenRouter
MODEL_PRICING = {
    "google/gemini-2.5-flash":        (0.30,  2.50),
    "google/gemini-2.5-flash-lite":   (0.10,  0.40),
    "google/gemini-2.0-flash-001":    (0.10,  0.40),
    "anthropic/claude-opus-4.7":      (15.00, 75.00),
    "anthropic/claude-opus-4.6":      (15.00, 75.00),
    "anthropic/claude-sonnet-4.6":    (3.00,  15.00),
    "deepseek/deepseek-v4-pro":       (0.44,  0.87),
    "deepseek/deepseek-chat-v3-0324": (0.20,  0.77),
}
_DEFAULT_PRICING = (1.00, 5.00)

def calc_cost(model: str, tok_in, tok_out) -> float:
    price_in, price_out = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    try:
        return (int(tok_in) / 1_000_000 * price_in) + (int(tok_out) / 1_000_000 * price_out)
    except Exception:
        return 0.0

# ANSI Colors
class Colors:
    HEADER  = '\033[95m'
    OKBLUE  = '\033[94m'
    OKCYAN  = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL    = '\033[91m'
    ENDC    = '\033[0m'
    BOLD    = '\033[1m'

# Thread-safe print — necessário para paralelismo
_print_lock = threading.Lock()

def tprint(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs, flush=True)


# ─────────────────────────────────────────────
# OpenRouter — chamada de API
# ─────────────────────────────────────────────

MAX_API_WALL_SECS = 240   # hard limit total por chamada (inclui streaming lento)

def call_openrouter(prompt, api_key, model, fallback_model=None, temperature=0.7, max_tokens=8000, pfx="", api_retries=3):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": OPENROUTER_SITE,
        "X-Title": OPENROUTER_APP,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    prompt_tokens_est = len(prompt) // 4
    tprint(f"  {Colors.OKCYAN}{pfx}[API→] {model.split('/')[-1]} | ~{len(prompt):,} chars prompt (~{prompt_tokens_est:,} tokens){Colors.ENDC}")

    def _call_with_wallclock(mdl):
        """Executa a chamada HTTP em thread separada com hard timeout wall-clock."""
        result = [None]
        error  = [None]

        def do_request():
            try:
                # timeout=(connect, read-per-chunk) — proteção contra servidor morto
                resp = requests.post(
                    OPENROUTER_URL, headers=headers,
                    json={**payload, "model": mdl},
                    timeout=(10, 90)
                )
                resp.raise_for_status()
                data = resp.json()
                if "choices" not in data or not data["choices"]:
                    err_msg = data.get("error", {}).get("message", str(data)[:120])
                    error[0] = ValueError(f"Resposta sem 'choices': {err_msg}")
                    return
                result[0] = (data["choices"][0]["message"]["content"], data.get("usage", {}))
            except Exception as e:
                error[0] = e

        t = threading.Thread(target=do_request, daemon=True)
        t0 = time.time()
        t.start()
        t.join(timeout=MAX_API_WALL_SECS)

        elapsed = time.time() - t0
        if t.is_alive():
            raise TimeoutError(f"Wall-clock limit de {MAX_API_WALL_SECS}s atingido (thread ainda ativa)")
        if error[0]:
            raise error[0]
        if result[0] is None:
            raise RuntimeError("Thread terminou sem resultado")

        text, usage = result[0]
        tok_in  = usage.get("prompt_tokens", 0)
        tok_out = usage.get("completion_tokens", 0)
        suffix  = " (fallback)" if mdl != model else ""
        tprint(f"  {Colors.OKGREEN}{pfx}[API←]{suffix} {elapsed:.1f}s | {len(text):,} chars | tokens entrada:{tok_in} saída:{tok_out}{Colors.ENDC}")
        return text, mdl, {"tok_in": tok_in, "tok_out": tok_out, "elapsed_api": elapsed}

    def _call(mdl, attempt=1):
        t0 = time.time()
        try:
            return _call_with_wallclock(mdl)
        except Exception as e:
            elapsed = time.time() - t0
            if attempt < api_retries:
                wait = 20 * attempt
                tprint(f"  {Colors.WARNING}{pfx}[API] Tentativa {attempt}/{api_retries} falhou em {elapsed:.0f}s ({type(e).__name__}: {str(e)[:80]}). Aguardando {wait}s...{Colors.ENDC}")
                time.sleep(wait)
                return _call(mdl, attempt + 1)
            raise

    try:
        return _call(model)
    except Exception as e:
        if fallback_model:
            tprint(f"  {Colors.WARNING}{pfx}[API] Todas tentativas com {model.split('/')[-1]} falharam. Fallback: {fallback_model}{Colors.ENDC}")
            return _call(fallback_model)
        raise


# ─────────────────────────────────────────────
# Sistema de Briefings
# ─────────────────────────────────────────────

def load_briefing(topic):
    """
    Detecta se existe um briefing relevante para o tema.
    Lê a linha de keywords do .md e verifica se alguma bate com o tópico.
    Retorna os primeiros 800 palavras do conteúdo (sem a linha de keywords).
    Retorna None se nenhum briefing bater.
    """
    if not os.path.isdir(BRIEFINGS_DIR):
        return None

    topic_lower = topic.lower()

    for filepath in glob.glob(os.path.join(BRIEFINGS_DIR, "*.md")):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        # Procura a linha de keywords (primeira linha que começa com "# Palavras-chave")
        keywords_line = ""
        content_lines = content.splitlines()
        body_start = 0
        for idx, line in enumerate(content_lines):
            if line.startswith("# Palavras-chave"):
                keywords_line = line
                body_start = idx + 1
                break

        if not keywords_line:
            continue

        # Extrai keywords da linha
        kw_part = keywords_line.split(":", 1)[-1].strip()
        keywords = [k.strip().lower() for k in kw_part.split(",") if k.strip()]

        # Verifica se alguma keyword bate com o tópico
        matched = any(kw in topic_lower for kw in keywords)
        if not matched:
            continue

        # Pega o corpo do briefing (sem a linha de keywords) e limita a 800 palavras
        body = "\n".join(content_lines[body_start:]).strip()
        words = body.split()
        if len(words) > 800:
            body = " ".join(words[:800]) + "..."

        briefing_name = os.path.basename(filepath).replace(".md", "").upper()
        print(f"  {Colors.OKCYAN}[BRIEFING] Injetando dados de '{briefing_name}' no prompt{Colors.ENDC}")
        return body

    return None


# ─────────────────────────────────────────────
# Contexto do cliente (compliance + produtos)
# ─────────────────────────────────────────────

def load_client_compliance():
    """Lê guia_agente.md com tom, keywords obrigatórias e blacklist do cliente."""
    path = os.path.join(CLIENT_DIR, "guia_agente.md")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_product_context(topic):
    """Extrai a seção de dossie_produtos.md mais relevante para o tema dado."""
    path = os.path.join(CLIENT_DIR, "dossie_produtos.md")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    topic_lower = topic.lower()
    MODULE_KEYWORDS = {
        "### 1.1": ["contas a pagar", "pagamento", "comprovante", "autorização"],
        "### 1.2": ["tesouraria", "extrato", "saldo", "multibanco", "tarifas", "tesoureiro"],
        "### 1.3": ["crédito", "antecipação", "recebíveis", "risco sacado", "supply chain", "capital de giro"],
        "### 1.4": ["analytics", "dados preditivos", "relatório", "dashboard", "planejamento"],
        "## 2.":   ["edi", "api", "open finance", "van bancária", "cnab", "integração bancária", "baas"],
        "## 3.":   ["cash pooling"],
    }

    best_marker, best_score = None, 0
    for marker, keywords in MODULE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in topic_lower)
        if score > best_score:
            best_score, best_marker = score, marker

    if best_marker is None:
        return content[:2000]

    start = content.find(best_marker)
    if start == -1:
        return content[:2000]

    # Find end of section (next heading at same or higher level)
    end = len(content)
    level = best_marker.count("#")
    for pattern in ["\n" + "#" * level + " ", "\n" + "#" * (level - 1) + " "]:
        idx = content.find(pattern, start + 1)
        if idx != -1 and idx < end:
            end = idx

    return content[start:end].strip()


# ─────────────────────────────────────────────
# Carregamento de regras e .env
# ─────────────────────────────────────────────

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_env_file(path=".env"):
    """Carrega variáveis do .env sem sobrescrever as que já existem no ambiente."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# ─────────────────────────────────────────────
# Geração de Prompt
# ─────────────────────────────────────────────

def generate_prompt(topic, rules_json, briefing=None):
    loc_settings    = rules_json.get('localization_settings', {})
    output_reqs     = rules_json.get('output_requirements', {})
    compliance      = rules_json.get('compliance_rules', {})
    seo_rules       = rules_json.get('advanced_seo_and_nlp_rules', {})
    quality         = rules_json.get('content_quality_and_humanization', {})
    tech_seo        = rules_json.get('technical_seo_mandates', {})

    # Client context — loaded fresh each call from client/*.md
    client_compliance = load_client_compliance()
    product_context   = load_product_context(topic)

    aio_rules   = seo_rules.get('aio_optimization_rules', {})
    aio_section = ""
    if aio_rules:
        aio_section = "\n    REGRAS AIO (Otimização para IAs Generativas):\n"
        for key, val in aio_rules.items():
            if key != '_comment':
                aio_section += f"    - {val}\n"

    richness         = quality.get('content_richness_rules', {})
    richness_section = ""
    if richness:
        richness_section = "\n    ELEMENTOS DE CONTEÚDO RICO (OBRIGATÓRIO):\n"
        for key, val in richness.items():
            richness_section += f"    - {val}\n"

    tech_reinforced = quality.get('technical_seo_reinforced', {})
    tech_section    = ""
    if tech_reinforced:
        tech_section = "\n    SEO TÉCNICO REFORÇADO:\n"
        for key, val in tech_reinforced.items():
            tech_section += f"    - {val}\n"

    kw_strategy = seo_rules.get('keyword_strategy', {})
    kw_section  = "\n    ESTRATÉGIA DE KEYWORDS:\n"
    for key, val in kw_strategy.items():
        kw_section += f"    - {val}\n"

    no_promises = compliance.get('no_false_promises', {}).get('rule', '')
    no_legal    = compliance.get('no_legal_advice', {}).get('rule', '')

    # Optional blocks injected when available
    briefing_block = ""
    if briefing:
        briefing_block = f"""
    ════════════════════════════════════════
    DADOS DE PESQUISA — USE ESTES FATOS NO ARTIGO:
    (Dados atualizados de 2025-2026. Integre naturalmente no texto, não como lista separada.)

    {briefing}
    ════════════════════════════════════════
"""

    compliance_block = ""
    if client_compliance:
        compliance_block = f"""
    ════════════════════════════════════════
    REGRAS DO CLIENTE ACCESSTAGE — LEIA ANTES DE ESCREVER:

    {client_compliance}
    ════════════════════════════════════════
"""

    product_block = ""
    if product_context:
        product_block = f"""
    ════════════════════════════════════════
    CONTEXTO DO PRODUTO ACCESSTAGE RELEVANTE PARA ESTE TEMA:

    {product_context}
    ════════════════════════════════════════
"""

    prompt = f"""
    PERSONA DO LEITOR (leia antes de qualquer coisa):
    CFO, diretor financeiro, gestor de tesouraria ou controller de empresa brasileira de médio/grande porte.
    Lê entre reuniões. Vai embora se o conteúdo for genérico, vago ou enrolado.
    Quer profundidade técnica, exemplos concretos do mercado financeiro e conclusões acionáveis.
    Escreva com autoridade consultiva — como um par especialista, não como um vendedor.

    ════════════════════════════════════════
    MISSÃO: Gerar artigo completo para o blog da Accesstage (https://blog.accesstage.com.br/)
    TEMA: "{topic}"
    IDIOMA: {loc_settings.get('force_language', 'pt-BR')}
    PÚBLICO: Gestores financeiros, CFOs e diretores de tesouraria de empresas brasileiras
{briefing_block}{compliance_block}{product_block}
    REGRAS GERAIS DE COMPLIANCE:
    - SEM FALSAS PROMESSAS: {no_promises}
    - {no_legal}

    ELEMENTOS VERIFICÁVEIS OBRIGATÓRIOS (o artigo será auditado por esses critérios):
    - 1 tabela HTML comparativa (use <table> com <thead> e <tbody>)
    - Mínimo 3 H3 dentro dos H2
    - FAQ com mínimo 5 perguntas e respostas completas
    - Word count entre 700 e 1.400 palavras — CONCISÃO É OBRIGATÓRIA. Use listas com bullet points (<ul><li>) sempre que listar etapas, benefícios ou exemplos — isso reduz palavras sem cortar o raciocínio. Parágrafos corridos só quando o argumento exige fluidez. Nenhuma frase incompleta ou cortada. Conclusão em 3 linhas no máximo.

    SEÇÕES ESTRUTURAIS OBRIGATÓRIAS (dentro dessas, crie H2s temáticos livres):
    - ABERTURA: contextualiza o problema com dado real ou pergunta provocativa; sem enrolação
    - DESENVOLVIMENTO: ao menos 4 H2 com profundidade real e exemplos práticos do mercado financeiro corporativo
    - ERROS COMUNS: liste ao menos 3 erros reais que gestores financeiros cometem no tema, com explicação
    - FAQ: mínimo 5 perguntas que um CFO real faria, com respostas diretas e completas
    - CONCLUSÃO + CTA: encerra com síntese e chamada natural para conhecer a Accesstage e a plataforma Veragi

    REGRAS DE FORMATAÇÃO:
    1. {output_reqs.get('wordpress_compatibility_rule', 'A resposta DEVE ter 2 blocos claramente separados.')}
    2. Bloco 1: Meta Title (máx {tech_seo.get('character_limits', {}).get('meta_title_tag', '60 chars')}) & Meta Description (máx {tech_seo.get('character_limits', {}).get('meta_description_tag', '155 chars')}) em texto plano.
    3. Bloco 2: Conteúdo HTML iniciando com <article lang="pt-BR"> e terminando com </article>.
    4. PROIBIDO: <a href>, <img>, <figure>, links externos, URLs de imagem, placeholders, blocos <script>, JSON-LD ou qualquer código técnico — o conteúdo deve ser HTML editorial puro.
    5. FAQ em HTML puro, sem schema markup. Use a estrutura de seção abaixo.
    6. NÃO incluir H1 no conteúdo — o WordPress usa o título do post como H1. Use H2/H3 para seções.
    {kw_section}
    REGRAS SEO/NLP:
    - {seo_rules.get('semantic_enrichment_lsi', {}).get('rule', '')}
    - {seo_rules.get('named_entity_recognition_ner', {}).get('rule', '')}
    {aio_section}
    {richness_section}
    {tech_section}
    QUALIDADE:
    - {quality.get('readability_targets', {}).get('rule', '')}
    - CTA final: convite consultivo e natural para conhecer a Accesstage e a Plataforma Veragi. Sem linguagem de vendas forçada.

    ANTI-CACOETES DE IA — ESTILO OBRIGATÓRIO:
    - PROIBIDO usar travessão (—) como recurso estilístico recorrente
    - PROIBIDO iniciar parágrafos com: "No entanto,", "Além disso,", "Portanto,", "Vale ressaltar que", "É importante destacar", "Em suma,", "Isso posto,", "Nesse sentido,", "Sendo assim,"
    - PROIBIDO aberturas genéricas: "Neste artigo, vamos explorar...", "Neste conteúdo, abordaremos...", "Ao longo deste texto..."
    - Varie o comprimento das frases — misture curtas e longas naturalmente
    - Use voz ativa preferencialmente
    - Conclua seções com argumento concreto, não com resumo do que acabou de ser dito
    - Escreva como um especialista humano escreveria: direto, específico, sem floreios artificiais

    ESTILO DO FAQ (OBRIGATÓRIO — sem script, sem JSON-LD):
    <section class="faq-section" style="background:#f8f9fa;border:1px solid #e2e2e2;border-radius:8px;padding:24px 28px;margin-top:32px;font-size:0.92em;line-height:1.6">
      <h2>Perguntas Frequentes</h2>
      <h3 style="margin-top:18px;margin-bottom:6px;font-size:1.05em;color:#1a1a1a">Pergunta?</h3>
      <p style="margin-top:0;color:#444">Resposta direta e completa.</p>
    </section>

    FORMATO DA RESPOSTA (EXATO — não adicione texto, código ou script fora desse formato):
    Meta Title: [título aqui, máx 60 chars]
    Meta Description: [descrição aqui, máx 155 chars]

    <article lang="pt-BR">
    [conteúdo HTML completo aqui, incluindo FAQ section com inline styles acima]
    </article>

    TEMA PARA ESCREVER: {topic}
    """
    return prompt


# ─────────────────────────────────────────────
# Parse de resposta
# ─────────────────────────────────────────────

def parse_response(response_text):
    post_content = ""
    meta_title   = ""
    meta_desc    = ""

    match_html = re.search(r'(<article.*?</article>)', response_text, re.DOTALL)
    if match_html:
        post_content = match_html.group(1)

    # Remove H1 redundante (WordPress renderiza o título do post como H1)
    post_content = re.sub(r'<h1[^>]*>.*?</h1>\s*', '', post_content, flags=re.DOTALL)

    # Remove imagens e figuras (não usamos no conteúdo)
    post_content = re.sub(r'<figure[^>]*>[\s\S]*?</figure>', '', post_content)
    post_content = re.sub(r'<p[^>]*>\s*<img[^>]*/?>[\s\S]*?</p>', '', post_content)
    post_content = re.sub(r'<img[^>]*/?>',  '', post_content)
    post_content = re.sub(r'<p[^>]*>\s*</p>', '', post_content)

    # Remove qualquer bloco <script> do conteúdo (JSON-LD não é mais usado)
    post_content = re.sub(r'<script\b[^>]*>[\s\S]*?</script>', '', post_content)

    # Remove markdown bold (**texto**) — não deve aparecer em HTML
    post_content = re.sub(r'\*\*(.+?)\*\*', r'\1', post_content, flags=re.DOTALL)

    match_meta_t = re.search(r'Meta Title:\s*(.*)', response_text)
    if match_meta_t:
        meta_title = match_meta_t.group(1).strip()
        meta_title = re.sub(r'\*\*(.+?)\*\*', r'\1', meta_title)

    match_meta_d = re.search(r'Meta Description:\s*(.*)', response_text)
    if match_meta_d:
        meta_desc = match_meta_d.group(1).strip()
        meta_desc = re.sub(r'\*\*(.+?)\*\*', r'\1', meta_desc)

    return post_content, meta_title, meta_desc


# ─────────────────────────────────────────────
# Self-Healing
# ─────────────────────────────────────────────

def self_heal(api_key, model, fallback_model, content, topic, validator, pfx=""):
    """Valida o conteúdo e tenta corrigir via OpenRouter se score < MIN_SCORE."""
    score, issues = validator.grade_article_raw(content)

    if score >= MIN_SCORE:
        return content, score, 0, issues

    for attempt in range(1, MAX_RETRIES + 1):
        issues_text = "\n".join(issues)
        fix_prompt = f"""
        TAREFA: Corrija o artigo HTML abaixo para resolver TODOS os problemas listados.
        TEMA: {topic}

        PROBLEMAS ENCONTRADOS:
        {issues_text}

        REGRAS OBRIGATÓRIAS:
        - Manter <article lang="pt-BR">...</article> como wrapper principal.
        - Seção FAQ DEVE estar em <section class="faq-section"> com <h2>, <h3> e <p>.
        - PROIBIDO: <script>, JSON-LD, <a href>, <img> ou URL externa.
        - Manter todo conteúdo em pt-BR com linguagem natural brasileira.
        - Incluir tabelas comparativas e listas quando relevante.
        - Densidade de keyword primária entre 0.5% e 4.0%.
        - WORD COUNT: MÁXIMO 1.400 PALAVRAS. Se longo, converta parágrafos corridos em listas <ul><li>. Nunca corte o FAQ nem a conclusão. Nenhuma frase incompleta.
        - PROIBIDO qualquer bloco <script>, JSON-LD ou código técnico. Apenas HTML editorial.
        - Retornar APENAS o HTML corrigido (Meta Title + Meta Description + article).

        ARTIGO ATUAL:
        {content}
        """
        try:
            response_text, used_model, _ = call_openrouter(fix_prompt, api_key, model, fallback_model, pfx=pfx)
            new_content, _, _ = parse_response(response_text)
            if not new_content:
                new_content = content

            score, issues = validator.grade_article_raw(new_content)
            tprint(f"  {Colors.OKCYAN}{pfx}[HEAL] tentativa {attempt} → Score {score}/100{Colors.ENDC}")

            if score >= MIN_SCORE:
                return new_content, score, attempt, issues

            content = new_content

        except Exception as e:
            tprint(f"  {Colors.WARNING}{pfx}[HEAL] tentativa {attempt} falhou: {e}{Colors.ENDC}")
            break

    return content, score, MAX_RETRIES, issues


# ─────────────────────────────────────────────
# Análise de artigo
# ─────────────────────────────────────────────

def extract_text(html):
    return re.sub(r'<[^>]+>', ' ', html)

def count_words(text):
    return len(text.split())

def analyze_article(content, meta_title, meta_desc):
    analysis = {}

    analysis['meta_title_len'] = len(meta_title)
    analysis['meta_desc_len']  = len(meta_desc)

    plain = extract_text(content)
    analysis['word_count'] = count_words(plain)

    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
    analysis['h1']     = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else 'N/A'
    analysis['h1_len'] = len(analysis['h1'])

    h2s = re.findall(r'<h2[^>]*>', content)
    h3s = re.findall(r'<h3[^>]*>', content)
    analysis['h2_count'] = len(h2s)
    analysis['h3_count'] = len(h3s)

    analysis['has_table']    = bool(re.search(r'<table[\s>]', content))
    analysis['has_lists']    = bool(re.search(r'<[uo]l[\s>]', content))
    analysis['has_faq_html'] = bool(re.search(r'<section class=["\']faq-section["\']>', content))
    analysis['has_jsonld']   = bool(re.search(r'<script type="application/ld\+json">', content))

    faq_qs = re.findall(r'<h3[^>]*>.*?\?</h3>', content, re.DOTALL)
    analysis['faq_count'] = len(faq_qs)

    if h1_match:
        h1_text  = analysis['h1'].lower()
        stopwords = {'como', 'para', 'com', 'que', 'seu', 'sua', 'dos', 'das',
                     'uma', 'por', 'mais', 'não', 'são', 'pode', 'podem', 'ser',
                     'está', 'isso', 'este', 'esta', 'esse', 'essa', 'nos', 'nas',
                     'aos', 'entre', 'sobre', 'após', 'até', 'sem', 'sob', 'desde',
                     'pmes', 'empresas', 'brasileiras', 'estratégia', 'guia', '2026',
                     'alto', 'impacto', 'vencedoras', 'resultados', 'escalada'}
        keywords = [w for w in h1_text.split() if len(w) >= 3 and w not in stopwords][:3]
        if keywords and analysis['word_count'] > 0:
            kw_count = sum(plain.lower().count(kw) for kw in keywords)
            analysis['keyword_density']  = round((kw_count / analysis['word_count']) * 100, 2)
            analysis['primary_keywords'] = ' '.join(keywords)
        else:
            analysis['keyword_density']  = 0
            analysis['primary_keywords'] = ''
    else:
        analysis['keyword_density']  = 0
        analysis['primary_keywords'] = ''

    entities = ['Accesstage', 'Veragi', 'Open Finance', 'CNAB', 'EDI',
                'Google', 'ChatGPT', 'Gemini', 'Perplexity', 'SEO', 'AIO']
    found_entities = [e for e in entities if e.lower() in plain.lower()]
    analysis['entities']     = found_entities
    analysis['entity_count'] = len(found_entities)

    first_p = re.search(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
    if first_p:
        opening = re.sub(r'<[^>]+>', '', first_p.group(1)).strip()[:100]
        if '?' in opening[:80]:
            analysis['opening_type'] = 'Pergunta provocativa'
        elif re.search(r'\d+%|\d+ (mil|bilh|milh)', opening):
            analysis['opening_type'] = 'Estatística impactante'
        elif any(w in opening.lower() for w in ['imagine', 'pense', 'você já']):
            analysis['opening_type'] = 'Cenário do leitor'
        elif any(w in opening.lower() for w in ['verdade', 'fato', 'realidade', 'mito']):
            analysis['opening_type'] = 'Afirmação ousada'
        else:
            analysis['opening_type'] = 'Narrativa/Introdutória'
    else:
        analysis['opening_type'] = 'N/A'

    return analysis


# ─────────────────────────────────────────────
# Relatório de produção (inalterado)
# ─────────────────────────────────────────────

def generate_report(batch_data, batch_num, model_name, timestamp):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"report_producao_{timestamp}.md")

    total        = len(batch_data)
    scores       = [d.get('qa_score', 0) for d in batch_data]
    retries_list = [d.get('heal_retries', 0) for d in batch_data]
    avg_score    = sum(scores) / total if total > 0 else 0
    approved_first  = sum(1 for r in retries_list if r == 0)
    healed          = sum(1 for r in retries_list if r > 0)
    total_api_calls = total + sum(retries_list)

    lines = []
    lines.append(f"# Orbit AI — Relatório de Produção\n")
    lines.append(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Modelo:** {model_name}")
    lines.append(f"**Artigos gerados:** {total}  |  **Batch:** lote_{batch_num}\n")
    lines.append("---\n")

    lines.append("## Resumo Executivo\n")
    lines.append("| Métrica | Valor |")
    lines.append("|---|---|")
    lines.append(f"| **Score QA Médio** | **{avg_score:.0f}/100** |")
    lines.append(f"| Aprovados de primeira (≥{MIN_SCORE}) | {approved_first} de {total} |")
    lines.append(f"| Corrigidos via self-heal | {healed} de {total} |")
    lines.append(f"| Total de chamadas API (geração + fixes) | {total_api_calls} |")
    all_ok = all(s >= MIN_SCORE for s in scores)
    lines.append(f"| Prontos para WordPress | {sum(1 for s in scores if s >= MIN_SCORE)} de {total} {'✅' if all_ok else '⚠️'} |")
    lines.append("")

    # Métricas de custo/velocidade
    costs    = [d.get('cost_usd', 0) for d in batch_data]
    elapsed_list = [d.get('elapsed_s', 0) for d in batch_data]
    toks_in  = [d.get('tok_in', 0) for d in batch_data]
    toks_out = [d.get('tok_out', 0) for d in batch_data]
    total_cost    = sum(c for c in costs if isinstance(c, (int, float)))
    avg_elapsed   = sum(elapsed_list) / total if total > 0 else 0
    total_tok_in  = sum(t for t in toks_in if isinstance(t, int))
    total_tok_out = sum(t for t in toks_out if isinstance(t, int))

    lines.append("---\n")
    lines.append("## Resumo de Custo e Velocidade\n")
    lines.append("| Métrica | Valor |")
    lines.append("|---|---|")
    lines.append(f"| Modelo principal | `{model_name}` |")
    lines.append(f"| Custo total do lote | U${total_cost:.4f} (≈ R${total_cost*5:.2f}) |")
    lines.append(f"| Custo médio por artigo | U${total_cost/total:.5f} (≈ R${total_cost/total*5:.3f}) |")
    lines.append(f"| Projeção 100 artigos | U${total_cost/total*100:.2f} (≈ R${total_cost/total*500:.2f}) |")
    lines.append(f"| Velocidade média | {avg_elapsed:.0f}s por artigo |")
    lines.append(f"| Tokens de entrada (total) | {total_tok_in:,} |")
    lines.append(f"| Tokens de saída (total) | {total_tok_out:,} |")
    lines.append("")

    lines.append("---\n")
    lines.append("## Nota Individual por Artigo\n")
    lines.append("| # | Título | QA | Tempo | Custo | Tokens (in/out) | Self-heal | Status |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, d in enumerate(batch_data):
        title    = d.get('post_title', 'N/A')[:45]
        score    = d.get('qa_score', 0)
        retries  = d.get('heal_retries', 0)
        el       = d.get('elapsed_s', 0)
        cost_a   = d.get('cost_usd', 0)
        ti       = d.get('tok_in', '—')
        to       = d.get('tok_out', '—')
        status   = "✅ Aprovado" if score >= MIN_SCORE else "❌ Precisa revisão"
        heal     = "✅ 1ª tentativa" if retries == 0 else f"⚠️ {retries}x corrigido"
        lines.append(f"| {i+1} | {title} | {score}/100 | {el:.0f}s | U${cost_a:.5f} | {ti}/{to} | {heal} | {status} |")
    lines.append("")

    for i, d in enumerate(batch_data):
        a = d.get('_analysis', {})
        lines.append("---\n")
        lines.append(f"## Artigo {i+1}: {d.get('post_title', 'N/A')}\n")

        lines.append("### Metadados SEO")
        lines.append("| Campo | Valor | Limite | Status |")
        lines.append("|---|---|---|---|")
        mt_len = a.get('meta_title_len', 0)
        md_len = a.get('meta_desc_len', 0)
        wc     = a.get('word_count', 0)
        mt_ok  = "✅" if mt_len <= 60 else "⚠️ acima de 60"
        md_ok  = "✅" if md_len <= 155 else "⚠️ acima de 155"
        wc_ok  = "✅" if 1200 <= wc <= 2500 else ("⚠️ abaixo do ideal" if wc < 1200 else "⚠️ acima do limite")
        lines.append(f"| Meta Title | \"{d.get('meta_title', 'N/A')[:55]}\" | ≤60 chars | {mt_ok} ({mt_len} chars) |")
        lines.append(f"| Meta Description | \"{d.get('meta_description', 'N/A')[:55]}\" | ≤155 chars | {md_ok} ({md_len} chars) |")
        lines.append(f"| Contagem de palavras | {wc:,} palavras | 1.200–2.500 | {wc_ok} |")
        lines.append("")

        lines.append("### Checklist WordPress (estrutura HTML)")
        lines.append("| Verificação | Resultado | Obs |")
        lines.append("|---|---|---|")
        has_article_tag = '<article lang="pt-BR">' in str(d.get('post_content', ''))
        has_h1_in_body  = bool(re.search(r'<h1[\s>]', str(d.get('post_content', ''))))
        has_links       = bool(re.search(r'<a href=', str(d.get('post_content', ''))))
        has_jsonld      = a.get('has_jsonld', False)
        faq_count       = a.get('faq_count', 0)
        lines.append(f"| Wrapper `<article lang=\"pt-BR\">` | {'✅ Presente' if has_article_tag else '❌ Ausente'} | Necessário para semântica HTML5 |")
        lines.append(f"| H1 ausente no corpo | {'✅ Correto' if not has_h1_in_body else '❌ H1 encontrado no corpo'} | WP usa o título do post como H1 da página |")
        lines.append(f"| Zero hyperlinks no conteúdo | {'✅ Correto' if not has_links else '❌ Links detectados'} | Invariante do projeto — nenhum link no corpo |")
        lines.append(f"| JSON-LD FAQPage ausente | {'✅ Correto' if not has_jsonld else '⚠️ JSON-LD detectado'} | Proibido — WP trata isso via plugin |")
        lines.append(f"| FAQ com ≥5 perguntas | {'✅ ' + str(faq_count) + ' perguntas' if faq_count >= 5 else '❌ Apenas ' + str(faq_count)} | Necessário para rich snippet |")
        lines.append(f"| Tabela HTML | {'✅ Presente' if a.get('has_table') else '—'} | Recomendado para scannability |")
        issues = d.get('_issues', [])
        lines.append(f"| Issues detectados pelo QA | {', '.join(issues) if issues else '✅ Nenhum'} | — |")
        lines.append("")

        lines.append("### Estrutura e SEO semântico")
        lines.append("| Métrica | Valor | Status |")
        lines.append("|---|---|---|")
        h2c = a.get('h2_count', 0)
        h3c = a.get('h3_count', 0)
        lines.append(f"| Hierarquia de headings | H2: {h2c} seções · H3: {h3c} subtópicos | {'✅' if h2c >= 3 and h3c >= 3 else '⚠️ verificar'} |")
        kw = a.get('primary_keywords', '')
        if kw and kw not in ('N/A', ''):
            density = a.get('keyword_density', 0)
            d_ok = "✅" if 0.5 <= density <= 4.0 else "⚠️ fora do range ideal (0.5–4%)"
            lines.append(f"| Keyword primária | {kw} | {density}% densidade — {d_ok} |")
        else:
            lines.append(f"| Keyword primária | — não informada no CSV | Adicione a coluna `keyword` ao CSV de temas para medir densidade |")
        lines.append(f"| Entidades semânticas ({a.get('entity_count', 0)}) | {', '.join(a.get('entities', []))} | Presença de entidades B2B relevantes |")
        lines.append(f"| Tipo de abertura | {a.get('opening_type', 'N/A')} | — |")
        lines.append("")

        retries = d.get('heal_retries', 0)
        model_u = d.get('_model_used', model_name)
        has_bfg = d.get('_briefing_injected', False)
        bfg_vert = d.get('_briefing_vertical', '')
        el_a    = d.get('elapsed_s', 0)
        cost_a  = d.get('cost_usd', 0)
        ti_a    = d.get('tok_in', '—')
        to_a    = d.get('tok_out', '—')
        lines.append("### Contexto injetado e dados de geração")
        lines.append("| Campo | Valor | Obs |")
        lines.append("|---|---|---|")
        lines.append(f"| Modelo | `{model_u}` | — |")
        lines.append(f"| Guia do agente (client/guia_agente.md) | ✅ Injetado | Tom, keywords, blacklist, argumentos por módulo |")
        lines.append(f"| Contexto do produto (client/dossie_produtos.md) | ✅ Injetado | Seção Veragi detectada pelo tema |")
        lines.append(f"| Briefing de vertical (briefings/) | {'✅ ' + bfg_vert[:40] if has_bfg else '— não configurado'} | Dados de mercado externos (opcional) |")
        lines.append(f"| Self-healing | {'✅ Aprovado na 1ª tentativa' if retries == 0 else f'⚠️ {retries}x reprocessado automaticamente'} | — |")
        lines.append(f"| Tempo de geração | {el_a:.0f}s | — |")
        lines.append(f"| Tokens entrada / saída | {ti_a} / {to_a} | — |")
        lines.append(f"| Custo por artigo | U${cost_a:.5f} (≈ R${cost_a*5:.4f}) | — |")
        lines.append("")

    lines.append("---\n")
    if all_ok:
        lines.append(f"## ✅ Status Final: PRONTO PARA PUBLICAÇÃO")
        lines.append(f"Todos os {total} artigos aprovados com score ≥{MIN_SCORE}/100.")
        lines.append(f"\n> **Próximo passo:** `python3 tools/preview_generator.py` para gerar o mockup → revisar → `python3 engine/publisher.py --test_one`")
    else:
        failed = sum(1 for s in scores if s < MIN_SCORE)
        lines.append(f"## ⚠️ Status Final: {failed} ARTIGO(S) PRECISAM REVISÃO MANUAL")
    lines.append(f"\n**Arquivo de artigos:** `output/articles/`")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return report_path


# ─────────────────────────────────────────────
# Sugestão de categoria
# ─────────────────────────────────────────────

def suggest_category(title, content):
    plain_text  = re.sub(r'<[^>]+>', ' ', content).lower()
    title_lower = title.lower()
    search_text = f"{title_lower} {title_lower} {title_lower} {plain_text}"

    scores = {}
    for cat_name, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            count = search_text.count(kw.lower())
            if count > 0:
                weight = len(kw.split())
                score += count * weight
        scores[cat_name] = score

    if scores:
        best = max(scores, key=scores.get)
        if scores[best] > 0:
            return best

    return FALLBACK_CATEGORY


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    load_env_file()

    parser = argparse.ArgumentParser(description="Orbit AI Content Engine — OpenRouter + Briefings")
    parser.add_argument("--openrouter_key", default=os.environ.get("OPENROUTER_API_KEY"), help="Chave OpenRouter")
    parser.add_argument("--api_key",        default=None, help="Alias para --openrouter_key (compatibilidade)")
    parser.add_argument("--model",          default="google/gemini-2.5-flash", help="Modelo primário OpenRouter")
    parser.add_argument("--fallback_model", default="google/gemini-2.5-flash-lite", help="Modelo fallback OpenRouter")
    parser.add_argument("--csv_input",      default=None, help="Caminho para CSV com temas")
    parser.add_argument("--start_batch",    type=int, default=1, help="Iniciar a partir deste batch")
    parser.add_argument("--max_batches",    type=int, default=None, help="Número máximo de batches")
    parser.add_argument("--wp_url",  default=os.environ.get("WORDPRESS_URL"), help="URL WordPress (para índice de imagens)")
    parser.add_argument("--wp_user", default=os.environ.get("WORDPRESS_USER"), help="Usuário WordPress")
    parser.add_argument("--wp_pass", default=os.environ.get("WORDPRESS_PASSWORD"), help="App password WordPress")
    parser.add_argument("--workers", type=int, default=3, help="Artigos em paralelo (default: 3)")
    args = parser.parse_args()

    # Resolve chave (--openrouter_key tem prioridade; --api_key como fallback de CLI)
    api_key = args.openrouter_key or args.api_key
    if not api_key:
        print(f"{Colors.FAIL}[ERRO] Chave OpenRouter não encontrada. Use --openrouter_key ou defina OPENROUTER_API_KEY no .env{Colors.ENDC}")
        return

    print(f"{Colors.HEADER}=== ORBIT AI CONTENT ENGINE — OPENROUTER + BRIEFINGS ==={Colors.ENDC}")
    print(f"{Colors.OKCYAN}[INFO] Modelo primário : {args.model}{Colors.ENDC}")
    if args.fallback_model:
        print(f"{Colors.OKCYAN}[INFO] Modelo fallback  : {args.fallback_model}{Colors.ENDC}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    rules = load_json(RULES_PATH)

    from engine.qa_validator import OrbitValidator
    validator = OrbitValidator()
    print(f"{Colors.OKCYAN}[INFO] Validator carregado (min score: {MIN_SCORE}){Colors.ENDC}")

    # Carrega índice de imagens do WordPress
    media_index = {}
    if args.wp_url and args.wp_user and args.wp_pass:
        from engine.media_indexer import fetch_all_media, build_index, save_index
        print(f"{Colors.OKCYAN}[MEDIA] Buscando biblioteca de imagens do WordPress...{Colors.ENDC}")
        try:
            items = fetch_all_media(args.wp_url, args.wp_user, args.wp_pass)
            media_index = build_index(items)
            save_index(media_index)
            print(f"{Colors.OKGREEN}[MEDIA] {len(media_index)} grupos de imagens indexados.{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}[MEDIA] Falha ao buscar imagens: {e}. Continuando sem imagens.{Colors.ENDC}")
    else:
        # Tenta carregar índice salvo anteriormente
        media_index = load_index()
        if media_index:
            print(f"{Colors.OKCYAN}[MEDIA] Índice local carregado: {len(media_index)} grupos.{Colors.ENDC}")
        else:
            print(f"{Colors.WARNING}[MEDIA] Sem credenciais WordPress e sem índice local. Imagens não serão atribuídas.{Colors.ENDC}")

    # Localiza CSV de temas
    csv_path = args.csv_input
    if not csv_path:
        candidates = sorted(glob.glob("relatorios/sugestao_temas_*.csv"), reverse=True)
        if candidates:
            csv_path = candidates[0]
        else:
            print(f"{Colors.FAIL}[ERRO] Nenhum CSV de temas encontrado. Rode orbit_topic_creator.py primeiro.{Colors.ENDC}")
            return

    df_topics = pd.read_csv(csv_path)
    topics = []
    topic_categories = {}  # topic_text → category string from input CSV
    for _, row in df_topics.iterrows():
        t = row.get('topic_pt') or row.get('topic_es') or row.get('Localized_ES_Draft') or row.get('Original_PT')
        if pd.notna(t) and str(t).strip():
            t = str(t).strip()
            topics.append(t)
            cat = row.get('category', '')
            if pd.notna(cat) and str(cat).strip():
                topic_categories[t] = str(cat).strip()

    print(f"{Colors.OKCYAN}[INFO] Carregados {len(topics)} temas de {csv_path}{Colors.ENDC}")

    total_batches    = (len(topics) + BATCH_SIZE - 1) // BATCH_SIZE
    timestamp        = datetime.now().strftime("%Y%m%d_%H%M")
    batches_processed = 0
    all_batch_data   = []

    for b in range(args.start_batch - 1, total_batches):
        if args.max_batches and batches_processed >= args.max_batches:
            print(f"{Colors.OKCYAN}[INFO] Limite de batches atingido ({args.max_batches}). Parando.{Colors.ENDC}")
            break

        batch_num  = b + 1
        start_idx  = b * BATCH_SIZE
        end_idx    = min(start_idx + BATCH_SIZE, len(topics))
        batch_topics = topics[start_idx:end_idx]

        tprint(f"\n{Colors.HEADER}--- BATCH {batch_num}/{total_batches} (Temas {start_idx+1}–{end_idx}) | workers={args.workers} ---{Colors.ENDC}")

        def generate_article(task):
            global_idx, topic = task
            pfx       = f"[{global_idx:02d}/{len(topics)}]"
            art_t0    = time.time()

            tprint(f"\n{Colors.BOLD}{'─'*60}{Colors.ENDC}")
            tprint(f"{Colors.BOLD}{pfx} {topic[:65]}{Colors.ENDC}")

            try:
                # 1. Contexto do cliente
                compliance_text = load_client_compliance()
                product_text    = load_product_context(topic)
                briefing        = load_briefing(topic)
                ctx_parts = []
                if compliance_text: ctx_parts.append(f"guia ({len(compliance_text):,}c)")
                if product_text:    ctx_parts.append(f"produto ({len(product_text):,}c)")
                if briefing:        ctx_parts.append(f"briefing ({len(briefing):,}c)")
                tprint(f"  {Colors.OKCYAN}{pfx}[CTX] {' | '.join(ctx_parts) or 'sem contexto extra'}{Colors.ENDC}")

                # 2. Prompt + API
                prompt = generate_prompt(topic, rules, briefing=briefing)
                response_text, used_model, api_stats = call_openrouter(
                    prompt, api_key, args.model, args.fallback_model, pfx=pfx
                )

                # 3. Parse
                post_content, meta_title, meta_desc = parse_response(response_text)
                plain_raw = re.sub(r'<[^>]+>', ' ', post_content)
                wc        = len(plain_raw.split())
                h2s       = len(re.findall(r'<h2[^>]*>', post_content))
                h3s       = len(re.findall(r'<h3[^>]*>', post_content))
                faqs      = len(re.findall(r'<h3[^>]*>.*?\?</h3>', post_content, re.DOTALL))
                tabela    = bool(re.search(r'<table[\s>]', post_content))
                tprint(f"  {Colors.OKCYAN}{pfx}[PARSE] {wc}p | H2:{h2s} H3:{h3s} FAQ:{faqs}q | Tabela:{'✓' if tabela else '✗'} | MT:{len(meta_title)}c MD:{len(meta_desc)}c{Colors.ENDC}")

                # 4. QA
                score_pre, issues_pre = validator.grade_article_raw(post_content)
                if issues_pre:
                    for iss in issues_pre:
                        tprint(f"  {Colors.WARNING}{pfx}[QA] ⚠ {iss}{Colors.ENDC}")
                else:
                    tprint(f"  {Colors.OKGREEN}{pfx}[QA] {score_pre}/100 — sem issues{Colors.ENDC}")

                # 5. Self-heal se necessário
                if score_pre < MIN_SCORE:
                    tprint(f"  {Colors.WARNING}{pfx}[HEAL] Score {score_pre} < {MIN_SCORE} — corrigindo...{Colors.ENDC}")
                healed_content, final_score, retries, issues = self_heal(
                    api_key, args.model, args.fallback_model,
                    post_content, topic, validator, pfx=pfx
                )
                if retries > 0:
                    wc_h = len(re.sub(r'<[^>]+>', ' ', healed_content).split())
                    tprint(f"  {Colors.OKCYAN}{pfx}[HEAL] Após {retries}x: {wc_h}p | Score final: {final_score}/100{Colors.ENDC}")

                # 6. Análise e categoria
                analysis       = analyze_article(healed_content, meta_title, meta_desc)
                cat_suggestion = suggest_category(topic, healed_content)
                article_id     = f"Orbit_{global_idx}"

                # 7. Imagens (se índice disponível)
                images, img_score, img_key = get_images_for_article(article_id, topic, media_index)
                images = images or {}
                if images.get("blog"):
                    tprint(f"  {Colors.OKGREEN}{pfx}[IMG] Match: {img_key} (score {img_score:.2f}){Colors.ENDC}")

                # 8. Resumo
                elapsed     = time.time() - art_t0
                tok_in      = api_stats.get("tok_in", 0)
                tok_out     = api_stats.get("tok_out", 0)
                cost        = calc_cost(used_model, tok_in, tok_out)
                score_color = Colors.OKGREEN if final_score >= MIN_SCORE else Colors.WARNING
                extras      = (f" | {retries}x heal" if retries > 0 else "") + (" | briefing" if briefing else "")
                tprint(f"  {score_color}{pfx} ✓ Score:{final_score}/100{extras} | {elapsed:.0f}s | U${cost:.5f}{Colors.ENDC}")

                return {
                    '_idx':              global_idx,
                    'unique_import_id':  article_id,
                    'post_title':        topic,
                    'post_content':      healed_content,
                    'post_date':         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'post_author':       '1',
                    'post_status':       'draft',
                    'language':          'pt-BR',
                    'meta_title':        meta_title,
                    'meta_description':  meta_desc,
                    'original_theme':    topic,
                    'qa_score':          final_score,
                    'heal_retries':      retries,
                    'tok_in':            tok_in,
                    'tok_out':           tok_out,
                    'elapsed_s':         round(elapsed, 1),
                    'cost_usd':          round(cost, 6),
                    'suggested_category': topic_categories.get(topic, cat_suggestion),
                    'img_blog':          images.get('blog', ''),
                    'img_linkedin':      images.get('linkedin', ''),
                    'img_instagram':     images.get('instagram', ''),
                    'img_facebook':      images.get('facebook', ''),
                    'img_tiktok':        images.get('tiktok', ''),
                    '_analysis':         analysis,
                    '_issues':           list(issues),
                    '_model_used':       used_model,
                    '_briefing_injected': bool(briefing),
                    '_briefing_vertical': briefing[:60] if briefing else "",
                }

            except Exception as e:
                elapsed = time.time() - art_t0
                tprint(f"  {Colors.FAIL}{pfx} ✗ ERRO em {elapsed:.0f}s: {e}{Colors.ENDC}")
                return {
                    '_idx':         global_idx,
                    'post_title':   topic,
                    'post_content': f"ERRO NA GERACAO: {e}",
                    'post_status':  'error',
                    'qa_score':     0,
                    'heal_retries': 0,
                    '_analysis':    {},
                    '_issues':      [str(e)],
                }

        tasks     = [(start_idx + i + 1, t) for i, t in enumerate(batch_topics)]
        batch_data = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(generate_article, task): task for task in tasks}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    batch_data.append(result)

        # Reordena pelo índice original (paralelismo quebra a ordem)
        batch_data.sort(key=lambda x: x.get('_idx', 0))

        # Salva batch em CSV (sem campos internos _*)
        input_stem     = os.path.splitext(os.path.basename(csv_path))[0].replace("_temas", "")
        model_slug     = re.sub(r"[^a-z0-9]+", "-", args.model.split("/")[-1].lower())[:20].strip("-")
        batch_filename = f"{input_stem}_{model_slug}_batch{batch_num}_artigos_{start_idx+1}_a_{end_idx}.csv"
        batch_path     = os.path.join(OUTPUT_DIR, batch_filename)
        csv_rows       = [{k: v for k, v in d.items() if not k.startswith('_')} for d in batch_data]
        pd.DataFrame(csv_rows).to_csv(batch_path, index=False, quoting=csv.QUOTE_ALL)

        print(f"{Colors.OKBLUE}>> Batch {batch_num} salvo em {batch_path}{Colors.ENDC}")
        all_batch_data.extend(batch_data)
        batches_processed += 1

    if all_batch_data:
        report_path = generate_report(all_batch_data, batches_processed, args.model, timestamp)
        print(f"\n{Colors.OKGREEN}[REPORT] Relatório gerado: {report_path}{Colors.ENDC}")

    print(f"\n{Colors.HEADER}=== TODOS OS BATCHES COMPLETOS ==={Colors.ENDC}")


if __name__ == "__main__":
    main()
