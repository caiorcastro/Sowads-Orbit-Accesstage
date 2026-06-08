#!/usr/bin/env python3
"""
hubspot_publisher.py — Publica artigos do Orbit AI como drafts no HubSpot CMS.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMO AUTENTICAR (sem precisar de Super Admin):

  1. Abrir app.hubspot.com logado como orbit-ai@sowads.com
  2. Ir em Marketing → Website → Blog
  3. Abrir DevTools (F12) → aba Network
  4. Filtrar por: api.hubapi.com
  5. Clicar em qualquer request XHR listado
  6. Em "Request Headers" copiar o valor de: Authorization: Bearer <TOKEN>
  7. Adicionar no .env:
       HUBSPOT_BEARER=<TOKEN_COPIADO>

  O token dura ~60 minutos. Suficiente para publicar um lote inteiro.
  Para publicações futuras basta repetir os passos 3-7.

  Alternativa permanente: pedir ao admin da Accesstage para criar um
  Private App em Settings → Integrations → Private Apps (scopes: content)
  e adicionar no .env: HUBSPOT_API_KEY=pat-na1-...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Uso:
  # Testar 1 artigo antes do lote (sempre fazer primeiro)
  python3 tools/hubspot_publisher.py --from_csv output/articles/<batch>.csv --test_one

  # Publicar CSV específico
  python3 tools/hubspot_publisher.py --from_csv output/articles/<batch>.csv

  # Publicar todos os CSVs de artigos
  python3 tools/hubspot_publisher.py --all

  # Listar blogs do portal (para confirmar qual usar)
  python3 tools/hubspot_publisher.py --list_blogs

  # Simular sem criar nada
  python3 tools/hubspot_publisher.py --from_csv <csv> --dry_run
"""
import os, sys, re, csv, json, time, argparse, glob
from datetime import datetime

import requests

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLES_DIR = os.path.join(BASE_DIR, "output", "articles")
REPORTS_DIR  = os.path.join(BASE_DIR, "output", "reports")
ENV_FILE     = os.path.join(BASE_DIR, ".env")

PORTAL_ID    = "457604"
HS_API       = "https://api.hubapi.com"

# Endpoint v2 (Content API) — funciona com cookie de sessão E com Private App
BLOGS_V2_EP  = f"{HS_API}/content/api/v2/blogs"
POSTS_V2_EP  = f"{HS_API}/content/api/v2/blog-posts"
# Endpoint v3 (CMS API) — requer Private App com scope content
BLOGS_V3_EP  = f"{HS_API}/cms/v3/blogs"
POSTS_V3_EP  = f"{HS_API}/cms/v3/blogs/posts"

# Mapeamento categoria CSV → tag HubSpot
CATEGORY_TO_TAG = {
    "SEO & AIO":                "SEO e AI-SEO",
    "Conteúdo":                 "Conteúdo em Escala",
    "Estratégia e Performance": "Estratégia e Performance",
    "Mídia Paga":               "Mídia Paga",
    "Data e Analytics":         "Dados e Analytics",
}


# ── ANSI ───────────────────────────────────────────────────────────────────────
class C:
    OK   = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END  = "\033[0m"

def ok(msg):   print(f"{C.OK}[✓]{C.END} {msg}", flush=True)
def warn(msg): print(f"{C.WARN}[!]{C.END} {msg}", flush=True)
def fail(msg): print(f"{C.FAIL}[✗]{C.END} {msg}", flush=True)
def info(msg): print(f"{C.CYAN}[→]{C.END} {msg}", flush=True)


# ── .env loader ────────────────────────────────────────────────────────────────
def load_env():
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


