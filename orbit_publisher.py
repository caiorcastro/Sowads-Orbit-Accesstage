
import os
import csv
import json
import argparse
import glob
import re
import html
import xmlrpc.client
import requests
import pandas as pd
from datetime import datetime

# --- Configuration ---
OUTPUT_DIR = "output_csv_batches_v2"
REPORTS_DIR = "relatorios"

# Keyword mapping for intelligent category detection.
# Keys = category name; Values = list of keywords to match in title+content.
CATEGORY_KEYWORDS = {
    "SEO & AIO": [
        "seo", "aio", "otimização para buscas", "ranking", "serp",
        "indexação", "orgânico", "tráfego orgânico", "palavras-chave",
        "busca orgânica", "search engine", "google search", "rich results",
        "schema", "link building", "backlink", "autoridade de domínio",
        "otimização com ia", "inteligência artificial para seo",
        "ai optimization", "orbit ai"
    ],
    "Mídia Paga": [
        "meta ads", "mídia paga", "tráfego pago", "anúncios pagos",
        "facebook ads", "instagram ads", "google ads", "cpc", "cpm",
        "cpa", "roas", "campanha paga", "gestão de tráfego",
        "remarketing", "retargeting", "lookalike", "público semelhante",
        "orçamento de mídia", "lance", "leilão de anúncios"
    ],
    "Data e Analytics": [
        "analytics", "métricas", "kpi", "dashboard", "google analytics",
        "tag manager", "pixel", "atribuição", "funil de conversão",
        "taxa de conversão", "bounce rate", "taxa de rejeição",
        "data-driven", "business intelligence", "relatório de dados",
        "performance de dados", "looker", "data studio"
    ],
    "Conteúdo": [
        "marketing de conteúdo", "copywriting", "storytelling",
        "calendário editorial", "blog corporativo", "redação publicitária",
        "branded content", "inbound marketing", "lead magnet",
        "e-book", "whitepaper", "infográfico", "webinar",
        "estratégia de conteúdo", "content marketing"
    ],
    "Estratégia e Performance": [
        "estratégia digital", "performance", "growth", "escalabilidade",
        "planejamento estratégico", "transformação digital",
        "funil de vendas", "jornada do cliente", "omnichannel",
        "branding", "posicionamento", "market fit"
    ]
}

# Fallback category when no keyword match is found
FALLBACK_CATEGORY = "Estratégia e Performance"


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def get_xmlrpc_client(wp_url):
    """Create XML-RPC client for WordPress."""
    xmlrpc_url = f"{wp_url}/xmlrpc.php"
    return xmlrpc.client.ServerProxy(xmlrpc_url)


def fetch_wp_categories(wp_url, wp_user=None, wp_pass=None):
    """Fetch all categories from WordPress.

    Tries REST API first (public, no auth needed).
    Falls back to XML-RPC if REST API returns HTML-encoded names.

    Returns:
        dict: {category_name: {id, slug, count, parent}} mapping
    """
    categories = {}

    # Try XML-RPC if credentials available (more reliable)
    if wp_user and wp_pass:
        try:
            server = get_xmlrpc_client(wp_url)
            cats = server.wp.getTerms(1, wp_user, wp_pass, 'category')
            for cat in cats:
                cat_name = html.unescape(cat['name'])
                categories[cat_name] = {
                    'id': int(cat['term_id']),
                    'slug': cat.get('slug', ''),
                    'count': int(cat.get('count', 0)),
                    'parent': int(cat.get('parent', 0))
                }
            return categories
        except Exception as e:
            print(f"{Colors.WARNING}XML-RPC fallback falhou: {e}{Colors.ENDC}")

    # Fallback: REST API (public, no auth)
    api_url = f"{wp_url}/wp-json/wp/v2/categories"
    page = 1
    while True:
        try:
            response = requests.get(api_url, params={'per_page': 100, 'page': page}, timeout=15)
            if response.status_code != 200:
                break
            data = response.json()
            if not data:
                break
            for cat in data:
                cat_name = html.unescape(cat['name'])
                categories[cat_name] = {
                    'id': cat['id'],
                    'slug': cat['slug'],
                    'count': cat['count'],
                    'parent': cat.get('parent', 0)
                }
            total_pages = int(response.headers.get('X-WP-TotalPages', 1))
            if page >= total_pages:
                break
            page += 1
        except Exception as e:
            print(f"{Colors.WARNING}Erro buscando categorias: {e}{Colors.ENDC}")
            break

    return categories


