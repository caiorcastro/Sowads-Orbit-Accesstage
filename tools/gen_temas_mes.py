# -*- coding: utf-8 -*-
"""
gen_temas_mes.py — Gera 20 temas NOVOS (deduplicados) para UM mês. Um mês por vez.

Uso: python3 tools/gen_temas_mes.py <N>     (N = número do mês, ex.: 1)
Saída: content_plan/temas_mes<N>.csv  (topic_pt,vertical,category)  + append em content_plan/_master.csv
Dedup contra: 385 URLs publicadas + lotes 1/2 + meses já gerados em content_plan/.
"""
import os, csv, json, re, sys, unicodedata, requests
from dotenv import load_dotenv

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE, ".env"))
KEY = os.getenv("OPENROUTER_API_KEY")
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash"
OUTDIR = os.path.join(BASE, "content_plan"); os.makedirs(OUTDIR, exist_ok=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
TARGET = 20

def norm(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", t)
def keyset(t):
    stop = {"como","de","da","do","a","o","e","em","para","por","com","que","os","as","no","na","um","uma","sua","seu","the","of","x"}
    return set(w for w in norm(t).split() if len(w) > 3 and w not in stop)

# --- dedup base ---
existing = []
u = os.path.join(BASE, "output/reports/urls_publicadas_accesstage.csv")
if os.path.exists(u):
    for r in csv.DictReader(open(u, encoding="utf-8")): existing.append(r.get("titulo_aprox",""))
for f in ["lote_veragi_temas.csv","lote_veragi_temas_batch2.csv","lote_veragi_temas_batch3.csv","lote_veragi_temas_batch4.csv","lote_veragi_lote2_combined.csv"]:
    p = os.path.join(BASE, "output/articles", f)
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            existing.append(r.get("topic_pt") or r.get("post_title") or "")
for f in os.listdir(OUTDIR):
    if f.startswith("temas_mes") and f.endswith(".csv"):
        for r in csv.DictReader(open(os.path.join(OUTDIR, f), encoding="utf-8")):
            existing.append(r.get("topic_pt",""))
existing_keys = [keyset(t) for t in existing if t and t.strip()]
print(f"Dedup base: {len(existing_keys)} títulos")

def is_dup(title, acc):
    k = keyset(title)
    if not k: return True
    for ek in existing_keys + acc:
        if ek and len(k & ek) / max(1, len(k | ek)) >= 0.5:
            return True
    return False

MODULES = ("Contas a Pagar; Contas a Receber; Tesouraria; Crédito/Risco Sacado/Antecipação; Analytics/Dados; "
           "Integrações Bancárias (EDI, API, Open Finance, CNAB, VAN); Cash Pooling; Estratégia/Governança/Compliance")
CATS = ["SEO & AIO","Estratégia e Performance","Data e Analytics"]

def parse_objs(txt):
    objs = []
    for m in re.finditer(r"\{[^{}]*\}", txt, re.S):
        s = m.group(0)
        for cand in (s, s.replace("'", '"')):
            try: objs.append(json.loads(cand)); break
            except Exception: continue
    return objs

def gen(nreq, avoid):
    usr = f"""Estrategista de conteúdo SEO B2B da Accesstage (fintech; produto Veragi — gestão financeira corporativa). Público: CFOs, tesoureiros, controllers de empresas médias/grandes no Brasil.

Gere {nreq} temas de artigo NOVOS, em português-BR, específicos e acionáveis, distribuídos pelos módulos: {MODULES}. Distribua no funil (topo/meio/fundo).

NÃO repita nem seja parecido com estes já cobertos:
{"; ".join(avoid[-140:])}

Responda SÓ com um array JSON, um objeto por tema: {{"topic_pt":"...","funnel":"Topo|Meio|Fundo","module":"...","category":"SEO & AIO|Estratégia e Performance|Data e Analytics"}}"""
    try:
        r = requests.post(URL, headers={"Authorization": f"Bearer {KEY}"},
            json={"model": MODEL, "messages": [{"role":"user","content":usr}], "temperature": 0.9, "max_tokens": 2600}, timeout=90)
        return parse_objs(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print("  (gen erro:", str(e)[:60], ")"); return []

got, acc, avoid = [], [], [t for t in existing if t and t.strip()]
tries = 0
while len(got) < TARGET and tries < 8:
    tries += 1
    for it in gen(26, avoid):
        title = (it.get("topic_pt") or "").strip()
        cat = it.get("category","SEO & AIO"); cat = cat if cat in CATS else "SEO & AIO"
        if not title or is_dup(title, acc): continue
        got.append({"topic_pt": title, "funnel": it.get("funnel",""), "category": cat})
        acc.append(keyset(title)); avoid.append(title)
        if len(got) >= TARGET: break
    print(f"  tentativa {tries}: {len(got)}/{TARGET}")

got = got[:TARGET]
out = os.path.join(OUTDIR, f"temas_mes{N}.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["topic_pt","vertical","category"])
    for t in got: w.writerow([t["topic_pt"], "fintech", t["category"]])
mp = os.path.join(OUTDIR, "_master.csv"); head = not os.path.exists(mp)
with open(mp, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if head: w.writerow(["month","topic_pt","funnel","category"])
    for t in got: w.writerow([N, t["topic_pt"], t["funnel"], t["category"]])
print(f"\n✓ {len(got)} temas do mês {N} -> {out}")
for t in got: print(f"   [{t['funnel'][:4]:4}] {t['topic_pt']}")