# ── Auth ───────────────────────────────────────────────────────────────────────
class HubSpotAuth:
    """
    Encapsula autenticação HubSpot — dois modos:

    MODO BEARER (Private App token — pat-na1-...):
      headers: Authorization: Bearer <token>
      endpoints: v3 CMS API

    MODO COOKIE (sessão do browser — hubspotapi cookie):
      headers: Cookie + X-HubSpot-CSRF-hubspotapi
      endpoints: v2 Content API (compatível com sessão)
    """

    def __init__(self, token: str = "", cookie: str = ""):
        self.token  = token
        self.cookie = cookie
        self.mode   = "cookie" if (cookie and not token) else "bearer"

    def headers(self) -> dict:
        if self.mode == "cookie":
            return {
                "Cookie":                      f"hubspotapi={self.cookie}",
                "X-HubSpot-CSRF-hubspotapi":   self.cookie,
                "Content-Type":                "application/json",
            }
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
        }

    def _blogs_ep(self):
        return BLOGS_V2_EP if self.mode == "cookie" else BLOGS_V3_EP

    def _posts_ep(self):
        return POSTS_V2_EP if self.mode == "cookie" else POSTS_V3_EP

    def get(self, url, **kw):
        return requests.get(url, headers=self.headers(), timeout=15, **kw)

    def post(self, url, **kw):
        return requests.post(url, headers=self.headers(), timeout=30, **kw)


# ── HubSpot Blog API ───────────────────────────────────────────────────────────
def list_blogs(auth: HubSpotAuth) -> list:
    if auth.mode == "cookie":
        r = auth.get(f"{auth._blogs_ep()}?portalId={PORTAL_ID}&limit=20")
    else:
        r = auth.get(f"{auth._blogs_ep()}?limit=20")
    r.raise_for_status()
    data = r.json()
    # v2 retorna {"objects": [...]} ; v3 retorna {"results": [...]}
    return data.get("results", data.get("objects", []))


def list_authors(auth: HubSpotAuth) -> list:
    if auth.mode == "cookie":
        r = auth.get(f"{HS_API}/content/api/v2/blog-authors?portalId={PORTAL_ID}&limit=50")
    else:
        r = auth.get(f"{HS_API}/cms/v3/blogs/authors?limit=50")
    if r.ok:
        data = r.json()
        return data.get("results", data.get("objects", []))
    return []


def resolve_tag(auth: HubSpotAuth, name: str, cache: dict) -> str | None:
    if name in cache:
        return cache[name]
    if auth.mode == "cookie":
        r = auth.get(f"{HS_API}/content/api/v2/blog-tags?portalId={PORTAL_ID}&limit=100")
    else:
        r = auth.get(f"{HS_API}/cms/v3/blogs/tags?limit=100")
    if r.ok:
        data = r.json()
        for t in data.get("results", data.get("objects", [])):
            if t.get("name", "").lower() == name.lower():
                cache[name] = t["id"]; return t["id"]
    # Criar tag
    if auth.mode == "cookie":
        r2 = auth.post(f"{HS_API}/content/api/v2/blog-tags",
                       json={"name": name, "portalId": PORTAL_ID})
    else:
        r2 = auth.post(f"{HS_API}/cms/v3/blogs/tags", json={"name": name})
    if r2.ok:
        tid = r2.json().get("id"); cache[name] = tid; return tid
    warn(f"Tag '{name}' não criada: {r2.text[:100]}")
    return None


def create_draft(auth: HubSpotAuth, blog_id: str, author_id: str,
                 title: str, body_html: str, meta_desc: str,
                 meta_title: str, tag_ids: list) -> dict:
    if auth.mode == "cookie":
        # v2 Content API — campos diferentes
        payload = {
            "portalId":       int(PORTAL_ID),
            "contentGroupId": int(blog_id),
            "name":           title,
            "htmlTitle":      meta_title or title,
            "postBody":       body_html,
            "metaDescription": meta_desc,
            "currentState":   "DRAFT",
            "language":       "pt-BR",
        }
        if author_id:
            payload["blogAuthorId"] = int(author_id)
        if tag_ids:
            payload["topicIds"] = [int(t) for t in tag_ids]
    else:
        # v3 CMS API
        payload = {
            "contentGroupId":  blog_id,
            "name":            title,
            "htmlTitle":       meta_title or title,
            "postBody":        body_html,
            "metaDescription": meta_desc,
            "state":           "DRAFT",
            "language":        "pt-BR",
        }
        if author_id:
            payload["blogAuthorId"] = author_id
        if tag_ids:
            payload["tagIds"] = tag_ids

    r = auth.post(auth._posts_ep(), json=payload)
    r.raise_for_status()
    return r.json()


