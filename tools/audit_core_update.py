#!/usr/bin/env python3
"""
Auditoria Core Update Jun/2026 — Sowads Orbit × Accesstage
Auditor sênior de conteúdo B2B financeiro.
"""

import csv
import re
import json
import os
import sys
import time
import requests
from html.parser import HTMLParser
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
CSV_PATH = BASE_DIR / "output/articles/_preview_combined.csv"
REPORT_PATH = BASE_DIR / "output/reports/auditoria_core_update_jun2026.md"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
EVAL_MODEL = "google/gemini-2.5-flash"

# ─── Listas de verificação ────────────────────────────────────────────────────
CLICHES = [
    "em resumo", "fundamental ressaltar", "divisor de águas", "no cenário atual",
    "cada vez mais", "num mundo globalizado", "jornada", "neste artigo vamos",
    "neste conteúdo", "ao longo deste texto", "vale ressaltar", "é importante destacar",
    "além disso", "portanto,", "sendo assim", "isso posto", "nesse sentido"
]

TECH_NOUNS = r"gestão|tesouraria|caixa|pagamento|recebível|cnab|edi|api|cash|conciliação|analytics|integração"

BLACKLIST = [
    " banco ", "planilhas", "grátis", "gratuito", "financiamento", "cartão",
    "download", "empréstimo", "o que é", "significado", "o que significa",
    " mei ", "pessoal", "fgts"
]

# ─── HTML Helpers ─────────────────────────────────────────────────────────────
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
        self.convert_charrefs = True

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return " ".join(self.fed)


def strip_html(html: str) -> str:
    s = MLStripper()
    s.feed(html)
    return s.get_data()


def word_count(html: str) -> int:
    text = strip_html(html)
    return len(text.split())