def detect_category(title, content, categories_map):
    """Intelligently detect the best category for an article.

    Scores each active category by counting keyword matches in the
    article title and content. Returns the highest-scoring category.

    Args:
        title: Article title
        content: Article HTML content
        categories_map: Dict from fetch_wp_categories()

    Returns:
        tuple: (category_id, category_name)
    """
    # Strip HTML tags for cleaner matching
    plain_text = re.sub(r'<[^>]+>', ' ', content).lower()
    title_lower = title.lower()
    # Weight title 3x for category relevance
    search_text = f"{title_lower} {title_lower} {title_lower} {plain_text}"

    # Score each category
    scores = {}
    for cat_name, keywords in CATEGORY_KEYWORDS.items():
        if cat_name not in categories_map:
            continue
        score = 0
        for kw in keywords:
            count = search_text.count(kw.lower())
            if count > 0:
                weight = len(kw.split())
                score += count * weight
        scores[cat_name] = score

    # Pick highest score
    if scores:
        best = max(scores, key=scores.get)
        if scores[best] > 0:
            return categories_map[best]['id'], best

    # Fallback
    if FALLBACK_CATEGORY in categories_map:
        return categories_map[FALLBACK_CATEGORY]['id'], FALLBACK_CATEGORY

    first_cat = next(iter(categories_map))
    return categories_map[first_cat]['id'], first_cat


def cleanup_unused_categories(wp_url, wp_user, wp_pass, categories_map, dry_run=False):
    """Delete categories with zero posts from WordPress via XML-RPC.

    Args:
        wp_url: WordPress site URL
        wp_user: WordPress username
        wp_pass: WordPress password
        categories_map: Dict from fetch_wp_categories()
        dry_run: If True, only list what would be deleted

    Returns:
        list: Names of deleted categories
    """
    deleted = []
    skip_names = {"Uncategorized"}

    server = get_xmlrpc_client(wp_url)

    for name, info in categories_map.items():
        if info['count'] == 0 and name not in skip_names:
            if dry_run:
                print(f"  [DRY-RUN] Deletaria: {name} (ID: {info['id']})")
                deleted.append(name)
                continue

            try:
                result = server.wp.deleteTerm(1, wp_user, wp_pass, 'category', info['id'])
                if result:
                    print(f"  {Colors.OKGREEN}Deletada: {name} (ID: {info['id']}){Colors.ENDC}")
                    deleted.append(name)
                else:
                    print(f"  {Colors.WARNING}Falha ao deletar {name}{Colors.ENDC}")
            except Exception as e:
                print(f"  {Colors.WARNING}Erro deletando {name}: {e}{Colors.ENDC}")

    return deleted


