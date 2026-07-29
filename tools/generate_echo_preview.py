#!/usr/bin/env python3
"""Gera o preview do lote com artigos e cards do Sowads Echo.

Exemplo:
  python3 tools/generate_echo_preview.py \
    --csv output/articles/lote.csv \
    --echo_json output/celso/sowads_echo_lote3.json \
    --source_dir output/accesstage-site/lote3 \
    --out_dir output/preview/accesstage/lote3-echo \
    --docx output/celso/sowads_echo_lote3.docx
"""
import argparse
import csv
import html
import json
import os
import re
import shutil
import unicodedata

PROFILE_IMAGE = os.path.join(os.path.dirname(__file__), "..", "client", "personas", "celso_sato.jpg")

def slugify(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[\s_-]+", "-", value)[:60]


def strip_html(value):
    value = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", value or "", flags=re.S | re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def esc(value):
    return html.escape(value or "", quote=True)


def article_filename(number, title):
    return f"artigo_{number:02d}_{slugify(title)}.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--echo_json", required=True)
    ap.add_argument("--source_dir", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--docx", required=True)
    ap.add_argument("--zip_name", default="Accesstage_Veragi_Lote3_com_Echo.zip")
    args = ap.parse_args()

    with open(args.csv, encoding="utf-8", newline="") as f:
        articles = list(csv.DictReader(f))
    with open(args.echo_json, encoding="utf-8") as f:
        echo_data = json.load(f)
    posts = echo_data["posts"]
    if len(articles) != len(posts):
        raise ValueError(f"Artigos ({len(articles)}) e posts Echo ({len(posts)}) não correspondem")

    os.makedirs(args.out_dir, exist_ok=True)
    # Copia as fichas HTML e imagens já aprovadas para a nova subpágina isolada.
    for name in os.listdir(args.source_dir):
        src = os.path.join(args.source_dir, name)
        dst = os.path.join(args.out_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif name != "index.html":
            shutil.copy2(src, dst)
    shutil.copy2(args.docx, os.path.join(args.out_dir, "sowads_echo_lote3.docx"))
    if not os.path.isfile(PROFILE_IMAGE):
        raise FileNotFoundError(f"Foto de perfil não encontrada: {PROFILE_IMAGE}")
    profile_dir = os.path.join(args.out_dir, "assets")
    os.makedirs(profile_dir, exist_ok=True)
    shutil.copy2(PROFILE_IMAGE, os.path.join(profile_dir, "celso-sato.jpg"))
    with open(os.path.join(args.out_dir, "sowads_echo_lote3.json"), "w", encoding="utf-8") as f:
        json.dump(echo_data, f, ensure_ascii=False, indent=2)

    paired_cards = []
    for idx, (article, post) in enumerate(zip(articles, posts), 1):
        title = article.get("post_title", "")
        description = article.get("meta_description", "") or strip_html(article.get("post_content", ""))[:175]
        filename = article_filename(idx, title)
        image = f"images/{slugify(title)}.png"
        copy = esc(post["copy"]).replace("\n", "<br>")
        paired_cards.append(f'''<article class="echo-pair" id="echo-{idx}">
  <a class="article-summary" href="{esc(filename)}"><img src="{esc(image)}" alt="{esc(title)}"><div class="article-body"><span>ARTIGO {idx:02d} · QA {esc(article.get("qa_score", "—"))}/100</span><h3>{esc(title)}</h3><p>{esc(description[:175])}</p><b>Ler ficha de publicação →</b></div></a>
  <div class="linkedin-card">
    <div class="linkedin-head"><img class="profile-photo" src="assets/celso-sato.jpg" alt="Celso Sato"><div><strong>Celso Sato</strong><span>CEO do Grupo Accesstage · 1º</span><small>Simulação para aprovação · Sowads Echo</small></div><b aria-label="Mais opções">•••</b></div>
    <div class="echo-copy">{copy}</div>
    <div class="echo-actions"><button type="button" data-copy="echo-copy-{idx}">Copiar post</button><a href="{esc(filename)}">Ler artigo →</a></div>
    <textarea class="sr-only" id="echo-copy-{idx}">{esc(post["copy"])}</textarea>
  </div>
</article>''')

    page = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Accesstage · Lote 3 + Sowads Echo</title>
<style>
:root{{--purple:#442357;--pink:#dc1668;--ink:#1f2937;--muted:#667085;--paper:#fff;--bg:#f4f6f9;--line:#dfe3e8}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);font:16px/1.55 Inter,Arial,sans-serif;color:var(--ink)}}
.top{{background:var(--purple);color:#fff;padding:15px 28px;display:flex;justify-content:space-between;gap:16px;align-items:center}}.top a{{color:#fff;font-weight:700;text-decoration:none}}
.hero{{background:linear-gradient(120deg,var(--purple),var(--pink));color:#fff;padding:58px 24px;text-align:center}}.hero h1{{margin:0;font-size:clamp(2rem,5vw,3.3rem)}}.hero p{{max-width:680px;margin:12px auto 0;opacity:.92}}.stats{{display:flex;justify-content:center;gap:14px;flex-wrap:wrap;margin-top:28px}}.stat{{min-width:150px;padding:14px 20px;background:#ffffff20;border:1px solid #ffffff45;border-radius:14px}}.stat b{{display:block;font-size:1.7rem}}.stat small{{text-transform:uppercase;letter-spacing:.04em}}
.nav{{max-width:1180px;margin:0 auto;padding:20px 24px;display:flex;justify-content:center;gap:20px;flex-wrap:wrap}}.nav a{{color:var(--purple);font-weight:800;text-decoration:none}}
section{{max-width:1180px;margin:0 auto;padding:25px 24px 54px}}.title{{max-width:760px;margin:0 auto 28px;text-align:center}}.eyebrow{{color:var(--pink);font-weight:800;text-transform:uppercase;font-size:.78rem;letter-spacing:.1em}}h2{{font-size:clamp(1.7rem,3vw,2.4rem);margin:8px 0}}.title p{{color:var(--muted)}}
.pair-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;align-items:start}}.echo-pair{{display:grid;grid-template-columns:minmax(190px,.8fr) minmax(260px,1.2fr);background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 3px 12px #10182812;min-width:0}}.article-summary{{color:inherit;text-decoration:none;background:#f8f4f7;display:flex;flex-direction:column}}.article-summary img{{width:100%;aspect-ratio:16/10;object-fit:cover}}.article-body{{padding:17px}}.article-body span{{color:#087f5b;font-weight:800;font-size:.72rem}}.article-body h3{{font-size:1rem;line-height:1.35;margin:8px 0}}.article-body p{{font-size:.86rem;color:var(--muted);margin:0 0 13px}}.article-body b{{color:var(--pink);font-size:.84rem}}.linkedin-card{{padding:17px;min-width:0}}.linkedin-head{{display:flex;gap:10px;align-items:flex-start}}.linkedin-head b{{margin-left:auto;color:#666;letter-spacing:1px}}.profile-photo{{height:46px;width:46px;object-fit:cover;border-radius:50%;border:1px solid var(--line)}}.linkedin-head strong,.linkedin-head span,.linkedin-head small{{display:block}}.linkedin-head span,.linkedin-head small{{color:var(--muted);font-size:.78rem}}.echo-copy{{white-space:normal;margin:18px 0 15px;font-size:.92rem}}.echo-actions{{border-top:1px solid var(--line);padding-top:12px;display:flex;justify-content:space-between;gap:10px;align-items:center}}.echo-actions button{{border:0;background:transparent;color:#0a66c2;font-weight:800;cursor:pointer;font-size:.85rem;padding:0}}.echo-actions a{{color:#0a66c2;font-size:.85rem;font-weight:800;text-decoration:none}}.sr-only{{position:absolute;left:-10000px}}
.download{{display:inline-block;padding:13px 20px;border-radius:8px;background:var(--purple);color:#fff;text-decoration:none;font-weight:800;margin-top:8px}}
footer{{background:var(--purple);color:#fff;text-align:center;padding:32px 20px;font-size:.88rem}}@media(max-width:1100px){{.pair-grid{{grid-template-columns:1fr}}}}@media(max-width:650px){{.top{{padding:14px 16px;font-size:.85rem}}section{{padding-left:16px;padding-right:16px}}.echo-pair{{grid-template-columns:1fr}}.article-summary{{display:grid;grid-template-columns:120px 1fr;align-items:stretch}}.article-summary img{{height:100%;aspect-ratio:auto}}.echo-actions{{flex-direction:column;align-items:flex-start}}}}@media(max-width:390px){{.article-summary{{display:block}}.article-summary img{{height:auto;aspect-ratio:16/10}}}}
</style></head><body>
<header class="top"><b>accesstage</b><span>Preview de aprovação · Sowads Orbit + Echo</span><a href="#echo">Artigos + posts</a></header>
<main><section class="hero"><div class="eyebrow" style="color:#fff">Plataforma Veragi · Lote 3</div><h1>12 artigos e 12 vozes de liderança</h1><p>Preview interno para aprovação do conteúdo do blog e das copies autorais de LinkedIn de Celso Sato.</p><div class="stats"><div class="stat"><b>12</b><small>Artigos QA 100</small></div><div class="stat"><b>12</b><small>Posts Sowads Echo</small></div><div class="stat"><b>5</b><small>Hashtags por post</small></div></div><a class="download" href="sowads_echo_lote3.docx" download>Baixar DOCX do Sowads Echo</a></section>
<nav class="nav"><a href="#echo">Sowads Echo</a><a href="#echo">Fichas e posts</a></nav>
<section id="echo"><div class="title"><div class="eyebrow">Sowads Echo</div><h2>Artigo e voz de liderança, lado a lado</h2><p>Em cada bloco: a ficha do artigo à esquerda e a simulação de post de Celso à direita. Dois blocos por linha em telas amplas.</p></div><div class="pair-grid">{''.join(paired_cards)}</div></section></main>
<footer>Sowads Orbit · Sowads Echo · Uso interno e aprovação do cliente</footer>
<script>document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',()=>{{const t=document.getElementById(b.dataset.copy);navigator.clipboard.writeText(t.value);const old=b.textContent;b.textContent='Copiado!';setTimeout(()=>b.textContent=old,1600)}}));</script>
</body></html>'''
    with open(os.path.join(args.out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"✓ Preview: {os.path.join(args.out_dir, 'index.html')}")


if __name__ == "__main__":
    main()
