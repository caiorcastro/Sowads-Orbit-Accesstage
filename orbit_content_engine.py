
import os
import csv
import json
import time
import re
import argparse
import warnings
from datetime import datetime
import google.generativeai as genai
import pandas as pd
from orbit_publisher import CATEGORY_KEYWORDS, FALLBACK_CATEGORY

# Suppress warnings
warnings.filterwarnings("ignore")

# --- Configuration ---
RULES_PATH = "regras_geracao/schema_orbit_ai_v1.json"
OUTPUT_DIR = "output_csv_batches_v2"
REPORTS_DIR = "relatorios"
BATCH_SIZE = 20
MAX_RETRIES = 2
MIN_SCORE = 80

# ANSI Colors for CLI
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_prompt(topic, rules_json):
    agent_profile = rules_json.get('agent_profile', {})
    loc_settings = rules_json.get('localization_settings', {})
    output_reqs = rules_json.get('output_requirements', {})
    compliance = rules_json.get('compliance_rules', {})
    brand = rules_json.get('sowads_brand', {})
    seo_rules = rules_json.get('advanced_seo_and_nlp_rules', {})
    quality = rules_json.get('content_quality_and_humanization', {})
    tech_seo = rules_json.get('technical_seo_mandates', {})

    independence_rule = compliance.get('product_independence', {}).get('rule', '')
    no_promises = compliance.get('no_false_promises', {}).get('rule', '')

    products_info = ""
    for key, prod in brand.get('products', {}).items():
        products_info += f"- {prod.get('name')}: {prod.get('description')}\n"

    # AIO rules
    aio_rules = seo_rules.get('aio_optimization_rules', {})
    aio_section = ""
    if aio_rules:
        aio_section = "\n    REGRAS AIO (Otimização para IAs Generativas):\n"
        for key, val in aio_rules.items():
            if key != '_comment':
                aio_section += f"    - {val}\n"

    # Content richness
    richness = quality.get('content_richness_rules', {})
    richness_section = ""
    if richness:
        richness_section = "\n    ELEMENTOS DE CONTEÚDO RICO (OBRIGATÓRIO):\n"
        for key, val in richness.items():
            richness_section += f"    - {val}\n"

    # Technical SEO reinforced
    tech_reinforced = quality.get('technical_seo_reinforced', {})
    tech_section = ""
    if tech_reinforced:
        tech_section = "\n    SEO TÉCNICO REFORÇADO:\n"
        for key, val in tech_reinforced.items():
            tech_section += f"    - {val}\n"

    # Keyword strategy detailed
    kw_strategy = seo_rules.get('keyword_strategy', {})
    kw_section = "\n    ESTRATÉGIA DE KEYWORDS:\n"
    for key, val in kw_strategy.items():
        kw_section += f"    - {val}\n"

    prompt = f"""
    ROLE: {agent_profile.get('agent_name')}
    DIRECTIVE: {agent_profile.get('primary_directive')}
    PHILOSOPHY: {agent_profile.get('core_philosophy')}

    TASK: Gerar um pacote de conteúdo WordPress para o tema: "{topic}"
    Público-alvo: Brasil ({', '.join(loc_settings.get('audience_country_supported', []))})
    Idioma: {loc_settings.get('force_language')}

    SOBRE A SOWADS:
    {products_info}
    Serviços: {', '.join(brand.get('services', []))}

    REGRAS DE COMPLIANCE:
    1. INDEPENDÊNCIA DE PRODUTOS: {independence_rule}
    2. SEM FALSAS PROMESSAS: {no_promises}
    3. {compliance.get('no_legal_advice', {}).get('rule', '')}

    REGRAS DE FORMATAÇÃO:
    1. {output_reqs.get('wordpress_compatibility_rule')}
    2. Bloco 1: Meta Title (máx {tech_seo.get('character_limits', {}).get('meta_title_tag', '60 chars')}) & Meta Description (máx {tech_seo.get('character_limits', {}).get('meta_description_tag', '155 chars')}) em texto plano.
    3. Bloco 2: Conteúdo HTML iniciando com <article lang="pt-BR"> e terminando com </article>.
    4. NENHUM LINK permitido no texto. Zero tags <a href>.
    PROIBIDO: NÃO incluir NENHUMA tag <img>. Zero imagens. Sem placeholders, sem example.com, sem URLs de imagem.
    5. {tech_seo.get('faq_schema_generation', {}).get('instruction', 'FAQ em HTML puro.')}
    6. Hierarquia: um único H1 (máx {tech_seo.get('character_limits', {}).get('h1_tag', '60 chars')}); H2/H3 para seções.
    7. O bloco JSON-LD <script type="application/ld+json"> com FAQPage DEVE vir DEPOIS do </article>.
    {kw_section}
    REGRAS SEO/NLP:
    - {seo_rules.get('semantic_enrichment_lsi', {}).get('rule', '')}
    - {seo_rules.get('named_entity_recognition_ner', {}).get('rule', '')}
    {aio_section}
    {richness_section}
    {tech_section}
    QUALIDADE:
    - {quality.get('readability_targets', {}).get('rule', '')}
    - Word count: 1200-2500 palavras.
    - CTA: {loc_settings.get('cta_text', '')}

    FORMATO DA RESPOSTA (EXATO):
    Meta Title: [título aqui, máx 60 chars]
    Meta Description: [descrição aqui, máx 155 chars]

    <article lang="pt-BR">
    [conteúdo HTML completo aqui, incluindo FAQ section]
    </article>
    <script type="application/ld+json">
    [JSON-LD FAQPage aqui]
    </script>

    TEMA PARA ESCREVER: {topic}
    """
    return prompt

