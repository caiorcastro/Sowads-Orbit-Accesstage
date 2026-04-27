#!/usr/bin/env python3
"""
preview_generator.py — Gera páginas HTML mock do blog Accesstage para aprovação.

Uso:
  python3 tools/preview_generator.py
  python3 tools/preview_generator.py --csv output/articles/lote_veragi_batch1_artigos_1_a_10.csv

Saída:
  output/preview/index.html          ← index com cards de todos os artigos
  output/preview/artigo_01_slug.html ← página individual por artigo
"""
import os, re, csv, sys, argparse, unicodedata
from datetime import datetime

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE     = os.path.join(BASE_DIR, "client", "html_template.html")
DEFAULT_CSV  = os.path.join(BASE_DIR, "output", "articles", "lote_veragi_batch1_artigos_1_a_10.csv")
OUT_DIR      = os.path.join(BASE_DIR, "output", "preview")

FALLBACK_IMG = "https://blog.accesstage.com.br/hubfs/ACC_BLOG_CTA-1.png"
AUTHOR_NAME  = "Equipe Accesstage"
AUTHOR_BIO   = "Time de conteúdo Accesstage"
AUTHOR_IMG   = "https://blog.accesstage.com.br/hs-fs/hubfs/raw_assets/public/access/images/logo-access.png?width=60"


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:60]


def reading_time(html):
    words = len(re.sub(r"<[^>]+>", " ", html).split())
    mins  = max(1, round(words / 200))
    return f"{mins} min."


def fmt_date(raw):
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
        return f"{dt.day} {meses[dt.month-1]} {dt.year}"
    except Exception:
        return raw or "2026"


def build_article_page(template: str, row: dict, idx: int) -> str:
    title       = row["post_title"].strip()
    meta_title  = row["meta_title"].strip() or title
    meta_desc   = row["meta_description"].strip()
    content     = row["post_content"].strip()
    img_url     = row["img_blog"].strip() or FALLBACK_IMG
    date_str    = fmt_date(row.get("post_date", ""))
    read_time   = reading_time(content)
    slug        = slugify(title)
    fake_url    = f"https://blog.accesstage.com.br/{slug}"

    html = template

    # ── <head> replacements ──────────────────────────────────────────────────
    html = re.sub(
        r"(<title>)[^<]*(</title>)",
        rf"\g<1>{meta_title} | Blog Accesstage\g<2>",
        html, count=1
    )
    html = re.sub(
        r'(<meta name="description"\s+content=")[^"]*(")',
        rf'\g<1>{meta_desc}\g<2>',
        html, count=1
    )
    for prop in ["og:description", "twitter:description"]:
        html = re.sub(
            rf'(<meta property="{prop}"\s+content="|<meta name="{prop}"\s+content=")[^"]*(")',
            rf'\g<1>{meta_desc}\g<2>',
            html, count=1
        )
    for prop in ["og:title", "twitter:title"]:
        html = re.sub(
            rf'(<meta property="{prop}"\s+content="|<meta name="{prop}"\s+content=")[^"]*(")',
            rf'\g<1>{meta_title}\g<2>',
            html, count=1
        )
    html = re.sub(
        r'(<link rel="canonical" href=")[^"]*(")',
        rf'\g<1>{fake_url}\g<2>',
        html, count=1
    )
    html = re.sub(
        r'(<meta property="og:url" content=")[^"]*(")',
        rf'\g<1>{fake_url}\g<2>',
        html, count=1
    )

    # ── H1 title ─────────────────────────────────────────────────────────────
    html = re.sub(
        r"(<h1>\s*)[^<]*(</h1>)",
        rf"\g<1>{title}\g<2>",
        html, count=1
    )

    # ── Reading time + date ───────────────────────────────────────────────────
    html = re.sub(
        r"(<div class=\"post-time\">)[^<]*(</div>)",
        rf"\g<1>Tempo de leitura: {read_time}\g<2>",
        html, count=1
    )
    html = re.sub(
        r"(<div class=\"post-data\">)<span>[^<]*</span>(\s*<span>[^<]*</span>)?(</div>)",
        rf"\g<1><span>Publicado em {date_str}</span>\g<3>",
        html, count=1
    )

    # ── Featured image ───────────────────────────────────────────────────────
    # Replace the complex data-srcset lazy-load img inside .post-img
    html = re.sub(
        r'(<div class="post-img">.*?)<img[^>]*>(.*?</div>)',
        rf'\g<1><img src="{img_url}" alt="{title}" class="img-fluid" style="width:100%;height:auto;border-radius:8px;">\g<2>',
        html, count=1, flags=re.DOTALL
    )

    # ── Article body ─────────────────────────────────────────────────────────
    # Replace everything between the opening and closing of post_body span
    html = re.sub(
        r'(<span id="hs_cos_wrapper_post_body"[^>]*>).*?(</span>(?=\s*<div class="post-author">))',
        rf'\g<1>\n{content}\n\g<2>',
        html, count=1, flags=re.DOTALL
    )

    # ── Author ───────────────────────────────────────────────────────────────
    # Replace author name links
    html = re.sub(
        r'(<h5>Por <a class="name-author"[^>]*>)[^<]*(</a></h5>)',
        rf'\g<1>{AUTHOR_NAME}\g<2>',
        html, count=1
    )
    html = re.sub(
        r'(<h5 class="post-author-name">Por )[^<]*(</h5>)',
        rf'\g<1>{AUTHOR_NAME} <br><span class="post-author-bio">{AUTHOR_BIO}</span></h5><!-- replaced -->',
        html, count=1
    )
    html = re.sub(r'(<h5 class="post-author-name">Por )[^<]*(</h5><!-- replaced -->)',
        rf'\g<1>{AUTHOR_NAME}\g<2>',
        html)

    # ── Audio player (remove for mock) ───────────────────────────────────────
    html = re.sub(
        r'<div id="hs_cos_wrapper_blog_post_audio".*?</div>\s*(?=<span id="hs_cos_wrapper_post_body")',
        '',
        html, count=1, flags=re.DOTALL
    )

    # ── Remove HubSpot CTA scripts (keep visual structure) ───────────────────
    html = re.sub(r'<script charset="utf-8" src="/hs/cta/[^"]*"[^>]*></script>', '', html)
    html = re.sub(r'<script type="text/javascript">\s*hbspt\.cta\._relativeUrls[^<]*</script>', '', html)

    # ── QA score badge (inject into header info) ─────────────────────────────
    qa_score = row.get("qa_score", "")
    if qa_score and qa_score != "0":
        score_color = "#22c55e" if int(qa_score) >= 90 else "#f59e0b"
        badge = (f'<span style="display:inline-block;margin-left:12px;padding:2px 10px;'
                 f'background:{score_color};color:#fff;border-radius:12px;font-size:12px;font-weight:600;">'
                 f'QA {qa_score}/100</span>')
        html = html.replace(f"Tempo de leitura: {read_time}</div>",
                            f"Tempo de leitura: {read_time} {badge}</div>", 1)

    # ── Preview notice bar (inject after <body>) ──────────────────────────────
    notice = (
        '<div style="background:#442357;color:#fff;text-align:center;padding:10px 16px;font-size:13px;'
        'font-family:sans-serif;position:sticky;top:0;z-index:9999;">'
        f'<strong>PREVIEW — Artigo {idx:02d}</strong> &nbsp;|&nbsp; '
        f'Score QA: <strong>{qa_score}/100</strong> &nbsp;|&nbsp; '
        f'Esta página é um mock para aprovação &nbsp;|&nbsp; '
        '<a href="index.html" style="color:#db8350;text-decoration:underline;">← Ver todos os artigos</a>'
        '</div>'
    )
    html = html.replace("<body>", f"<body>\n{notice}", 1)

    return html


