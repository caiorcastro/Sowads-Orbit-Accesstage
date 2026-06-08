#!/usr/bin/env python3
"""
generate_hubspot_kit.py — Gera fichas de publicação para upload manual no HubSpot.

Uso:
  python3 tools/generate_hubspot_kit.py --csv output/articles/<batch>.csv
  python3 tools/generate_hubspot_kit.py --all   # todos os CSVs de artigos publicáveis
"""
import os, re, csv, argparse, unicodedata, glob, shutil

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR    = os.path.join(BASE_DIR, "output", "hubspot-kit")
IMAGES_DIR = os.path.join(BASE_DIR, "output", "images")

CATEGORY_MAP = {
    "SEO & AIO":                "SEO e AI-SEO",
    "Conteúdo":                 "Conteúdo em Escala",
    "Estratégia e Performance": "Estratégia e Performance",
    "Mídia Paga":               "Mídia Paga",
    "Data e Analytics":         "Dados e Analytics",
}

def slugify(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:60]

def clean_content(html):
    # Remove wrapper <article> se existir
    html = re.sub(r'^<article[^>]*>\s*', '', html.strip())
    html = re.sub(r'\s*</article>\s*$', '', html)
    return html.strip()

def generate_ficha(idx, total, row, out_dir):
    title        = row.get("post_title", "").strip()
    content      = clean_content(row.get("post_content", ""))
    meta_desc    = row.get("meta_description", "").strip()
    meta_title   = row.get("meta_title", title).strip()
    category_raw = row.get("original_theme", "").strip()
    category     = CATEGORY_MAP.get(category_raw, category_raw)
    qa_score     = row.get("qa_score", "—")
    slug         = slugify(title)

    # Imagem: busca PNG correspondente
    img_path = os.path.join(IMAGES_DIR, f"{slug}.png")
    img_name = f"{slug}.png" if os.path.exists(img_path) else "— imagem não encontrada —"
    has_img  = os.path.exists(img_path)

    # Copia imagem para output/hubspot-kit/images/
    if has_img:
        img_kit_dir = os.path.join(out_dir, "images")
        os.makedirs(img_kit_dir, exist_ok=True)
        shutil.copy2(img_path, os.path.join(img_kit_dir, f"{slug}.png"))

    # Escape HTML para exibir no bloco de código
    def esc(s):
        return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

    filename = f"artigo_{idx:02d}_{slug}.html"
    filepath = os.path.join(out_dir, filename)

    html = f"""<!doctype html>
<html lang="pt">
<head>
<meta charset="utf-8">
<title>#{idx:02d} — {esc(title)}</title>
<meta name="robots" content="noindex,nofollow">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"Segoe UI",system-ui,sans-serif;background:#f4f5f7;color:#1a1a2e;padding:32px 0 60px}}
  .wrap{{max-width:860px;margin:0 auto;padding:0 24px}}
  .header{{background:#1a1a2e;color:#fff;border-radius:12px;padding:20px 28px;margin-bottom:24px;display:flex;align-items:center;gap:16px}}
  .badge{{background:#7c3aed;color:#fff;font-size:.75rem;font-weight:700;padding:4px 12px;border-radius:20px;white-space:nowrap}}
  .badge-ok{{background:#16a34a}}
  .header h1{{font-size:1rem;font-weight:400;color:#aaa;flex:1}}
  .counter{{font-size:.8rem;color:#666;margin-left:auto}}
  .field{{background:#fff;border-radius:10px;padding:20px 24px;margin-bottom:16px;border:1px solid #e2e4ea;position:relative}}
  .field-label{{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#7c3aed;margin-bottom:8px;display:flex;align-items:center;gap:8px}}
  .field-label .hint{{font-weight:400;text-transform:none;letter-spacing:0;color:#999;font-size:.7rem}}
  .field-value{{font-size:1rem;line-height:1.55;color:#1a1a2e}}
  .field-value.large{{font-size:1.15rem;font-weight:600;line-height:1.4}}
  .copy-btn{{position:absolute;top:16px;right:16px;background:#7c3aed;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;font-weight:600;cursor:pointer;transition:background .15s}}
  .copy-btn:hover{{background:#6d28d9}}
  .copy-btn.copied{{background:#16a34a}}
  .meta-row{{display:flex;gap:12px;flex-wrap:wrap}}
  .meta-row .field{{flex:1;min-width:200px}}
  .img-field{{display:flex;align-items:flex-start;gap:20px}}
  .img-thumb{{width:180px;min-width:180px;border-radius:8px;border:1px solid #e2e4ea;object-fit:cover}}
  .img-info{{flex:1}}
  .img-filename{{font-family:monospace;font-size:.85rem;background:#f4f5f7;padding:6px 10px;border-radius:6px;display:inline-block;margin-bottom:8px;color:#374151}}
  .content-area{{font-family:monospace;font-size:.8rem;line-height:1.6;background:#f8f9fb;border:1px solid #e2e4ea;border-radius:8px;padding:16px;max-height:320px;overflow-y:auto;white-space:pre-wrap;word-break:break-word;color:#374151}}
  .nav{{display:flex;justify-content:space-between;align-items:center;margin-top:28px}}
  .nav a{{background:#1a1a2e;color:#fff;text-decoration:none;padding:10px 20px;border-radius:8px;font-size:.85rem;font-weight:600}}
  .nav a:hover{{background:#7c3aed}}
  .nav .disabled{{background:#e2e4ea;color:#999;pointer-events:none}}
  .divider{{height:1px;background:#e2e4ea;margin:6px 0 16px}}
  @media(max-width:600px){{.meta-row{{flex-direction:column}}.img-field{{flex-direction:column}}.img-thumb{{width:100%}}}}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <span class="badge">Accesstage · Veragi</span>
    <h1>Ficha de Publicação — HubSpot Blog</h1>
    <span class="counter">{idx} de {total}</span>
    <span class="badge badge-ok">QA {qa_score}/100</span>
  </div>

  <!-- TÍTULO -->
  <div class="field">
    <div class="field-label">Título do Post <span class="hint">→ campo "Title" no HubSpot</span></div>
    <div class="field-value large" id="f-title">{esc(title)}</div>
    <button class="copy-btn" onclick="copyField('f-title', this)">Copiar</button>
  </div>

  <!-- META TITLE + META DESCRIPTION -->
  <div class="meta-row">
    <div class="field">
      <div class="field-label">Meta Title <span class="hint">→ SEO → Page title</span></div>
      <div class="field-value" id="f-meta-title">{esc(meta_title)}</div>
      <button class="copy-btn" onclick="copyField('f-meta-title', this)">Copiar</button>
    </div>
    <div class="field">
      <div class="field-label">Meta Description <span class="hint">→ SEO → Meta description</span></div>
      <div class="field-value" id="f-meta-desc">{esc(meta_desc)}</div>
      <button class="copy-btn" onclick="copyField('f-meta-desc', this)">Copiar</button>
    </div>
  </div>

  <!-- CATEGORIA + AUTOR -->
  <div class="meta-row">
    <div class="field">
      <div class="field-label">Categoria <span class="hint">→ Topic / Category</span></div>
      <div class="field-value" id="f-cat">{esc(category)}</div>
      <button class="copy-btn" onclick="copyField('f-cat', this)">Copiar</button>
    </div>
    <div class="field">
      <div class="field-label">Autor</div>
      <div class="field-value" id="f-author">Sowads Orbit AI</div>
      <button class="copy-btn" onclick="copyField('f-author', this)">Copiar</button>
    </div>
  </div>

  <!-- IMAGEM DESTACADA -->
  <div class="field">
    <div class="field-label">Imagem Destacada <span class="hint">→ Featured image — arquivo na pasta images/</span></div>
    <div class="img-field">
      {"<img class='img-thumb' src='images/" + slug + ".png' alt='" + esc(title) + "'>" if has_img else "<div style='width:180px;min-width:180px;height:101px;background:#f4f5f7;border-radius:8px;border:1px dashed #ccc;display:flex;align-items:center;justify-content:center;color:#999;font-size:.75rem'>sem imagem</div>"}
      <div class="img-info">
        <div class="img-filename">{img_name}</div>
        <div style="font-size:.8rem;color:#666;line-height:1.5">Fazer upload desta imagem no HubSpot como Featured Image do post.<br>Arquivo está na pasta <strong>images/</strong> junto com esta ficha.</div>
      </div>
    </div>
  </div>

  <!-- CONTEÚDO -->
  <div class="field">
    <div class="field-label">Conteúdo HTML <span class="hint">→ colar no editor: ícone "&lt;&gt;" → Source code</span></div>
    <div class="divider"></div>
    <div class="content-area" id="f-content">{esc(content)}</div>
    <button class="copy-btn" style="top:auto;bottom:16px" onclick="copyField('f-content', this)">Copiar HTML</button>
  </div>

  <!-- NAVEGAÇÃO -->
  <div class="nav">
    {"<a href='artigo_" + f"{idx-1:02d}_{slugify(title)}" + ".html'>← Artigo " + str(idx-1) + "</a>" if idx > 1 else "<span class='disabled'>← Início</span>"}
    <span style="font-size:.8rem;color:#999">{idx} / {total}</span>
    {"<a href='artigo_" + f"{idx+1:02d}" + "_próximo.html'>Artigo " + str(idx+1) + " →</a>" if idx < total else "<span class='disabled'>Fim →</span>"}
  </div>

</div>
<script>
function copyField(id, btn) {{
  const el = document.getElementById(id);
  const text = el.innerText || el.textContent;
  navigator.clipboard.writeText(text).then(() => {{
    btn.textContent = '✓ Copiado!';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = id === 'f-content' ? 'Copiar HTML' : 'Copiar'; btn.classList.remove('copied'); }}, 2000);
  }});
}}
</script>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    return filename


def generate_index(articles, out_dir):
    rows_html = ""
    for idx, (filename, title, category, qa, has_img) in enumerate(articles, 1):
        img_icon = "🖼" if has_img else "⚠️"
        rows_html += f"""
    <tr>
      <td style="text-align:center;color:#999">{idx}</td>
      <td><a href="{filename}">{title}</a></td>
      <td>{category}</td>
      <td style="text-align:center">{qa}</td>
      <td style="text-align:center">{img_icon}</td>
      <td style="text-align:center"><a href="{filename}" style="background:#7c3aed;color:#fff;padding:4px 12px;border-radius:6px;font-size:.75rem;font-weight:600;text-decoration:none">Abrir</a></td>
    </tr>"""

    html = f"""<!doctype html>