def parse_response(response_text):
    post_content = ""
    meta_title = ""
    meta_desc = ""

    # Capture article
    match_html = re.search(r'(<article.*?</article>)', response_text, re.DOTALL)
    if match_html:
        post_content = match_html.group(1)

    # Strip <h1> — WordPress renders the post title as H1 automatically
    post_content = re.sub(r'<h1[^>]*>.*?</h1>\s*', '', post_content, flags=re.DOTALL)

    # Strip any <img> tags (Gemini sometimes adds placeholder images)
    post_content = re.sub(r'<figure[^>]*>\s*<img[^>]*/?>[\s\S]*?</figure>', '', post_content)
    post_content = re.sub(r'<p[^>]*>\s*<img[^>]*/?>[\s\S]*?</p>', '', post_content)
    post_content = re.sub(r'<img[^>]*/?>',  '', post_content)
    post_content = re.sub(r'<p[^>]*>\s*</p>', '', post_content)

    # Capture JSON-LD block and append
    match_jsonld = re.search(r'(<script type="application/ld\+json">.*?</script>)', response_text, re.DOTALL)
    if match_jsonld:
        post_content = post_content + "\n" + match_jsonld.group(1)

    # Meta fields
    match_meta_t = re.search(r'Meta Title:\s*(.*)', response_text)
    if match_meta_t:
        meta_title = match_meta_t.group(1).strip()

    match_meta_d = re.search(r'Meta Description:\s*(.*)', response_text)
    if match_meta_d:
        meta_desc = match_meta_d.group(1).strip()

    return post_content, meta_title, meta_desc