def get_media_id_by_url(wp_url, wp_user, wp_pass, img_url):
    """Look up WordPress media attachment ID from a URL using REST API."""
    if not img_url or not img_url.startswith("http"):
        return None
    try:
        filename = img_url.split("/")[-1].rsplit(".", 1)[0]  # slug without extension
        api_url = f"{wp_url}/wp-json/wp/v2/media"
        resp = requests.get(
            api_url,
            params={"search": filename, "per_page": 10, "_fields": "id,source_url"},
            auth=(wp_user, wp_pass),
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        for item in resp.json():
            if item.get("source_url", "").split("?")[0] == img_url.split("?")[0]:
                return item["id"]
    except Exception:
        pass
    return None


def set_featured_image(wp_url, wp_user, wp_pass, post_id, media_id):
    """Set the featured image (post thumbnail) of a WordPress post via XML-RPC."""
    try:
        server = get_xmlrpc_client(wp_url)
        server.wp.editPost(1, wp_user, wp_pass, post_id, {"post_thumbnail": str(media_id)})
        return True
    except Exception:
        return False


def list_draft_articles(input_dir):
    """List all draft articles from CSV files."""
    csv_files = sorted(glob.glob(f"{input_dir}/*.csv"))
    all_drafts = []

    for file_path in csv_files:
        try:
            df = pd.read_csv(file_path)
            for idx, row in df.iterrows():
                status = str(row.get('post_status', '')).strip().lower()
                if status in ['draft', 'rascunho']:
                    content = str(row.get('post_content', ''))
                    if len(content) > 100 and 'ERRO' not in content:
                        all_drafts.append({
                            'file': file_path,
                            'file_idx': idx,
                            'title': str(row.get('post_title', 'Sem titulo')),
                            'meta_title': str(row.get('meta_title', '')),
                            'meta_desc': str(row.get('meta_description', '')),
                            'content': content,
                            'qa_score': row.get('qa_score', 'N/A'),
                            'date': str(row.get('post_date', '')),
                            'original_theme': str(row.get('original_theme', '')),
                            'suggested_category': str(row.get('suggested_category', '')),
                            'img_blog': str(row.get('img_blog', '')).strip(),
                        })
        except Exception as e:
            print(f"{Colors.WARNING}Erro lendo {file_path}: {e}{Colors.ENDC}")

    return all_drafts


def publish_to_wordpress(wp_url, wp_user, wp_pass, article, publish_status='draft', categories=None):
    """Publish article to WordPress via XML-RPC, with featured image if img_blog is set."""
    server = get_xmlrpc_client(wp_url)

    title = article['meta_title'] if article.get('meta_title') else article['title']
    content = article['content']

    post_data = {
        'post_type': 'post',
        'post_status': publish_status,
        'post_title': title,
        'post_content': content,
    }

    if categories:
        post_data['terms'] = {'category': categories}

    custom_fields = []
    if article.get('meta_title'):
        custom_fields.append({'key': '_yoast_wpseo_title', 'value': article['meta_title']})
        custom_fields.append({'key': 'rank_math_title', 'value': article['meta_title']})
    if article.get('meta_desc'):
        custom_fields.append({'key': '_yoast_wpseo_metadesc', 'value': article['meta_desc']})
        custom_fields.append({'key': 'rank_math_description', 'value': article['meta_desc']})
    if custom_fields:
        post_data['custom_fields'] = custom_fields

    try:
        post_id = server.wp.newPost(1, wp_user, wp_pass, post_data)
        post_info = server.wp.getPost(1, wp_user, wp_pass, int(post_id), ['link', 'post_status'])
        link = post_info.get('link', '')

        # Set featured image
        img_url = article.get('img_blog', '')
        featured_set = False
        if img_url and img_url.startswith('http'):
            media_id = get_media_id_by_url(wp_url, wp_user, wp_pass, img_url)
            if media_id:
                featured_set = set_featured_image(wp_url, wp_user, wp_pass, int(post_id), media_id)

        return {
            'success': True,
            'post_id': int(post_id),
            'link': link,
            'status': post_info.get('post_status', publish_status),
            'featured_image': 'ok' if featured_set else ('sem_url' if not img_url else 'nao_encontrada'),
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def mark_as_published(file_path, file_idx, post_id):
    """Update CSV to mark article as published."""
    try:
        df = pd.read_csv(file_path)
        df.loc[file_idx, 'post_status'] = 'published'
        df.loc[file_idx, 'wp_post_id'] = post_id
        df.loc[file_idx, 'published_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.to_csv(file_path, index=False, quoting=csv.QUOTE_ALL)
    except Exception as e:
        print(f"{Colors.WARNING}Erro atualizando CSV: {e}{Colors.ENDC}")


def generate_publish_report(results, timestamp):
    """Generate publish report."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"report_publicacao_{timestamp}.md")

    lines = []
    lines.append("# Orbit AI -- Relatorio de Publicacao\n")
    lines.append(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    success = sum(1 for r in results if r['success'])
    failed = sum(1 for r in results if not r['success'])

    lines.append("## Resumo\n")
    lines.append("| Metrica | Valor |")
    lines.append("|---|---|")
    lines.append(f"| Total publicados | {success} |")
    lines.append(f"| Falhas | {failed} |")
    lines.append("")

    lines.append("## Detalhamento\n")
    lines.append("| # | Titulo | Score QA | Categoria | Status | Post ID | Link |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, r in enumerate(results):
        cat = r.get('category_name', 'N/A')
        if r['success']:
            lines.append(f"| {i+1} | {r['title'][:45]} | {r.get('qa_score', 'N/A')} | {cat} | Publicado | {r.get('post_id', '')} | {r.get('link', '')} |")
        else:
            lines.append(f"| {i+1} | {r['title'][:45]} | {r.get('qa_score', 'N/A')} | {cat} | ERRO | - | {r.get('error', '')[:50]} |")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return report_path


def main():
    parser = argparse.ArgumentParser(description="Orbit AI WordPress Publisher")
    parser.add_argument("--wp_url", default="https://sowads.com.br", help="WordPress site URL")
    parser.add_argument("--wp_user", default=None, help="WordPress username (or set WP_USER env var)")
    parser.add_argument("--wp_pass", default=None, help="WordPress app password (or set WP_PASS env var)")
    parser.add_argument("--input_dir", default=OUTPUT_DIR, help="Directory with CSV files")
    parser.add_argument("--publish", action='store_true', help="Publish as 'publish' instead of 'draft'")
    parser.add_argument("--all", action='store_true', help="Publish all drafts without asking")
    parser.add_argument("--list", action='store_true', help="Only list drafts, don't publish")
    parser.add_argument("--category_id", type=int, default=None, help="Override category ID for all articles")
    parser.add_argument("--no_category", action='store_true', help="Skip automatic category assignment")
    parser.add_argument("--cleanup_categories", action='store_true', help="Delete unused categories (0 posts)")
    parser.add_argument("--dry_run", action='store_true', help="Show what would be done without making changes")
    parser.add_argument("--test_one", action='store_true', help="Publica apenas o primeiro artigo para validacao manual")
    args = parser.parse_args()

    # Get credentials from args or env vars
    wp_user = args.wp_user or os.environ.get('WP_USER')
    wp_pass = args.wp_pass or os.environ.get('WP_PASS')

    print(f"{Colors.HEADER}=== ORBIT AI WORDPRESS PUBLISHER ==={Colors.ENDC}")
    print(f"Site: {args.wp_url}")
    print(f"Input: {args.input_dir}")

    # Fetch WordPress categories
    print(f"\n{Colors.OKCYAN}Buscando categorias do WordPress...{Colors.ENDC}")
    categories_map = fetch_wp_categories(args.wp_url, wp_user, wp_pass)
    if categories_map:
        active = [(n, c) for n, c in categories_map.items() if c['count'] > 0]
        active_str = ', '.join(f"{n} ({c['count']}p)" for n, c in active)
        print(f"  Categorias ativas: {active_str}")
    else:
        print(f"  {Colors.WARNING}Nao foi possivel buscar categorias.{Colors.ENDC}")

    # Cleanup unused categories
    if args.cleanup_categories:
        if not wp_user or not wp_pass:
            print(f"\n{Colors.FAIL}Credenciais necessarias para deletar categorias.{Colors.ENDC}")
            return
        print(f"\n{Colors.HEADER}Limpando categorias sem uso...{Colors.ENDC}")
        deleted = cleanup_unused_categories(args.wp_url, wp_user, wp_pass, categories_map, dry_run=args.dry_run)
        if deleted:
            print(f"\n  {Colors.OKGREEN}Removidas {len(deleted)} categorias sem uso.{Colors.ENDC}")
        else:
            print(f"  Nenhuma categoria para remover.")
        if not args.list and not args.all:
            return

    # List all draft articles
    drafts = list_draft_articles(args.input_dir)

    if not drafts:
        print(f"\n{Colors.WARNING}Nenhum artigo em rascunho encontrado em {args.input_dir}/{Colors.ENDC}")
        return

    # Detect categories for each draft
    for d in drafts:
        if args.category_id:
            cat_id = args.category_id
            cat_name = next((n for n, c in categories_map.items() if c['id'] == cat_id), f"ID:{cat_id}")
        elif args.no_category:
            cat_id = None
            cat_name = "-"
        elif d.get('suggested_category') and d['suggested_category'] in categories_map:
            cat_id = categories_map[d['suggested_category']]['id']
            cat_name = d['suggested_category']
        elif categories_map:
            cat_id, cat_name = detect_category(d['title'], d['content'], categories_map)
        else:
            cat_id = None
            cat_name = "-"
        d['detected_category_id'] = cat_id
        d['detected_category_name'] = cat_name

    # Display drafts
    print(f"\n{Colors.OKCYAN}Encontrados {len(drafts)} artigos em rascunho:{Colors.ENDC}\n")
    print(f"{'#':<4} {'Score':<8} {'Categoria':<25} {'Titulo'}")
    print("-" * 100)
    for i, d in enumerate(drafts):
        score = d.get('qa_score', 'N/A')
        cat = d.get('detected_category_name', '-')
        title = d['title'][:55]
        print(f"{i+1:<4} {str(score):<8} {cat:<25} {title}")

    if args.list:
        print(f"\n{Colors.OKCYAN}Modo lista. Use --all ou selecione artigos para publicar.{Colors.ENDC}")
        return

    if not wp_user or not wp_pass:
        print(f"\n{Colors.FAIL}Credenciais nao fornecidas. Use --wp_user/--wp_pass ou defina WP_USER/WP_PASS.{Colors.ENDC}")
        return

    # Selection
    if args.test_one:
        selected = [0]
        print(f"\n{Colors.WARNING}[TEST_ONE] Publicando apenas o primeiro artigo para validacao.{Colors.ENDC}")
    elif args.all:
        selected = list(range(len(drafts)))
    else:
        print(f"\n{Colors.BOLD}Quais artigos publicar? (ex: 1,3,5 ou 'all' para todos){Colors.ENDC}")
        selection = input("> ").strip()
        if selection.lower() == 'all':
            selected = list(range(len(drafts)))
        else:
            try:
                selected = [int(x.strip()) - 1 for x in selection.split(',')]
            except ValueError:
                print(f"{Colors.FAIL}Selecao invalida.{Colors.ENDC}")
                return

    # Publish
    publish_status = 'publish' if args.publish else 'draft'
    print(f"\n{Colors.HEADER}Publicando {len(selected)} artigos como '{publish_status}'...{Colors.ENDC}\n")

    results = []
    for pos, idx in enumerate(selected):
        if idx < 0 or idx >= len(drafts):
            continue

        article = drafts[idx]
        cat_name = article.get('detected_category_name', '-')
        cat_id = article.get('detected_category_id')
        categories = [cat_id] if cat_id else None

        print(f"  [{pos+1}/{len(selected)}] {article['title'][:45]}... [{cat_name}]", end=" ")

        if args.dry_run:
            print(f"{Colors.OKCYAN}[DRY-RUN]{Colors.ENDC}")
            results.append({
                'success': True, 'title': article['title'],
                'qa_score': article.get('qa_score', 'N/A'),
                'category_name': cat_name, 'post_id': 'DRY', 'link': '-'
            })
            continue

        result = publish_to_wordpress(args.wp_url, wp_user, wp_pass, article, publish_status, categories)
        result['title'] = article['title']
        result['qa_score'] = article.get('qa_score', 'N/A')
        result['category_name'] = cat_name

        if result['success']:
            img_status = result.get('featured_image', '?')
            img_icon = '🖼️' if img_status == 'ok' else '⚠️ sem imagem'
            print(f"{Colors.OKGREEN}OK (ID: {result['post_id']}) {img_icon}{Colors.ENDC}")
            mark_as_published(article['file'], article['file_idx'], result['post_id'])
        else:
            print(f"{Colors.FAIL}ERRO: {result['error'][:60]}{Colors.ENDC}")

        results.append(result)

    # Report
    if results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        report_path = generate_publish_report(results, timestamp)
        print(f"\n{Colors.OKGREEN}[REPORT] Relatorio de publicacao: {report_path}{Colors.ENDC}")

    success_count = sum(1 for r in results if r['success'])
    print(f"\n{Colors.HEADER}=== PUBLICACAO COMPLETA: {success_count}/{len(results)} ==={Colors.ENDC}")


if __name__ == "__main__":
    main()
