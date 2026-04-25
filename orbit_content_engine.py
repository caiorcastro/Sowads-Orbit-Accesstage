import os
import csv
import json
import time
import re
import glob
import argparse
import warnings
import requests
from datetime import datetime
import pandas as pd
from orbit_publisher import CATEGORY_KEYWORDS, FALLBACK_CATEGORY
from orbit_media_indexer import load_index, save_index, get_images_for_article

warnings.filterwarnings("ignore")

# --- Configuration ---
RULES_PATH = "regras_geracao/schema_orbit_ai_v1.json"
BRIEFINGS_DIR = "briefings"
OUTPUT_DIR = "output_csv_batches_v2"
REPORTS_DIR = "relatorios"
BATCH_SIZE = 20
MAX_RETRIES = 2
MIN_SCORE = 80

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_SITE = "https://sowads.com.br"
OPENROUTER_APP  = "Sowads Orbit AI Content Engine"

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


# ─────────────────────────────────────────────
# OpenRouter — chamada de API
# ─────────────────────────────────────────────

def call_openrouter(prompt, api_key, model, fallback_model=None, temperature=0.7, max_tokens=8000):
    """Call OpenRouter API with optional fallback model on failure."""
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

    # Attempt primary model
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        used_model = model
        return text, used_model
    except Exception as e:
        if fallback_model:
            print(f"  {Colors.WARNING}[OPENROUTER] Modelo principal falhou ({e}). Tentando fallback: {fallback_model}{Colors.ENDC}")
            payload["model"] = fallback_model
            try:
                resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=300)
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return text, fallback_model
            except Exception as e2:
                raise RuntimeError(f"Falha no modelo primário e no fallback: {e} | {e2}")
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
    agent_profile = rules_json.get('agent_profile', {})
    loc_settings   = rules_json.get('localization_settings', {})
    output_reqs    = rules_json.get('output_requirements', {})
    compliance     = rules_json.get('compliance_rules', {})
    brand          = rules_json.get('sowads_brand', {})
    seo_rules      = rules_json.get('advanced_seo_and_nlp_rules', {})
    quality        = rules_json.get('content_quality_and_humanization', {})
    tech_seo       = rules_json.get('technical_seo_mandates', {})

    independence_rule = compliance.get('product_independence', {}).get('rule', '')
    no_promises       = compliance.get('no_false_promises', {}).get('rule', '')

    products_info = ""
    for key, prod in brand.get('products', {}).items():
        products_info += f"- {prod.get('name')}: {prod.get('description')}\n"

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

    # Briefing injection (dados reais além do corte da IA)
    briefing_block = ""
    if briefing:
        briefing_block = f"""
    ════════════════════════════════════════
    DADOS DE PESQUISA — USE ESTES FATOS NO ARTIGO:
    (Dados atualizados de 2025-2026. Integre naturalmente no texto, não como lista separada.)

    {briefing}
    ════════════════════════════════════════
"""

    prompt = f"""
    PERSONA DO LEITOR (leia antes de qualquer coisa):
    Gestor, profissional de marketing ou empreendedor brasileiro, 28–50 anos, formação superior.
    Consome o artigo no celular ou entre reuniões. Vai embora se o conteúdo for genérico, vago
    ou enrolado. Quer profundidade, dados reais e conclusões acionáveis. Escreva para ele.

    ════════════════════════════════════════
    ROLE: {agent_profile.get('agent_name')}
    DIRECTIVE: {agent_profile.get('primary_directive')}
    PHILOSOPHY: {agent_profile.get('core_philosophy')}

    TASK: Gerar um pacote de conteúdo WordPress para o tema: "{topic}"
    Público-alvo: Brasil ({', '.join(loc_settings.get('audience_country_supported', []))})
    Idioma: {loc_settings.get('force_language')}
{briefing_block}
    SOBRE A SOWADS:
    {products_info}
    Serviços: {', '.join(brand.get('services', []))}

    REGRAS DE COMPLIANCE:
    1. INDEPENDÊNCIA DE PRODUTOS: {independence_rule}
       ⚠️ ATENÇÃO ESPECIAL: Se o tema envolve "Mídia Paga", "anúncios" ou "tráfego pago", é PROIBIDO sugerir que anúncios melhoram ranqueamento orgânico, autoridade de domínio ou posição nos buscadores. Tratá-los sempre como canais paralelos e independentes. Violações invalidam o artigo.
    2. SEM FALSAS PROMESSAS: {no_promises}
    3. {compliance.get('no_legal_advice', {}).get('rule', '')}

    ELEMENTOS VERIFICÁVEIS OBRIGATÓRIOS (o artigo será auditado por esses critérios):
    - 1 tabela HTML comparativa (use <table> com <thead> e <tbody>)
    - Mínimo 3 H3 dentro dos H2
    - FAQ com mínimo 5 perguntas e respostas completas
    - Word count entre 700 e 1.400 palavras — CONCISÃO É OBRIGATÓRIA. Use listas com bullet points (<ul><li>) sempre que listar etapas, benefícios ou exemplos — isso reduz palavras sem cortar o raciocínio. Parágrafos corridos só quando o argumento exige fluidez. Nenhuma frase incompleta ou cortada. Conclusão em 3 linhas no máximo.

    SEÇÕES ESTRUTURAIS OBRIGATÓRIAS (dentro dessas, crie H2s temáticos livres):
    - ABERTURA: contextualiza o problema com dado real ou pergunta provocativa; sem enrolação
    - DESENVOLVIMENTO: ao menos 4 H2 com profundidade real, dados e exemplos práticos
    - ERROS COMUNS: liste ao menos 3 erros reais que gestores cometem no tema, com explicação
    - FAQ: mínimo 5 perguntas que um leitor real faria, com respostas diretas e completas
    - CONCLUSÃO + CTA: encerra com síntese e chamada natural para a Sowads

    REGRAS DE FORMATAÇÃO:
    1. {output_reqs.get('wordpress_compatibility_rule')}
    2. Bloco 1: Meta Title (máx {tech_seo.get('character_limits', {}).get('meta_title_tag', '60 chars')}) & Meta Description (máx {tech_seo.get('character_limits', {}).get('meta_description_tag', '155 chars')}) em texto plano.
    3. Bloco 2: Conteúdo HTML iniciando com <article lang="pt-BR"> e terminando com </article>.
    4. PROIBIDO: <a href>, <img>, <figure>, links externos, URLs de imagem, placeholders, blocos <script>, JSON-LD ou qualquer código técnico — o conteúdo deve ser HTML editorial puro.
    5. FAQ em HTML puro, sem schema markup. Use a estrutura de seção abaixo.
    6. Hierarquia: um único H1 (máx {tech_seo.get('character_limits', {}).get('h1_tag', '60 chars')}); H2/H3 para seções.
    {kw_section}
    REGRAS SEO/NLP:
    - {seo_rules.get('semantic_enrichment_lsi', {}).get('rule', '')}
    - {seo_rules.get('named_entity_recognition_ner', {}).get('rule', '')}
    {aio_section}
    {richness_section}
    {tech_section}
    QUALIDADE:
    - {quality.get('readability_targets', {}).get('rule', '')}
    - CTA: {loc_settings.get('cta_text', '')}

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

def self_heal(api_key, model, fallback_model, content, topic, validator):
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
            response_text, used_model = call_openrouter(fix_prompt, api_key, model, fallback_model)
            new_content, _, _ = parse_response(response_text)
            if not new_content:
                new_content = content

            score, issues = validator.grade_article_raw(new_content)
            print(f"    {Colors.OKCYAN}[HEAL] Tentativa {attempt} ({used_model}): Score {score}/100{Colors.ENDC}")

            if score >= MIN_SCORE:
                return new_content, score, attempt, issues

            content = new_content

        except Exception as e:
            print(f"    {Colors.WARNING}[HEAL] Tentativa {attempt} falhou: {e}{Colors.ENDC}")
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

    entities = ['Sowads', 'Orbit AI', 'Meta Ads', 'Google', 'ChatGPT', 'Gemini',
                'Perplexity', 'WordPress', 'SEO', 'AIO', 'Facebook', 'Instagram']
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

    lines.append("---\n")
    lines.append("## Nota Individual por Artigo\n")
    lines.append("| # | Título | Score | Retries | Modelo | Briefing | Status |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, d in enumerate(batch_data):
        title    = d.get('post_title', 'N/A')[:50]
        score    = d.get('qa_score', 0)
        retries  = d.get('heal_retries', 0)
        model_u  = d.get('_model_used', model_name).split('/')[-1]
        briefing = "✅" if d.get('_briefing_injected') else "—"
        status   = "✅ Aprovado" if score >= MIN_SCORE else "❌ Precisa revisão"
        lines.append(f"| {i+1} | {title} | {score}/100 | {retries} | {model_u} | {briefing} | {status} |")
    lines.append("")

    for i, d in enumerate(batch_data):
        a = d.get('_analysis', {})
        lines.append("---\n")
        lines.append(f"## Detalhamento — Artigo {i+1}: {d.get('post_title', 'N/A')}\n")

        lines.append("### Metadados")
        lines.append("| Campo | Valor | Limite | OK? |")
        lines.append("|---|---|---|---|")
        mt_ok = "✅" if a.get('meta_title_len', 0) <= 60 else "❌"
        md_ok = "✅" if a.get('meta_desc_len', 0) <= 155 else "❌"
        h1_ok = "✅" if a.get('h1_len', 0) <= 60 else "❌"
        wc    = a.get('word_count', 0)
        wc_ok = "✅" if 1200 <= wc <= 2500 else "⚠️"
        lines.append(f"| Meta Title | \"{d.get('meta_title', 'N/A')[:50]}\" | ≤60 chars | {mt_ok} {a.get('meta_title_len', 0)} chars |")
        lines.append(f"| Meta Description | \"{d.get('meta_description', 'N/A')[:50]}\" | ≤155 chars | {md_ok} {a.get('meta_desc_len', 0)} chars |")
        lines.append(f"| H1 | \"{a.get('h1', 'N/A')[:50]}\" | ≤60 chars | {h1_ok} {a.get('h1_len', 0)} chars |")
        lines.append(f"| Word Count | {wc:,} palavras | 1200-2500 | {wc_ok} |")
        lines.append("")

        lines.append(f"### Checklist de Qualidade (Score: {d.get('qa_score', 0)}/100)")
        lines.append("| Verificação | Resultado |")
        lines.append("|---|---|")
        has_article_tag = '<article lang="pt-BR">' in str(d.get('post_content', ''))
        lines.append(f"| `<article lang=\"pt-BR\">` | {'✅' if has_article_tag else '❌'} |")
        lines.append(f"| `<h1>` único | {'✅' if a.get('h1') != 'N/A' else '❌'} |")
        lines.append(f"| `<section class=\"faq-section\">` | {'✅' if a.get('has_faq_html') else '❌'} |")
        lines.append(f"| JSON-LD FAQPage | {'✅' if a.get('has_jsonld') else '❌'} |")
        lines.append(f"| Zero links `<a href>` | {'✅' if not re.search(r'<a href=', str(d.get('post_content', ''))) else '❌'} |")
        lines.append(f"| Tabela HTML | {'✅' if a.get('has_table') else '❌'} |")
        lines.append(f"| Mínimo 3 H3 | {'✅' if a.get('h3_count', 0) >= 3 else '❌ ' + str(a.get('h3_count', 0))} |")
        lines.append(f"| FAQ (≥5 perguntas) | {'✅ ' + str(a.get('faq_count', 0)) if a.get('faq_count', 0) >= 5 else '❌ ' + str(a.get('faq_count', 0))} |")
        issues = d.get('_issues', [])
        lines.append(f"| **Issues** | {', '.join(issues) if issues else 'Nenhum ✅'} |")
        lines.append("")

        lines.append("### Análise SEO")
        lines.append("| Métrica | Valor |")
        lines.append("|---|---|")
        lines.append(f"| Keyword primária | \"{a.get('primary_keywords', 'N/A')}\" |")
        density    = a.get('keyword_density', 0)
        density_ok = "✅" if 0.5 <= density <= 4.0 else "⚠️"
        lines.append(f"| Densidade da keyword | {density}% {density_ok} |")
        lines.append(f"| Hierarquia headings | H1(1) → H2({a.get('h2_count', 0)}) → H3({a.get('h3_count', 0)}) |")
        lines.append(f"| Entidades detectadas ({a.get('entity_count', 0)}) | {', '.join(a.get('entities', []))} |")
        lines.append(f"| Abertura | {a.get('opening_type', 'N/A')} |")
        lines.append("")

        retries  = d.get('heal_retries', 0)
        model_u  = d.get('_model_used', model_name)
        briefing = d.get('_briefing_injected', False)
        lines.append("### Geração")
        lines.append("| Campo | Valor |")
        lines.append("|---|---|")
        lines.append(f"| Modelo usado | `{model_u}` |")
        lines.append(f"| Briefing injetado | {'✅ Sim' if briefing else '— Não'} |")
        lines.append(f"| Self-healing | {'Aprovado de primeira ✅' if retries == 0 else str(retries) + ' correção(ões) aplicadas'} |")
        lines.append("")

    lines.append("---\n")
    if all_ok:
        lines.append(f"## ✅ Status Final: PRONTO PARA PRODUÇÃO")
        lines.append(f"Todos os {total} artigos atingiram score ≥{MIN_SCORE}.")
    else:
        failed = sum(1 for s in scores if s < MIN_SCORE)
        lines.append(f"## ⚠️ Status Final: {failed} ARTIGO(S) PRECISAM REVISÃO MANUAL")
    lines.append(f"\nArquivos: `{OUTPUT_DIR}/lote_{batch_num}_*.csv`")

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
    parser.add_argument("--model",          default="deepseek/deepseek-v4-pro", help="Modelo primário OpenRouter")
    parser.add_argument("--fallback_model", default=None, help="Modelo fallback OpenRouter (opcional)")
    parser.add_argument("--csv_input",      default=None, help="Caminho para CSV com temas")
    parser.add_argument("--start_batch",    type=int, default=1, help="Iniciar a partir deste batch")
    parser.add_argument("--max_batches",    type=int, default=None, help="Número máximo de batches")
    parser.add_argument("--wp_url",  default=os.environ.get("WORDPRESS_URL"), help="URL WordPress (para índice de imagens)")
    parser.add_argument("--wp_user", default=os.environ.get("WORDPRESS_USER"), help="Usuário WordPress")
    parser.add_argument("--wp_pass", default=os.environ.get("WORDPRESS_PASSWORD"), help="App password WordPress")
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

    from orbit_qa_validator import OrbitValidator
    validator = OrbitValidator()
    print(f"{Colors.OKCYAN}[INFO] Validator carregado (min score: {MIN_SCORE}){Colors.ENDC}")

    # Carrega índice de imagens do WordPress
    media_index = {}
    if args.wp_url and args.wp_user and args.wp_pass:
        from orbit_media_indexer import fetch_all_media, build_index, save_index
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

        print(f"\n{Colors.HEADER}--- BATCH {batch_num}/{total_batches} (Temas {start_idx+1}–{end_idx}) ---{Colors.ENDC}")

        batch_data = []

        for i, topic in enumerate(batch_topics):
            global_idx = start_idx + i + 1
            print(f"{Colors.BOLD}[{global_idx}/{len(topics)}] Gerando:{Colors.ENDC} {topic[:60]}...")

            try:
                briefing = load_briefing(topic)
                prompt   = generate_prompt(topic, rules, briefing=briefing)

                response_text, used_model = call_openrouter(
                    prompt, api_key, args.model, args.fallback_model
                )

                post_content, meta_title, meta_desc = parse_response(response_text)

                healed_content, final_score, retries, issues = self_heal(
                    api_key, args.model, args.fallback_model,
                    post_content, topic, validator
                )

                analysis       = analyze_article(healed_content, meta_title, meta_desc)
                cat_suggestion = suggest_category(topic, healed_content)
                article_id     = f"Orbit_{global_idx}"

                # Match de imagens pelo ID do artigo e pelo tema
                images, img_score, img_key = get_images_for_article(article_id, topic, media_index)
                images = images or {}
                if images.get("blog"):
                    print(f"  {Colors.OKGREEN}[IMG] Match encontrado para {article_id}{Colors.ENDC}")
                else:
                    print(f"  {Colors.WARNING}[IMG] Sem imagem disponível para {article_id}{Colors.ENDC}")

                row = {
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
                }
                batch_data.append(row)

                score_color = Colors.OKGREEN if final_score >= MIN_SCORE else Colors.WARNING
                status_msg  = f"Score: {final_score}/100"
                if retries > 0:
                    status_msg += f" (após {retries} correção(ões))"
                if briefing:
                    status_msg += " [briefing injetado]"
                print(f"  -> {score_color}{status_msg}{Colors.ENDC}")
                time.sleep(2)

            except Exception as e:
                print(f"  -> {Colors.FAIL}ERRO: {e}{Colors.ENDC}")
                batch_data.append({
                    'post_title':   topic,
                    'post_content': f"ERRO NA GERACAO: {str(e)}",
                    'post_status':  'error',
                    'qa_score':     0,
                    'heal_retries': 0,
                    '_analysis':    {},
                    '_issues':      [str(e)],
                })

        # Salva batch em CSV (sem campos internos _*)
        input_stem     = os.path.splitext(os.path.basename(csv_path))[0].replace("_temas", "")
        batch_filename = f"{input_stem}_batch{batch_num}_artigos_{start_idx+1}_a_{end_idx}.csv"
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