def build_index(articles: list) -> str:
    cards = ""
    for a in articles:
        score = int(a["qa_score"] or 0)
        score_color = "#22c55e" if score >= 90 else "#f59e0b" if score >= 80 else "#ef4444"
        img = a["img_blog"] or FALLBACK_IMG
        fname = a["_filename"]
        title = a["post_title"]
        meta_desc = a["meta_description"][:120] + "..." if len(a["meta_description"]) > 120 else a["meta_description"]
        status = "✅ Pronto" if score >= 80 else ("⏳ Pendente" if score == 0 else "⚠️ Verificar")
        cards += f"""
    <div class="card">
      <a href="{fname}">
        <img src="{img}" alt="{title}" onerror="this.src='{FALLBACK_IMG}'">
        <div class="card-body">
          <span class="badge" style="background:{score_color};">QA {score}/100</span>
          <span class="status">{status}</span>
          <h3>{title}</h3>
          <p>{meta_desc}</p>
          <span class="read-more">Ler artigo →</span>
        </div>
      </a>
    </div>"""

    total = len(articles)
    ready = sum(1 for a in articles if int(a["qa_score"] or 0) >= 80)

    return f"""<!doctype html>
<html lang="pt">
<head>
<meta charset="utf-8">
<title>Preview de Artigos — Accesstage Blog | Sowads Orbit</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="shortcut icon" href="https://blog.accesstage.com.br/hubfs/cropped-cropped-Site_Accesstage_FAVICON.png">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"Open Sans",system-ui,sans-serif;background:#f1f6fc;color:#222}}
  .topbar{{background:#442357;color:#fff;padding:16px 32px;display:flex;justify-content:space-between;align-items:center}}
  .topbar a{{color:#db8350;text-decoration:none;font-weight:600}}
  .topbar img{{height:32px}}
  .hero{{background:linear-gradient(135deg,#442357,#dc1668);color:#fff;padding:48px 32px;text-align:center}}
  .hero h1{{font-size:2rem;margin-bottom:8px}}
  .hero p{{font-size:1rem;opacity:.85}}
  .summary{{display:flex;gap:24px;justify-content:center;margin-top:24px;flex-wrap:wrap}}
  .summary-box{{background:rgba(255,255,255,.15);border-radius:12px;padding:16px 28px;text-align:center}}
  .summary-box .num{{font-size:2rem;font-weight:700}}
  .summary-box .lbl{{font-size:.8rem;opacity:.8;text-transform:uppercase}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:24px;padding:40px 32px;max-width:1300px;margin:0 auto}}
  .card{{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);transition:transform .2s,box-shadow .2s}}
  .card:hover{{transform:translateY(-4px);box-shadow:0 8px 24px rgba(0,0,0,.14)}}
  .card a{{text-decoration:none;color:inherit;display:flex;flex-direction:column;height:100%}}
  .card img{{width:100%;height:180px;object-fit:cover}}
  .card-body{{padding:20px;display:flex;flex-direction:column;gap:8px;flex:1}}
  .badge{{display:inline-block;padding:3px 10px;border-radius:20px;color:#fff;font-size:11px;font-weight:700}}
  .status{{font-size:12px;color:#666}}
  .card-body h3{{font-size:1rem;font-weight:700;color:#442357;line-height:1.4;margin-top:4px}}
  .card-body p{{font-size:13px;color:#555;line-height:1.5;flex:1}}
  .read-more{{color:#dc1668;font-weight:600;font-size:13px;margin-top:8px}}
  footer{{text-align:center;padding:32px;color:#888;font-size:12px;border-top:1px solid #ddd;margin-top:16px}}
  @media(max-width:600px){{.grid{{padding:20px 16px}}.hero{{padding:32px 16px}}.hero h1{{font-size:1.4rem}}}}
</style>
</head>
<body>
<div class="topbar">
  <img src="https://blog.accesstage.com.br/hs-fs/hubfs/raw_assets/public/access/images/logo-access.png?width=200" alt="Accesstage">
  <span>Preview de Conteúdo &mdash; Sowads Orbit AI</span>
  <a href="https://site.accesstage.com.br/" target="_blank" rel="noopener">Visite o site →</a>
</div>
<div class="hero">
  <h1>Artigos Gerados para o Blog Accesstage</h1>
  <p>Preview para aprovação de conteúdo — Lote Veragi · Gerado em {datetime.now().strftime("%d/%m/%Y às %H:%M")}</p>
  <div class="summary">
    <div class="summary-box"><div class="num">{total}</div><div class="lbl">Artigos gerados</div></div>
    <div class="summary-box"><div class="num">{ready}</div><div class="lbl">Prontos (QA ≥ 80)</div></div>
    <div class="summary-box"><div class="num">{total - ready}</div><div class="lbl">Pendentes</div></div>
  </div>
</div>
<div class="grid">{cards}
</div>
<footer>Preview gerado automaticamente pela Sowads Orbit AI &mdash; Para uso interno e aprovação do cliente.<br>
Conteúdo &copy; Accesstage {datetime.now().year}</footer>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV)
    args = parser.parse_args()

    if not os.path.exists(TEMPLATE):
        print(f"Template não encontrado: {TEMPLATE}")
        sys.exit(1)
    if not os.path.exists(args.csv):
        print(f"CSV não encontrado: {args.csv}")
        sys.exit(1)

    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    os.makedirs(OUT_DIR, exist_ok=True)

    index_articles = []
    generated = 0
    skipped   = 0

    for idx, row in enumerate(rows, 1):
        score = int(row.get("qa_score", 0) or 0)
        title = row.get("post_title", "").strip()

        if score == 0 or not title or not row.get("post_content", "").strip():
            print(f"  [{idx:02d}] ⏭  Pulando (score={score}, sem conteúdo): {title[:50]}")
            skipped += 1
            row["_filename"] = "#"
            index_articles.append(row)
            continue

        slug     = slugify(title)
        filename = f"artigo_{idx:02d}_{slug}.html"
        filepath = os.path.join(OUT_DIR, filename)

        page = build_article_page(template, row, idx)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(page)

        row["_filename"] = filename
        index_articles.append(row)
        generated += 1
        print(f"  [{idx:02d}] ✅ {filename}  (score={score})")

    index_html = build_index(index_articles)
    index_path = os.path.join(OUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"\n✅ {generated} artigos gerados, {skipped} pulados")
    print(f"📂 Pasta: {OUT_DIR}")
    print(f"🌐 Abra: {index_path}")


if __name__ == "__main__":
    main()