<html lang="pt">
<head>
<meta charset="utf-8">
<title>Kit HubSpot — Accesstage · Veragi</title>
<meta name="robots" content="noindex,nofollow">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"Segoe UI",system-ui,sans-serif;background:#f4f5f7;color:#1a1a2e;padding:40px 24px}}
  .wrap{{max-width:900px;margin:0 auto}}
  h1{{font-size:1.5rem;font-weight:700;margin-bottom:6px}}
  .sub{{color:#666;font-size:.9rem;margin-bottom:28px}}
  .instructions{{background:#fff;border:1px solid #e2e4ea;border-radius:10px;padding:20px 24px;margin-bottom:28px;font-size:.85rem;line-height:1.7;color:#374151}}
  .instructions strong{{color:#7c3aed}}
  table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;border:1px solid #e2e4ea}}
  th{{background:#1a1a2e;color:#fff;padding:10px 14px;font-size:.75rem;text-align:left;font-weight:600;text-transform:uppercase;letter-spacing:.05em}}
  td{{padding:10px 14px;font-size:.85rem;border-bottom:1px solid #f0f1f5}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#fafafa}}
  td a{{color:#7c3aed;text-decoration:none;font-weight:500}}
  td a:hover{{text-decoration:underline}}
</style>
</head>
<body>
<div class="wrap">
  <h1>Kit de Publicação — HubSpot Blog</h1>
  <p class="sub">Accesstage · Plataforma Veragi · {len(articles)} artigos · gerado por Sowads Orbit AI</p>

  <div class="instructions">
    <strong>Como usar:</strong><br>
    1. Abra o HubSpot → Marketing → Blog → <em>Create blog post</em><br>
    2. Clique em qualquer artigo abaixo para abrir a ficha de publicação<br>
    3. Copie cada campo com o botão <strong>Copiar</strong> e cole no campo correspondente do HubSpot<br>
    4. Para o conteúdo: no editor HubSpot clique em <strong>&lt;&gt; Source code</strong> e cole o HTML<br>
    5. Para a imagem: clique em <strong>Featured image</strong> → <em>Upload</em> → selecione o arquivo da pasta <strong>images/</strong>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:36px">#</th>
        <th>Título</th>
        <th>Categoria</th>
        <th style="width:60px;text-align:center">QA</th>
        <th style="width:48px;text-align:center">Img</th>
        <th style="width:80px;text-align:center">Ficha</th>
      </tr>
    </thead>
    <tbody>{rows_html}
    </tbody>
  </table>
</div>
</body>
</html>"""

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="CSV de artigos")
    parser.add_argument("--all", action="store_true", help="Todos os CSVs de artigos publicáveis")
    parser.add_argument("--output_dir", default=OUT_DIR)
    args = parser.parse_args()

    if args.all:
        csvs = sorted(["output/articles/lote_veragi_batch3_claude-opus-4-7_batch1_artigos_1_a_10.csv","output/articles/lote_veragi_batch4_claude-opus-4-7_batch1_artigos_1_a_20.csv","output/articles/lote_veragi_batch4_claude-opus-4-7_batch2_artigos_21_a_30.csv","output/articles/lote_veragi_opus-4-7_todos_artigos_1_a_20.csv"])
        csvs = [c for c in csvs if "_bak" not in c and "_temas" not in c and "_retry" not in c]
    elif args.csv:
        csvs = [args.csv]
    else:
        print("Informe --csv <arquivo> ou --all")
        return

    # Coletar todos os artigos
    all_rows = []
    for path in csvs:
        with open(path, newline="", encoding="utf-8") as f:
            all_rows.extend(list(csv.DictReader(f)))

    # Deduplica por título
    seen = set()
    rows = []
    for r in all_rows:
        t = r.get("post_title", "").strip()
        if t and t not in seen:
            seen.add(t)
            rows.append(r)

    os.makedirs(args.output_dir, exist_ok=True)
    total = len(rows)
    print(f"📋 Gerando kit HubSpot — {total} artigos")
    print(f"   Saída: {args.output_dir}")
    print()

    articles_index = []
    for idx, row in enumerate(rows, 1):
        title    = row.get("post_title", "").strip()
        category_raw = row.get("original_theme", "").strip()
        category = CATEGORY_MAP.get(category_raw, category_raw)
        qa       = row.get("qa_score", "—")
        slug     = slugify(title)
        has_img  = os.path.exists(os.path.join(IMAGES_DIR, f"{slug}.png"))

        filename = generate_ficha(idx, total, row, args.output_dir)
        articles_index.append((filename, title, category, qa, has_img))
        print(f"  [{idx:02d}/{total}] ✅ {filename}")

    generate_index(articles_index, args.output_dir)
    print()
    print(f"✅ {total} fichas geradas")
    print(f"📂 Abrir: {os.path.join(args.output_dir, 'index.html')}")


if __name__ == "__main__":
    main()