def first_paragraph_text(html: str) -> str:
    m = re.search(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    return strip_html(m.group(1)).strip()


def last_20pct(html: str) -> str:
    n = max(1, len(html) * 80 // 100)
    return html[n:]


# ─── Verificações programáticas ───────────────────────────────────────────────
def check_cliches(content: str):
    content_lower = content.lower()
    hits = [c for c in CLICHES if c in content_lower]
    count = len(hits)
    if count == 0:
        status = "✅"
    elif count <= 2:
        status = "⚠️"
    else:
        status = "❌"
    return status, count, hits


def check_time_to_answer(content: str):
    first_p = first_paragraph_text(content)
    words = first_p.split()
    wc = len(words)
    has_tech = bool(re.search(TECH_NOUNS, first_p, re.IGNORECASE))
    if wc <= 40 and has_tech:
        return "✅", wc, first_p[:120]
    elif wc > 80 or not has_tech:
        return "❌", wc, first_p[:120]
    else:
        return "⚠️", wc, first_p[:120]


def check_proximos_passos(content: str):
    pattern = r"próximos passos|checklist|o que fazer|passo a passo"
    if re.search(pattern, content, re.IGNORECASE):
        return "✅"
    return "❌"


def check_faq(content: str):
    if 'class="faq-section"' in content or "faq-section" in content:
        return "✅"
    return "❌"


def check_word_count(content: str):
    wc = word_count(content)
    if 700 <= wc <= 1400:
        return "✅", wc
    elif 1400 < wc <= 1800:
        return "⚠️", wc
    else:
        return "❌", wc


def check_blacklist(content: str):
    content_lower = content.lower()
    hits = [b for b in BLACKLIST if b.lower() in content_lower]
    if not hits:
        return "✅", []
    return "❌", hits


def check_cta(content: str):
    tail = last_20pct(content)
    if re.search(r"Veragi|Accesstage", tail):
        return "✅"
    return "❌"


def check_hyperlinks(content: str):
    if "<a href" in content.lower():
        return "❌"
    return "✅"


def check_meta_title(meta_title: str):
    l = len(meta_title.strip())
    if 30 <= l <= 60:
        return "✅", l
    return "⚠️", l


def check_meta_desc(meta_desc: str):
    l = len(meta_desc.strip())
    if 120 <= l <= 155:
        return "✅", l
    return "⚠️", l


def check_h2_count(content: str):
    count = len(re.findall(r"<h2[\s>]", content, re.IGNORECASE))
    if count >= 3:
        return "✅", count
    return "⚠️", count


def check_h3_count(content: str):
    count = len(re.findall(r"<h3[\s>]", content, re.IGNORECASE))
    if count >= 3:
        return "✅", count
    return "⚠️", count


def check_table(content: str):
    if re.search(r"<table[\s>]", content, re.IGNORECASE):
        return "✅"
    return "❌"


def check_lists(content: str):
    if re.search(r"<[uo]l[\s>]", content, re.IGNORECASE):
        return "✅"
    return "❌"


# ─── LLM Evaluator ────────────────────────────────────────────────────────────
def llm_evaluate(title: str, content: str, api_key: str) -> str:
    truncated = content[:6000]
    prompt = f"""Você é auditor sênior de SEO/AEO B2B financeiro.
Avalie este artigo HTML nos critérios abaixo. Seja cirúrgico — cite trechos reais.

ARTIGO: {title}
HTML: {truncated}

CRITÉRIOS (nota 0-10 cada):

1. TIME-TO-ANSWER: O primeiro parágrafo entrega valor nas primeiras 40 palavras? Ou começa com introdução genérica?

2. E-E-A-T EXPERIÊNCIA: Tom de quem vivenciou/analisou na prática? Ou enciclopédico/teórico?

3. INFORMATION GAIN: Há dados, insights ou ângulos que não estão nos top resultados genéricos do Google sobre o tema? Cite 1 exemplo ou diga "genérico".

4. SILAGEM TEMÁTICA: O artigo cria pontes naturais com outros módulos da Plataforma Veragi? Cite 1 exemplo.

5. QUALIDADE EDITORIAL GERAL: Tom consultivo para CFO/tesoureiro? Profundidade real? Fluidez?

6. AEO (Answer Engine Optimization): O conteúdo está estruturado para ser extraído por AI Overviews e LLMs? FAQ com perguntas diretas? Respostas concisas e factuais?

7. COMPLIANCE ACCESSTAGE: Alguma palavra proibida (banco, planilhas, grátis, financiamento, empréstimo)? CTA para Accesstage/Veragi presente?

Para cada critério: nota /10 + 1 frase de justificativa + cite trecho se negativo.
Ao final: NOTA GERAL /10 e APTO PARA PUBLICAÇÃO? (Sim / Sim com ressalvas / Não)"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://sowads.com.br",
        "X-Title": "Sowads Orbit Auditor"
    }
    payload = {
        "model": EVAL_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.3
    }

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERRO NA AVALIAÇÃO LLM: {e}"


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    if not OPENROUTER_KEY:
        print("ERRO: OPENROUTER_API_KEY não encontrada no ambiente.")
        sys.exit(1)

    # Ler CSV
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"✅ CSV carregado: {len(rows)} artigos")
    print("=" * 70)

    results = []

    # ── PARTE 1: Auditoria programática ──────────────────────────────────────
    for i, row in enumerate(rows, 1):
        title = row.get("post_title", "").strip()
        content = row.get("post_content", "")
        meta_title = row.get("meta_title", "")
        meta_desc = row.get("meta_description", "")
        qa_score = row.get("qa_score", "N/A")

        print(f"\nArtigo {i:02d}: {title[:60]}")

        cliche_st, cliche_n, cliche_hits = check_cliches(content)
        tta_st, tta_wc, tta_snippet = check_time_to_answer(content)
        pp_st = check_proximos_passos(content)
        faq_st = check_faq(content)
        wc_st, wc_n = check_word_count(content)
        bl_st, bl_hits = check_blacklist(content)
        cta_st = check_cta(content)
        links_st = check_hyperlinks(content)
        mt_st, mt_len = check_meta_title(meta_title)
        md_st, md_len = check_meta_desc(meta_desc)
        h2_st, h2_n = check_h2_count(content)
        h3_st, h3_n = check_h3_count(content)
        table_st = check_table(content)
        lists_st = check_lists(content)

        r = {
            "num": i,
            "title": title,
            "qa_score": qa_score,
            "cliche": cliche_st, "cliche_n": cliche_n, "cliche_hits": cliche_hits,
            "tta": tta_st, "tta_wc": tta_wc, "tta_snippet": tta_snippet,
            "proximos": pp_st,
            "faq": faq_st,
            "words": wc_st, "word_n": wc_n,
            "blacklist": bl_st, "bl_hits": bl_hits,
            "cta": cta_st,
            "links": links_st,
            "meta_title": mt_st, "mt_len": mt_len,
            "meta_desc": md_st, "md_len": md_len,
            "h2": h2_st, "h2_n": h2_n,
            "h3": h3_st, "h3_n": h3_n,
            "table": table_st,
            "lists": lists_st,
        }
        results.append(r)

        # Status resumido
        print(f"  QA={qa_score} | Clichês={cliche_st}({cliche_n}) | TTA={tta_st}({tta_wc}w) | FAQ={faq_st} | Words={wc_st}({wc_n}) | BL={bl_st} | CTA={cta_st} | Links={links_st}")
        if bl_hits:
            print(f"  ⚠️  BLACKLIST HITS: {bl_hits}")

    # ── PARTE 2: Auditoria LLM ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PARTE 2 — Auditoria LLM (5 artigos)")
    print("=" * 70)

    # Selecionar artigos: 1 do lote1, 2 do batch4 primeiros, 2 do batch4 finais
    llm_indices = [0, 10, 15, 29, 39]  # 0-based
    llm_results = []

    for idx in llm_indices:
        row = rows[idx]
        title = row.get("post_title", "").strip()
        content = row.get("post_content", "")
        print(f"\n  Avaliando artigo {idx+1}: {title[:60]} ...")
        eval_text = llm_evaluate(title, content, OPENROUTER_KEY)
        llm_results.append({"num": idx+1, "title": title, "eval": eval_text})
        print(f"  ✅ Avaliação concluída ({len(eval_text)} chars)")
        time.sleep(2)  # Rate limit

    # ── PARTE 3: Gerar relatório ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PARTE 3 — Gerando relatório...")

    # Contar aprovados/ressalvas/reprovados
    def article_verdict(r):
        critical_fails = [
            r["blacklist"] == "❌",
            r["links"] == "❌",
        ]
        major_issues = [
            r["faq"] == "❌",
            r["tta"] == "❌",
            r["cliche"] == "❌",
            r["words"] == "❌",
        ]
        if any(critical_fails):
            return "Reprovado"
        elif sum(1 for x in major_issues if x) >= 2:
            return "Ressalvas"
        elif any(major_issues):
            return "Ressalvas"
        else:
            return "Aprovado"

    verdicts = [article_verdict(r) for r in results]
    approved = sum(1 for v in verdicts if v == "Aprovado")
    ressalvas = sum(1 for v in verdicts if v == "Ressalvas")
    reprovados = sum(1 for v in verdicts if v == "Reprovado")

    qa_scores = []
    for r in results:
        try:
            qa_scores.append(float(r["qa_score"]))
        except:
            pass
    qa_avg = sum(qa_scores) / len(qa_scores) if qa_scores else 0

    # Problemas sistêmicos
    cliche_count = sum(1 for r in results if r["cliche"] != "✅")
    tta_fail = sum(1 for r in results if r["tta"] == "❌")
    pp_fail = sum(1 for r in results if r["proximos"] == "❌")
    faq_fail = sum(1 for r in results if r["faq"] == "❌")
    wc_fail = sum(1 for r in results if r["words"] == "❌")
    bl_fail = sum(1 for r in results if r["blacklist"] == "❌")
    cta_fail = sum(1 for r in results if r["cta"] == "❌")
    links_fail = sum(1 for r in results if r["links"] == "❌")
    mt_fail = sum(1 for r in results if r["meta_title"] != "✅")
    md_fail = sum(1 for r in results if r["meta_desc"] != "✅")
    h2_fail = sum(1 for r in results if r["h2"] != "✅")
    table_fail = sum(1 for r in results if r["table"] == "❌")
    lists_fail = sum(1 for r in results if r["lists"] == "❌")

    # ── Montar relatório Markdown ──────────────────────────────────────────────
    md_lines = []
    md_lines.append("# Auditoria Core Update Jun/2026 — Sowads Orbit × Accesstage")
    md_lines.append("")
    md_lines.append(f"**Data da auditoria:** {time.strftime('%Y-%m-%d %H:%M')}")
    md_lines.append(f"**Modelo avaliador:** {EVAL_MODEL}")
    md_lines.append("")

    # Sumário Executivo
    md_lines.append("## Sumário Executivo")
    md_lines.append("")
    md_lines.append(f"- **Total de artigos auditados:** 40")
    md_lines.append(f"- **Aprovados sem ressalvas:** {approved}")
    md_lines.append(f"- **Aprovados com ressalvas:** {ressalvas}")
    md_lines.append(f"- **Reprovados:** {reprovados}")
    md_lines.append(f"- **Score QA médio:** {qa_avg:.1f}/100")
    md_lines.append("")
    md_lines.append("### Principais problemas sistêmicos encontrados")
    md_lines.append("")

    issues = []
    if cliche_count > 0:
        issues.append(f"**Clichês editoriais** ({cliche_count}/40 artigos afetados) — frases proibidas detectadas")
    if tta_fail > 0:
        issues.append(f"**Time-to-Answer fraco** ({tta_fail}/40) — primeiros parágrafos com introdução genérica ou > 80 palavras")
    if pp_fail > 0:
        issues.append(f"**Próximos Passos/Checklist ausente** ({pp_fail}/40) — artigos sem seção de ação")
    if faq_fail > 0:
        issues.append(f"**FAQ ausente** ({faq_fail}/40) — artigos sem faq-section")
    if wc_fail > 0:
        issues.append(f"**Word count fora do ideal** ({wc_fail}/40) — < 700 ou > 1800 palavras")
    if bl_fail > 0:
        issues.append(f"**⚠️ CRÍTICO: Blacklist violations** ({bl_fail}/40) — palavras proibidas detectadas")
    if cta_fail > 0:
        issues.append(f"**CTA ausente no final** ({cta_fail}/40) — sem menção a Veragi/Accesstage nos últimos 20%")
    if links_fail > 0:
        issues.append(f"**⚠️ CRÍTICO: Hyperlinks no conteúdo** ({links_fail}/40) — viola invariante do projeto")
    if mt_fail > 0:
        issues.append(f"**Meta title fora do range** ({mt_fail}/40) — comprimento fora de 30-60 chars")
    if md_fail > 0:
        issues.append(f"**Meta description fora do range** ({md_fail}/40) — comprimento fora de 120-155 chars")
    if table_fail > 0:
        issues.append(f"**Sem tabela** ({table_fail}/40) — artigos sem elemento <table>")
    if lists_fail > 0:
        issues.append(f"**Sem listas** ({lists_fail}/40) — artigos sem <ul> ou <ol>")

    for issue in issues:
        md_lines.append(f"- {issue}")

    md_lines.append("")

    # Tabela de resultados
    md_lines.append("## Tabela de Resultados — Todos os 40 Artigos")
    md_lines.append("")
    md_lines.append("| # | Título | QA | Anti-clichê | TTA | Próx.Passos | FAQ | Words | Blacklist | CTA | Links | MetaTitle | MetaDesc | H2 | Tabela | Listas |")
    md_lines.append("|---|--------|----|----|----|----|----|----|----|----|----|----|----|----|----|----|")

    for r in results:
        title_short = r["title"][:40] + ("…" if len(r["title"]) > 40 else "")
        qa = r["qa_score"]
        cliche_cell = f"{r['cliche']}({r['cliche_n']})"
        words_cell = f"{r['words']}({r['word_n']})"
        mt_cell = f"{r['meta_title']}({r['mt_len']})"
        md_cell = f"{r['meta_desc']}({r['md_len']})"
        h2_cell = f"{r['h2']}({r['h2_n']})"

        md_lines.append(
            f"| {r['num']:02d} | {title_short} | {qa} | {cliche_cell} | {r['tta']} | {r['proximos']} | {r['faq']} | {words_cell} | {r['blacklist']} | {r['cta']} | {r['links']} | {mt_cell} | {md_cell} | {h2_cell} | {r['table']} | {r['lists']} |"
        )

    md_lines.append("")

    # Detalhes dos problemas críticos
    md_lines.append("### Detalhes: Blacklist Violations")
    bl_any = [(r["num"], r["title"][:50], r["bl_hits"]) for r in results if r["blacklist"] == "❌"]
    if bl_any:
        for num, t, hits in bl_any:
            md_lines.append(f"- **Artigo {num:02d}** ({t}): `{hits}`")
    else:
        md_lines.append("- Nenhuma violação encontrada. ✅")
    md_lines.append("")

    md_lines.append("### Detalhes: Clichês Encontrados")
    cliche_detail = [(r["num"], r["title"][:50], r["cliche_hits"]) for r in results if r["cliche_hits"]]
    if cliche_detail:
        for num, t, hits in cliche_detail:
            md_lines.append(f"- **Artigo {num:02d}** ({t}): {hits}")
    else:
        md_lines.append("- Nenhum clichê encontrado. ✅")
    md_lines.append("")

    md_lines.append("### Detalhes: Time-to-Answer (primeiros parágrafos)")
    for r in results:
        if r["tta"] != "✅":
            md_lines.append(f"- **Artigo {r['num']:02d}** [{r['tta']}] ({r['tta_wc']} words): \"{r['tta_snippet']}...\"")
    md_lines.append("")

    # Auditoria LLM
    md_lines.append("## Auditoria LLM — 5 Artigos em Profundidade")
    md_lines.append("")
    md_lines.append(f"Modelo avaliador: `{EVAL_MODEL}` via OpenRouter")
    md_lines.append("")

    lote_labels = {
        1: "Lote 1 (artigo 01 — mais antigo, pré-Core Update)",
        11: "Batch 4 — primeiros (artigo 11)",
        16: "Batch 4 — primeiros (artigo 16)",
        30: "Batch 4 — finais (artigo 30)",
        40: "Batch 4 — finais (artigo 40)"
    }

    for lr in llm_results:
        lote_label = lote_labels.get(lr["num"], f"Artigo {lr['num']}")
        md_lines.append(f"### Artigo {lr['num']:02d} — {lote_label}")
        md_lines.append(f"**Título:** {lr['title']}")
        md_lines.append("")
        md_lines.append(lr["eval"])
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    # Problemas sistêmicos
    md_lines.append("## Problemas Sistêmicos")
    md_lines.append("")
    md_lines.append("Padrões negativos que aparecem em múltiplos artigos:")
    md_lines.append("")

    if cliche_count > 0:
        all_cliche_hits = {}
        for r in results:
            for h in r["cliche_hits"]:
                all_cliche_hits[h] = all_cliche_hits.get(h, 0) + 1
        top_cliches = sorted(all_cliche_hits.items(), key=lambda x: -x[1])[:5]
        md_lines.append(f"### 1. Clichês recorrentes ({cliche_count}/40 artigos)")
        for phrase, count in top_cliches:
            md_lines.append(f"- `\"{phrase}\"` — aparece em {count} artigos")
        md_lines.append("")

    if tta_fail > 0:
        md_lines.append(f"### 2. Primeiros parágrafos genéricos ({tta_fail}/40 artigos)")
        md_lines.append("Artigos que começam com contextualização longa em vez de responder diretamente:")
        for r in results:
            if r["tta"] != "✅":
                md_lines.append(f"- Artigo {r['num']:02d}: {r['tta_wc']} palavras no 1º parágrafo")
        md_lines.append("")

    if pp_fail > 0:
        md_lines.append(f"### 3. Ausência de seção de ação ({pp_fail}/40 artigos)")
        md_lines.append("Artigos sem 'Próximos Passos', 'Checklist' ou 'O que fazer' — fundamental para AEO/conversão.")
        md_lines.append("")

    if table_fail > 0:
        md_lines.append(f"### 4. Ausência de tabelas ({table_fail}/40 artigos)")
        md_lines.append("Tabelas aumentam scannability e são extraídas por AI Overviews com mais frequência.")
        md_lines.append("")

    # Recomendações
    md_lines.append("## Recomendações por Critério")
    md_lines.append("")

    md_lines.append("### O que foi bem (pontos fortes)")
    md_lines.append("")
    strengths = []
    if links_fail == 0:
        strengths.append("✅ **Zero hyperlinks** em todos os artigos — invariante respeitada")
    if bl_fail == 0:
        strengths.append("✅ **Zero violações de blacklist** — compliance Accesstage mantido")
    if faq_fail == 0:
        strengths.append("✅ **FAQ presente** em todos os artigos — bom para AEO")
    if qa_avg >= 90:
        strengths.append(f"✅ **Score QA alto** (média {qa_avg:.1f}/100) — estrutura técnica sólida")
    if wc_fail == 0:
        strengths.append("✅ **Word count dentro do range** em todos os artigos")
    for s in strengths:
        md_lines.append(f"- {s}")
    md_lines.append("")

    md_lines.append("### Prioridade 1 — CRÍTICO (corrigir antes de publicar no HubSpot)")
    md_lines.append("")
    if bl_fail > 0:
        md_lines.append(f"- **Blacklist violations** em {bl_fail} artigos — revisar e remover termos proibidos antes de qualquer publicação")
    if links_fail > 0:
        md_lines.append(f"- **Hyperlinks no conteúdo** em {links_fail} artigos — viola invariante core do projeto, remover imediatamente")
    if cta_fail > 0:
        md_lines.append(f"- **CTA ausente** em {cta_fail} artigos — adicionar menção a Veragi/Accesstage nos últimos parágrafos")
    if bl_fail == 0 and links_fail == 0 and cta_fail == 0:
        md_lines.append("- Nenhum problema crítico detectado na auditoria programática. ✅")
    md_lines.append("")

    md_lines.append("### Prioridade 2 — Relevante (melhorar para performance máxima)")
    md_lines.append("")
    if cliche_count > 0:
        md_lines.append(f"- **Eliminar clichês** de {cliche_count} artigos — substituir por linguagem consultiva e específica")
    if tta_fail > 0:
        md_lines.append(f"- **Reescrever primeiros parágrafos** de {tta_fail} artigos — entregar valor nas primeiras 40 palavras com substantivo técnico")
    if pp_fail > 0:
        md_lines.append(f"- **Adicionar seção de ação** em {pp_fail} artigos — 'Próximos Passos' ou checklist no final")
    if md_fail > 0:
        md_lines.append(f"- **Ajustar meta descriptions** de {md_fail} artigos — manter entre 120-155 chars")
    md_lines.append("")

    md_lines.append("### Prioridade 3 — Melhoria futura")
    md_lines.append("")
    if table_fail > 0:
        md_lines.append(f"- **Adicionar tabelas** em {table_fail} artigos — aumentam scannability e extração por AI Overviews")
    if h2_fail > 0:
        md_lines.append(f"- **Revisar estrutura H2** de {h2_fail} artigos — mínimo 3 H2 por artigo")
    md_lines.append("- Considerar adicionar dados proprietários (pesquisas, benchmarks) para aumentar Information Gain")
    md_lines.append("- Revisar silagem temática entre artigos para criar linking interno consistente")
    md_lines.append("")

    # Veredito final
    md_lines.append("## Veredito Final")
    md_lines.append("")

    if reprovados == 0 and bl_fail == 0 and links_fail == 0:
        veredito = "**✅ APTO PARA PUBLICAÇÃO NO HUBSPOT** com as ressalvas abaixo."
    elif reprovados > 0 or bl_fail > 0 or links_fail > 0:
        veredito = f"**⚠️ PUBLICAÇÃO CONDICIONAL** — {reprovados} artigos reprovados e/ou {bl_fail} violações críticas precisam de revisão manual antes da publicação."
    else:
        veredito = "**⚠️ PUBLICAÇÃO COM RESSALVAS** — revisar problemas listados antes de publicar."

    md_lines.append(veredito)
    md_lines.append("")

    if ressalvas > 0:
        md_lines.append(f"**Artigos que precisam revisão manual ({ressalvas}):**")
        for r, v in zip(results, verdicts):
            if v == "Ressalvas":
                issues_list = []
                if r["cliche"] == "❌": issues_list.append(f"clichês({r['cliche_n']})")
                if r["tta"] == "❌": issues_list.append("TTA fraco")
                if r["proximos"] == "❌": issues_list.append("sem próx.passos")
                if r["words"] == "❌": issues_list.append(f"words={r['word_n']}")
                if r["cta"] == "❌": issues_list.append("sem CTA")
                md_lines.append(f"- **Artigo {r['num']:02d}**: {r['title'][:55]} — [{', '.join(issues_list)}]")
        md_lines.append("")

    if reprovados > 0:
        md_lines.append(f"**Artigos reprovados — NÃO publicar ({reprovados}):**")
        for r, v in zip(results, verdicts):
            if v == "Reprovado":
                issues_list = []
                if r["blacklist"] == "❌": issues_list.append(f"blacklist={r['bl_hits']}")
                if r["links"] == "❌": issues_list.append("hyperlinks")
                md_lines.append(f"- **Artigo {r['num']:02d}**: {r['title'][:55]} — [{', '.join(issues_list)}]")
        md_lines.append("")

    md_lines.append("---")
    md_lines.append("*Relatório gerado automaticamente por Sowads Orbit Auditor — uso interno.*")

    report_content = "\n".join(md_lines)

    # Salvar relatório
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"\n✅ Relatório salvo em: {REPORT_PATH}")
    print("\n" + "=" * 70)
    print(report_content)


if __name__ == "__main__":
    main()