def self_heal(model, content, topic, validator):
    """Validate content and retry with Gemini if score < MIN_SCORE. Max MAX_RETRIES attempts."""
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
        - A seção FAQ DEVE estar dentro de <section class="faq-section"> com <h2>, <h3> e <p>.
        - DEVE incluir <script type="application/ld+json"> com FAQPage schema APÓS o </article>.
        - NENHUM link <a href=...> permitido.
        - Manter todo conteúdo em pt-BR com linguagem natural brasileira.
        - Incluir tabelas comparativas e listas quando relevante.
        - Densidade de keyword primária entre 0.5% e 4.0%.
        - Retornar APENAS o HTML corrigido (Meta Title + Meta Description + article + JSON-LD), sem explicações.

        ARTIGO ATUAL:
        Meta Title: (manter o existente ou melhorar)
        Meta Description: (manter o existente ou melhorar)

        {content}
        """
        try:
            response = model.generate_content(fix_prompt)
            new_content, _, _ = parse_response(response.text)
            if not new_content:
                new_content = content

            score, issues = validator.grade_article_raw(new_content)
            print(f"    {Colors.OKCYAN}[HEAL] Tentativa {attempt}: Score {score}/100{Colors.ENDC}")

            if score >= MIN_SCORE:
                return new_content, score, attempt, issues

            content = new_content

        except Exception as e:
            print(f"    {Colors.WARNING}[HEAL] Tentativa {attempt} falhou: {e}{Colors.ENDC}")
            break

    return content, score, MAX_RETRIES, issues


def extract_text(html):
    """Strip HTML tags and return plain text."""
    return re.sub(r'<[^>]+>', ' ', html)

def count_words(text):
    """Count words in plain text."""
    return len(text.split())

def analyze_article(content, meta_title, meta_desc):
    """Analyze article for report metrics."""
    analysis = {}

    # Meta lengths
    analysis['meta_title_len'] = len(meta_title)
    analysis['meta_desc_len'] = len(meta_desc)

    # Word count
    plain = extract_text(content)
    analysis['word_count'] = count_words(plain)

    # H1
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
    analysis['h1'] = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else 'N/A'
    analysis['h1_len'] = len(analysis['h1'])

    # Headings hierarchy
    h2s = re.findall(r'<h2[^>]*>', content)
    h3s = re.findall(r'<h3[^>]*>', content)
    analysis['h2_count'] = len(h2s)
    analysis['h3_count'] = len(h3s)

    # Has table?
    analysis['has_table'] = bool(re.search(r'<table[\s>]', content))

    # Has lists?
    analysis['has_lists'] = bool(re.search(r'<[uo]l[\s>]', content))

    # Has FAQ HTML?
    analysis['has_faq_html'] = bool(re.search(r'<section class=["\']faq-section["\']>', content))

    # Has JSON-LD?
    analysis['has_jsonld'] = bool(re.search(r'<script type="application/ld\+json">', content))

    # FAQ question count
    faq_qs = re.findall(r'<h3[^>]*>.*?\?</h3>', content, re.DOTALL)
    analysis['faq_count'] = len(faq_qs)

    # Keyword density — usa as top 2-3 palavras mais relevantes do H1
    if h1_match:
        h1_text = analysis['h1'].lower()
        stopwords = {'como', 'para', 'com', 'que', 'seu', 'sua', 'dos', 'das',
                     'uma', 'por', 'mais', 'não', 'são', 'pode', 'podem', 'ser',
                     'está', 'isso', 'este', 'esta', 'esse', 'essa', 'nos', 'nas',
                     'aos', 'entre', 'sobre', 'após', 'até', 'sem', 'sob', 'desde',
                     'pmes', 'empresas', 'brasileiras', 'estratégia', 'guia', '2026',
                     'alto', 'impacto', 'vencedoras', 'resultados', 'escalada'}
        keywords = [w for w in h1_text.split() if len(w) >= 3 and w not in stopwords]
        # Keep only top 3 most specific keywords
        keywords = keywords[:3]
        if keywords and analysis['word_count'] > 0:
            kw_count = sum(plain.lower().count(kw) for kw in keywords)
            analysis['keyword_density'] = round((kw_count / analysis['word_count']) * 100, 2)
            analysis['primary_keywords'] = ' '.join(keywords)
        else:
            analysis['keyword_density'] = 0
            analysis['primary_keywords'] = ''
    else:
        analysis['keyword_density'] = 0
        analysis['primary_keywords'] = ''

    # Entities detected
    entities = ['Sowads', 'Orbit AI', 'Meta Ads', 'Google', 'ChatGPT', 'Gemini',
                'Perplexity', 'WordPress', 'SEO', 'AIO', 'Facebook', 'Instagram']
    found_entities = [e for e in entities if e.lower() in plain.lower()]
    analysis['entities'] = found_entities
    analysis['entity_count'] = len(found_entities)

    # Opening type detection
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


def generate_report(batch_data, batch_num, model_name, timestamp):
    """Generate detailed production report in Markdown."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"report_producao_{timestamp}.md")

    total = len(batch_data)
    scores = [d.get('qa_score', 0) for d in batch_data]
    retries_list = [d.get('heal_retries', 0) for d in batch_data]
    avg_score = sum(scores) / total if total > 0 else 0
    approved_first = sum(1 for r in retries_list if r == 0)
    healed = sum(1 for r in retries_list if r > 0)
    total_api_calls = total + sum(retries_list)

    lines = []
    lines.append(f"# 📊 Orbit AI — Relatório de Produção\n")
    lines.append(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Modelo:** {model_name}")
    lines.append(f"**Artigos gerados:** {total}  |  **Batch:** lote_{batch_num}\n")
    lines.append("---\n")

    # Resumo executivo
    lines.append("## Resumo Executivo\n")
    lines.append("| Métrica | Valor |")
    lines.append("|---|---|")
    lines.append(f"| **Score QA Médio** | **{avg_score:.0f}/100** |")
    lines.append(f"| Artigos aprovados de primeira (≥{MIN_SCORE}) | {approved_first} de {total} |")
    lines.append(f"| Artigos corrigidos via self-heal | {healed} de {total} |")
    lines.append(f"| Total de chamadas Gemini (geração + fixes) | {total_api_calls} |")
    all_ok = all(s >= MIN_SCORE for s in scores)
    lines.append(f"| Artigos prontos para WordPress | {sum(1 for s in scores if s >= MIN_SCORE)} de {total} {'✅' if all_ok else '⚠️'} |")
    lines.append("")

    # Nota individual
    lines.append("---\n")
    lines.append("## 📝 Nota Individual por Artigo\n")
    lines.append("| # | Título | Score | Retries | Status |")
    lines.append("|---|---|---|---|---|")
    for i, d in enumerate(batch_data):
        title = d.get('post_title', 'N/A')[:55]
        score = d.get('qa_score', 0)
        retries = d.get('heal_retries', 0)
        status = "✅ Aprovado" if score >= MIN_SCORE else "❌ Precisa revisão"
        lines.append(f"| {i+1} | {title} | {score}/100 | {retries} | {status} |")
    lines.append("")

    # Detalhamento por artigo
    for i, d in enumerate(batch_data):
        a = d.get('_analysis', {})
        lines.append("---\n")
        lines.append(f"## 🔍 Detalhamento — Artigo {i+1}: {d.get('post_title', 'N/A')}\n")

        # Metadados
        lines.append("### Metadados")
        lines.append("| Campo | Valor | Limite | OK? |")
        lines.append("|---|---|---|---|")
        mt_ok = "✅" if a.get('meta_title_len', 0) <= 60 else "❌"
        md_ok = "✅" if a.get('meta_desc_len', 0) <= 155 else "❌"
        h1_ok = "✅" if a.get('h1_len', 0) <= 60 else "❌"
        wc = a.get('word_count', 0)
        wc_ok = "✅" if 1200 <= wc <= 2500 else "⚠️"
        lines.append(f"| Meta Title | \"{d.get('meta_title', 'N/A')[:50]}\" | ≤60 chars | {mt_ok} {a.get('meta_title_len', 0)} chars |")
        lines.append(f"| Meta Description | \"{d.get('meta_description', 'N/A')[:50]}\" | ≤155 chars | {md_ok} {a.get('meta_desc_len', 0)} chars |")
        lines.append(f"| H1 | \"{a.get('h1', 'N/A')[:50]}\" | ≤60 chars | {h1_ok} {a.get('h1_len', 0)} chars |")
        lines.append(f"| Word Count | {wc:,} palavras | 1200-2500 | {wc_ok} |")
        lines.append("")

        # Checklist de qualidade
        lines.append(f"### Checklist de Qualidade (Score: {d.get('qa_score', 0)}/100)")
        lines.append("| Verificação | Resultado |")
        lines.append("|---|---|")
        lines.append(f"| `<article lang=\"pt-BR\">` | {'✅' if '<article lang=\"pt-BR\">' in str(d.get('post_content', '')) else '❌'} |")
        lines.append(f"| `<h1>` único | {'✅' if a.get('h1') != 'N/A' else '❌'} |")
        lines.append(f"| `<section class=\"faq-section\">` | {'✅' if a.get('has_faq_html') else '❌'} |")
        lines.append(f"| JSON-LD FAQPage | {'✅' if a.get('has_jsonld') else '❌'} |")
        lines.append(f"| Zero links `<a href>` | {'✅' if not re.search(r'<a href=', str(d.get('post_content', ''))) else '❌'} |")
        issues = d.get('_issues', [])
        lines.append(f"| **Issues** | {', '.join(issues) if issues else 'Nenhum ✅'} |")
        lines.append("")

        # Elementos de conteúdo rico
        lines.append("### Elementos de Conteúdo Rico")
        lines.append("| Elemento | Presente? |")
        lines.append("|---|---|")
        lines.append(f"| Tabela comparativa | {'✅' if a.get('has_table') else '❌'} |")
        lines.append(f"| Listas `<ul>/<ol>` | {'✅' if a.get('has_lists') else '❌'} |")
        lines.append(f"| FAQ (perguntas) | {'✅ ' + str(a.get('faq_count', 0)) + ' perguntas' if a.get('faq_count', 0) > 0 else '❌'} |")
        lines.append(f"| Abertura | {a.get('opening_type', 'N/A')} |")
        lines.append("")

        # Análise SEO
        lines.append("### Análise SEO")
        lines.append("| Métrica | Valor |")
        lines.append("|---|---|")
        lines.append(f"| Keyword primária | \"{a.get('primary_keywords', 'N/A')}\" |")
        density = a.get('keyword_density', 0)
        density_ok = "✅" if 0.5 <= density <= 4.0 else "⚠️"
        lines.append(f"| Densidade da keyword | {density}% {density_ok} |")
        lines.append(f"| Hierarquia headings | H1(1) → H2({a.get('h2_count', 0)}) → H3({a.get('h3_count', 0)}) |")
        lines.append(f"| Entidades detectadas ({a.get('entity_count', 0)}) | {', '.join(a.get('entities', []))} |")
        lines.append("")

        # Self-healing
        retries = d.get('heal_retries', 0)
        if retries == 0:
            lines.append(f"### Self-healing: Aprovado de primeira ✅\n")
        else:
            lines.append(f"### Self-healing: {retries} correção(ões) aplicadas\n")

    # Análise consolidada
    lines.append("---\n")
    lines.append("## 📈 Análise Consolidada\n")

    # SEO Global
    lines.append("### SEO Global")
    lines.append("| # | Keyword Primária | Densidade | Headings |")
    lines.append("|---|---|---|---|")
    for i, d in enumerate(batch_data):
        a = d.get('_analysis', {})
        lines.append(f"| {i+1} | {a.get('primary_keywords', 'N/A')[:30]} | {a.get('keyword_density', 0)}% | H2({a.get('h2_count', 0)}) H3({a.get('h3_count', 0)}) |")
    lines.append("")

    # Diversidade de aberturas
    lines.append("### Diversidade de Aberturas")
    lines.append("| Artigo | Tipo |")
    lines.append("|---|---|")
    for i, d in enumerate(batch_data):
        a = d.get('_analysis', {})
        lines.append(f"| {i+1} | {a.get('opening_type', 'N/A')} |")
    lines.append("")

    # Status final
    lines.append("---\n")
    if all_ok:
        lines.append(f"## ✅ Status Final: PRONTO PARA PRODUÇÃO")
        lines.append(f"Todos os {total} artigos atingiram score ≥{MIN_SCORE}.")
    else:
        failed = sum(1 for s in scores if s < MIN_SCORE)
        lines.append(f"## ⚠️ Status Final: {failed} ARTIGO(S) PRECISAM REVISÃO MANUAL")
    lines.append(f"\nArquivos: `{OUTPUT_DIR}/lote_{batch_num}_*.csv`")

    # Write report
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return report_path


def suggest_category(title, content):
    """Suggest a category name based on article title and content.
    Uses the same keyword mapping as orbit_publisher.py for consistency."""
    plain_text = re.sub(r'<[^>]+>', ' ', content).lower()
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


def main():
    parser = argparse.ArgumentParser(description="Orbit AI Content Engine v2 (CSV Batch + Self-Healing)")
    parser.add_argument("--api_key", help="Google Gemini API Key", required=True)
    parser.add_argument("--model", help="Specific Gemini Model Name", required=True)
    parser.add_argument("--csv_input", help="Path to CSV with topics", default=None)
    parser.add_argument("--start_batch", type=int, default=1, help="Start processing from this batch number")
    parser.add_argument("--max_batches", type=int, default=None, help="Maximum number of batches to process")
    args = parser.parse_args()

    print(f"{Colors.HEADER}=== ORBIT AI CONTENT ENGINE V2 (CSV BATCH + SELF-HEALING) ==={Colors.ENDC}")

    # 1. Setup
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    rules = load_json(RULES_PATH)
    genai.configure(api_key=args.api_key)
    model = genai.GenerativeModel(args.model)
    print(f"{Colors.OKCYAN}[INFO] Usando modelo: {args.model}{Colors.ENDC}")

    # Import validator
    from orbit_qa_validator import OrbitValidator
    validator = OrbitValidator()
    print(f"{Colors.OKCYAN}[INFO] Validator carregado (min score: {MIN_SCORE}){Colors.ENDC}")

    # 2. Find CSV input
    csv_path = args.csv_input
    if not csv_path:
        import glob
        candidates = sorted(glob.glob("relatorios/sugestao_temas_*.csv"), reverse=True)
        if candidates:
            csv_path = candidates[0]
        else:
            print(f"{Colors.FAIL}[ERRO] Nenhum CSV de temas encontrado. Rode orbit_topic_creator.py primeiro.{Colors.ENDC}")
            return

    # 3. Read Topics
    df_topics = pd.read_csv(csv_path)
    topics = []

    for index, row in df_topics.iterrows():
        t_pt = row.get('topic_pt')
        if pd.notna(t_pt) and str(t_pt).strip():
            topics.append(str(t_pt).strip())
            continue
        t_old = row.get('topic_es') or row.get('Localized_ES_Draft') or row.get('Original_PT')
        if pd.notna(t_old) and str(t_old).strip():
            topics.append(str(t_old).strip())

    print(f"{Colors.OKCYAN}[INFO] Carregados {len(topics)} temas de {csv_path}.{Colors.ENDC}")

    # 4. Batch Processing
    total_batches = (len(topics) + BATCH_SIZE - 1) // BATCH_SIZE
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    batches_processed = 0
    all_batch_data = []

    for b in range(args.start_batch - 1, total_batches):
        if args.max_batches and batches_processed >= args.max_batches:
            print(f"{Colors.OKCYAN}[INFO] Limite de batches atingido ({args.max_batches}). Parando.{Colors.ENDC}")
            break

        batch_num = b + 1
        start_idx = b * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(topics))
        current_batch_topics = topics[start_idx:end_idx]

        print(f"\n{Colors.HEADER}--- PROCESSANDO BATCH {batch_num}/{total_batches} (Temas {start_idx+1}-{end_idx}) ---{Colors.ENDC}")

        batch_data = []

        for i, topic in enumerate(current_batch_topics):
            global_idx = start_idx + i + 1
            print(f"{Colors.BOLD}[{global_idx}/{len(topics)}] Gerando:{Colors.ENDC} {topic[:55]}...")

            try:
                prompt = generate_prompt(topic, rules)
                response = model.generate_content(prompt)

                post_content, meta_title, meta_desc = parse_response(response.text)

                # Self-healing validation loop
                healed_content, final_score, retries, issues = self_heal(
                    model, post_content, topic, validator
                )

                # Analyze for report
                analysis = analyze_article(healed_content, meta_title, meta_desc)

                # Suggest category based on content
                cat_suggestion = suggest_category(topic, healed_content)

                row = {
                    'unique_import_id': f"Orbit_{global_idx}",
                    'post_title': topic,
                    'post_content': healed_content,
                    'post_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'post_author': '1',
                    'post_status': 'draft',
                    'language': 'pt-BR',
                    'meta_title': meta_title,
                    'meta_description': meta_desc,
                    'original_theme': topic,
                    'qa_score': final_score,
                    'heal_retries': retries,
                    'suggested_category': cat_suggestion,
                    '_analysis': analysis,
                    '_issues': [iss for iss in issues]
                }
                batch_data.append(row)

                score_color = Colors.OKGREEN if final_score >= MIN_SCORE else Colors.WARNING
                status_msg = f"Score: {final_score}/100"
                if retries > 0:
                    status_msg += f" (após {retries} correção(ões))"
                print(f"  -> {score_color}{status_msg}{Colors.ENDC}")
                time.sleep(2)

            except Exception as e:
                print(f"  -> {Colors.FAIL}ERRO: {e}{Colors.ENDC}")
                batch_data.append({
                    'post_title': topic,
                    'post_content': f"ERRO NA GERACAO: {str(e)}",
                    'post_status': 'error',
                    'qa_score': 0,
                    'heal_retries': 0,
                    '_analysis': {},
                    '_issues': [str(e)]
                })

        # Save Batch CSV (without internal fields)
        batch_filename = f"lote_{batch_num}_artigos_{start_idx+1}_a_{end_idx}.csv"
        batch_path = os.path.join(OUTPUT_DIR, batch_filename)

        csv_rows = []
        for d in batch_data:
            csv_row = {k: v for k, v in d.items() if not k.startswith('_')}
            csv_rows.append(csv_row)

        output_df = pd.DataFrame(csv_rows)
        output_df.to_csv(batch_path, index=False, quoting=csv.QUOTE_ALL)

        print(f"{Colors.OKBLUE}>> Batch {batch_num} salvo em {batch_path}{Colors.ENDC}")

        all_batch_data.extend(batch_data)
        batches_processed += 1

    # Generate production report
    if all_batch_data:
        report_path = generate_report(all_batch_data, batches_processed, args.model, timestamp)
        print(f"\n{Colors.OKGREEN}[REPORT] Relatório de produção gerado: {report_path}{Colors.ENDC}")

    print(f"\n{Colors.HEADER}=== TODOS OS BATCHES COMPLETOS ==={Colors.ENDC}")

if __name__ == "__main__":
    main()