# ── CSV ────────────────────────────────────────────────────────────────────────
def load_articles(path: str) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            content = row.get("post_content", "")
            if len(content) < 200 or "ERRO" in str(content):
                continue
            rows.append(row)
    return rows


def collect_article_csvs() -> list[str]:
    # Exclui CSVs de temas (sem coluna post_content)
    paths = sorted(glob.glob(os.path.join(ARTICLES_DIR, "lote_veragi_*.csv")))
    article_csvs = []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            header = f.readline()
        if "post_content" in header:
            article_csvs.append(p)
    return article_csvs


# ── Publish loop ───────────────────────────────────────────────────────────────
def publish_batch(auth: HubSpotAuth, blog_id: str, author_id: str,
                  rows: list[dict], tag_cache: dict, dry_run=False) -> list[dict]:
    results = []
    for i, row in enumerate(rows, 1):
        title    = row.get("post_title", "").strip()
        content  = row.get("post_content", "").strip()
        meta_t   = row.get("meta_title",       title).strip()
        meta_d   = row.get("meta_description", "").strip()
        category = row.get("suggested_category", "").strip()

        if not title or not content:
            warn(f"[{i:02d}] Pulando — sem título ou conteúdo"); continue

        info(f"[{i:02d}] {title[:65]}...")

        if dry_run:
            ok(f"[{i:02d}] DRY RUN")
            results.append({"title": title, "status": "dry_run", "hs_id": "", "url": "", "error": ""})
            continue

        tag_name = CATEGORY_TO_TAG.get(category, category)
        tag_ids  = []
        if tag_name:
            tid = resolve_tag(auth, tag_name, tag_cache)
            if tid:
                tag_ids = [tid]

        try:
            resp   = create_draft(auth, blog_id, author_id,
                                  title, content, meta_d, meta_t, tag_ids)
            hs_id  = resp.get("id", "?")
            hs_url = resp.get("url", "")
            ok(f"[{i:02d}] Draft criado → ID {hs_id}")
            results.append({"title": title, "status": "ok", "hs_id": hs_id, "url": hs_url, "error": ""})
        except requests.HTTPError as e:
            body = e.response.text[:200]
            fail(f"[{i:02d}] HTTP {e.response.status_code}: {body}")
            results.append({"title": title, "status": "error", "hs_id": "", "url": "", "error": body})
        except Exception as e:
            fail(f"[{i:02d}] {e}")
            results.append({"title": title, "status": "error", "hs_id": "", "url": "", "error": str(e)})

        time.sleep(0.4)

    return results


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    load_env()

    parser = argparse.ArgumentParser(description="Orbit AI → HubSpot Draft Publisher")
    parser.add_argument("--from_csv",   help="CSV de artigos (lote específico)")
    parser.add_argument("--all",        action="store_true", help="Todos os CSVs de artigos")
    parser.add_argument("--test_one",   action="store_true", help="Publicar só 1 artigo (teste)")
    parser.add_argument("--list_blogs", action="store_true", help="Listar blogs do portal")
    parser.add_argument("--blog_id",    default="", help="ID do blog (auto-detectado se vazio)")
    parser.add_argument("--dry_run",    action="store_true", help="Simular sem criar posts")
    parser.add_argument("--token",      default="", help="Bearer token (HUBSPOT_BEARER ou HUBSPOT_API_KEY)")
    args = parser.parse_args()

    # Prioridade: --token > HUBSPOT_API_KEY (Private App) > HUBSPOT_COOKIE (sessão)
    bearer = args.token or os.environ.get("HUBSPOT_API_KEY", "")
    cookie = os.environ.get("HUBSPOT_COOKIE", "")

    if not bearer and not cookie:
        fail("Nenhuma credencial HubSpot encontrada.")
        print("""
OPÇÃO A — Cookie de sessão (não precisa de Super Admin):
  1. Abrir app.hubspot.com logado como orbit-ai@sowads.com
  2. DevTools (F12) → aba Console
  3. Colar e Enter:
       document.cookie.split(';').find(c => c.trim().startsWith('hubspotapi='))
  4. Copiar o valor após 'hubspotapi='
  5. Adicionar no .env:  HUBSPOT_COOKIE=<valor_copiado>

OPÇÃO B — Private App Token (pede para o admin da Accesstage criar):
  HubSpot → Settings → Integrations → Private Apps
  Adicionar no .env:  HUBSPOT_API_KEY=pat-na1-...
""")
        sys.exit(1)

    auth = HubSpotAuth(token=bearer, cookie=cookie)
    info(f"Modo autenticação: {'Private App (Bearer)' if bearer else 'Cookie de sessão'}")

    # ── Teste de conectividade ──────────────────────────────────────────────────
    try:
        blogs = list_blogs(auth)
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            fail("Token inválido ou expirado. Repita os passos do DevTools.")
        else:
            fail(f"Erro HubSpot {e.response.status_code}: {e.response.text[:200]}")
        sys.exit(1)

    if args.list_blogs:
        print(f"\nBlogs no portal {PORTAL_ID}:")
        for b in blogs:
            print(f"  ID {b['id']:<20} → {b.get('name','?')}")
        return

    # ── Resolver blog_id ────────────────────────────────────────────────────────
    blog_id = args.blog_id
    if not blog_id:
        if not blogs:
            fail("Nenhum blog encontrado no portal."); sys.exit(1)
        blog_id = blogs[0]["id"]
        info(f"Blog: {blogs[0].get('name','?')} (ID {blog_id})")

    # ── Resolver author_id ──────────────────────────────────────────────────────
    author_id = ""
    authors = list_authors(auth)
    if authors:
        author_id = authors[0]["id"]
        info(f"Autor: {authors[0].get('displayName', authors[0].get('fullName','?'))}")

    tag_cache: dict = {}
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # ── Selecionar CSVs ─────────────────────────────────────────────────────────
    if args.from_csv:
        csv_paths = [args.from_csv]
    elif args.all:
        csv_paths = collect_article_csvs()
        if not csv_paths:
            fail(f"Nenhum CSV de artigos em {ARTICLES_DIR}"); sys.exit(1)
        info(f"{len(csv_paths)} CSV(s) encontrado(s)")
    else:
        parser.print_help(); sys.exit(0)

    # ── Publicar ────────────────────────────────────────────────────────────────
    all_results = []
    for path in csv_paths:
        info(f"\nArquivo: {os.path.basename(path)}")
        rows = load_articles(path)
        if not rows:
            warn(f"Sem artigos válidos em {os.path.basename(path)}"); continue
        if args.test_one:
            rows = rows[:1]
            info("Modo --test_one: publicando apenas 1 artigo")
        results = publish_batch(auth, blog_id, author_id, rows, tag_cache, dry_run=args.dry_run)
        all_results.extend(results)

    # ── Relatório ───────────────────────────────────────────────────────────────
    ok_n  = sum(1 for r in all_results if r["status"] == "ok")
    err_n = sum(1 for r in all_results if r["status"] == "error")
    ts    = datetime.now().strftime("%Y%m%d_%H%M")
    rpath = os.path.join(REPORTS_DIR, f"hubspot_publish_{ts}.csv")

    with open(rpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["title","status","hs_id","url","error"])
        w.writeheader()
        w.writerows(all_results)

    print(f"\n{'─'*50}")
    print(f"  Drafts criados : {ok_n}")
    print(f"  Erros          : {err_n}")
    print(f"  Relatório      : {rpath}")
    print(f"{'─'*50}")


if __name__ == "__main__":
    main()
