"""
orbit_media_indexer.py

Indexa a biblioteca de mídia do WordPress e faz match temático entre
imagens existentes e novos artigos gerados pelo Orbit AI Content Engine.

COMO O MATCH FUNCIONA
─────────────────────
Cada grupo de imagens (blog + redes sociais) tem um topic_slug extraído
do nome do arquivo. Quando um novo artigo é gerado, o sistema compara
as palavras significativas do tema do artigo com as palavras do topic_slug
de cada grupo disponível, usando um score de similaridade (Jaccard).

Score final por grupo:
  similarity  = |palavras_comuns| / |palavras_artigo ∪ palavras_imagem|
  completude  = nº de tipos disponíveis (blog, li, ig, fb, tt) / 5
  final_score = (similarity * 0.80) + (completude * 0.20)

Grupos já usados recebem score zero — garantindo não-repetição.
O índice é salvo em disco com o campo "used" persistindo entre runs.

PADRÃO DE NOMENCLATURA RECONHECIDO
────────────────────────────────────
  {Prefix}_{N}_{type}_{topic-slug}_{hash}.jpg
  {Prefix}_{sub}_{N}_{type}_{topic-slug}_{hash}.jpg  (ex: sowads_ia_001_wp_...)

Tipos: blog/wp → featured | li/linkedin | ig/instagram | fb/facebook | tt/tiktok | meta (4:5)

USO STANDALONE
──────────────
  python orbit_media_indexer.py --wp_url https://sowads.com.br --wp_user caio --wp_pass "..."
  python orbit_media_indexer.py --reset   # zera flags "used" mantendo o índice
  python orbit_media_indexer.py --show    # exibe o índice atual sem buscar WP

IMPORTAR EM OUTROS SCRIPTS
───────────────────────────
  from orbit_media_indexer import load_index, save_index, get_images_for_article
"""

import os
import re
import json
import argparse
import requests
from datetime import datetime

_BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(_BASE_DIR, "output", "reports", "media_index.json")

TYPE_MAP = {
    'blog': 'blog', 'wp': 'blog',
    'li': 'linkedin', 'linkedin': 'linkedin',
    'ig': 'instagram', 'instagram': 'instagram',
    'fb': 'facebook', 'facebook': 'facebook',
    'tt': 'tiktok', 'tiktok': 'tiktok',
    'meta': 'meta',
}

SOCIAL_TYPES = ['blog', 'linkedin', 'instagram', 'facebook', 'tiktok']

# Stopwords PT-BR irrelevantes para matching temático
STOPWORDS = {
    'como', 'para', 'com', 'que', 'seu', 'sua', 'dos', 'das', 'uma', 'por',
    'mais', 'nao', 'sao', 'pode', 'podem', 'ser', 'esta', 'esse', 'essa',
    'nos', 'nas', 'aos', 'entre', 'sobre', 'apos', 'ate', 'sem', 'sob',
    'desde', 'guia', 'voce', 'mas', 'bem', 'qual', 'quais', 'quando',
    'onde', 'quem', 'por', 'porque', 'entao', 'assim', 'tudo', 'cada',
    'todo', 'toda', 'todos', 'todas', 'caso', 'vez', 'vezes', 'tipo',
    'fazer', 'feito', 'real', 'novo', 'nova', 'grandes', 'grande', 'melhor',
    'usar', 'usar', 'usar', 'alem', 'ainda', 'isso', 'este', 'aqui',
}

PATTERN_MAIN = re.compile(
    r'^([A-Za-z]+)_(\d+)_(blog|wp|li|ig|fb|tt|linkedin|instagram|facebook|tiktok|meta)_(.+?)_([a-f0-9]{8})',
    re.IGNORECASE
)
PATTERN_SUB = re.compile(
    r'^([A-Za-z]+)_([A-Za-z]+)_(\d+)_(blog|wp|li|ig|fb|tt|linkedin|instagram|facebook|tiktok|meta)_(.+?)_([a-f0-9]{8})',
    re.IGNORECASE
)


# ─────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────

def load_env_file(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def normalize(text):
    """Remove acentos e caracteres especiais, retorna texto minúsculo."""
    text = text.lower()
    for src, dst in [('áàãâä','a'),('éèêë','e'),('íìîï','i'),('óòõôö','o'),('úùûü','u'),('ç','c')]:
        for c in src:
            text = text.replace(c, dst)
    return re.sub(r'[^a-z0-9\-]', '', text)


def extract_words(slug_or_text):
    """Extrai palavras significativas de um slug ou texto livre."""
    normalized = normalize(slug_or_text)
    words = re.split(r'[\-\s_]+', normalized)
    return {w for w in words if len(w) >= 4 and w not in STOPWORDS}


# ─────────────────────────────────────────────
# Fetch e parse da biblioteca WP
# ─────────────────────────────────────────────

def fetch_all_media(wp_url, wp_user, wp_pass):
    base = wp_url.rstrip("/") + "/wp-json/wp/v2/media"
    auth = (wp_user, wp_pass)

    resp = requests.get(base, params={"per_page": 100, "page": 1}, auth=auth, timeout=30)
    resp.raise_for_status()
    total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
    total_items = int(resp.headers.get("X-WP-Total", 0))
    print(f"  [MEDIA] {total_items} itens em {total_pages} páginas")

    items = resp.json()
    for page in range(2, total_pages + 1):
        r = requests.get(base, params={"per_page": 100, "page": page}, auth=auth, timeout=30)
        r.raise_for_status()
        items.extend(r.json())
        print(f"  [MEDIA] Página {page}/{total_pages} ({len(items)} itens acumulados)")

    return items


def parse_slug(slug, url):
    m = PATTERN_SUB.match(slug)
    if m:
        prefix, sub, num, typ, topic_slug, _ = m.groups()
        return dict(
            prefix=f"{prefix}_{sub}".lower(),
            num=int(num),
            type=TYPE_MAP.get(typ.lower(), typ.lower()),
            topic_slug=topic_slug,
            url=url,
        )
    m = PATTERN_MAIN.match(slug)
    if m:
        prefix, num, typ, topic_slug, _ = m.groups()
        return dict(
            prefix=prefix.lower(),
            num=int(num),
            type=TYPE_MAP.get(typ.lower(), typ.lower()),
            topic_slug=topic_slug,
            url=url,
        )
    return None


def build_index(items, existing_index=None):
    """
    Constrói o índice de grupos de imagens.
    Se existing_index é passado, preserva use_count e assigned_to existentes.
    """
    groups = {}

    for item in items:
        slug = item.get("slug", "")
        url  = item.get("source_url", "")
        if not slug or not url:
            continue

        parsed = parse_slug(slug, url)
        if not parsed:
            continue

        key = f"{parsed['prefix']}_{parsed['num']}"
        if key not in groups:
            groups[key] = {
                "topic_slug":  parsed["topic_slug"],
                "topic_words": list(extract_words(parsed["topic_slug"])),
                "use_count":   0,
                "assigned_to": [],   # lista de article_ids que usaram este grupo
            }
            # Preserva histórico de uso de índice anterior
            if existing_index and key in existing_index:
                prev = existing_index[key]
                groups[key]["use_count"]   = prev.get("use_count", 0)
                groups[key]["assigned_to"] = prev.get("assigned_to", [])

        t = parsed["type"]
        if t not in groups[key]:
            groups[key][t] = parsed["url"]

        if t == "meta":
            if "instagram" not in groups[key]:
                groups[key]["instagram"] = parsed["url"]
            if "facebook" not in groups[key]:
                groups[key]["facebook"] = parsed["url"]

    for key, entry in groups.items():
        available = sum(1 for t in SOCIAL_TYPES if t in entry)
        entry["completude"] = round(available / len(SOCIAL_TYPES), 2)

    return groups


# ─────────────────────────────────────────────
# Persistência
# ─────────────────────────────────────────────

def save_index(groups, path=INDEX_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    used_count = sum(1 for e in groups.values() if e.get("use_count", 0) > 0)
    data = {
        "generated_at":    datetime.now().isoformat(),
        "total_groups":    len(groups),
        "used_count":      used_count,
        "available_count": len(groups) - used_count,
        "images":          groups,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [INDEX] Salvo: {path} | {len(groups)} grupos | {used_count} usados | {len(groups)-used_count} disponíveis")


def load_index(path=INDEX_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("images", {})


# ─────────────────────────────────────────────
# Scoring e match
# ─────────────────────────────────────────────

def similarity_score(article_words, image_words):
    """Jaccard similarity entre dois sets de palavras."""
    if not article_words or not image_words:
        return 0.0
    intersection = article_words & image_words
    union        = article_words | image_words
    return len(intersection) / len(union)


def repetition_penalty(use_count):
    """
    Penalidade progressiva por reutilização.
    use_count=0 → sem penalidade (1.0)
    use_count=1 → 50% do score
    use_count=2 → 25%
    use_count=3+ → 10%
    """
    if use_count == 0:
        return 1.0
    if use_count == 1:
        return 0.5
    if use_count == 2:
        return 0.25
    return 0.10


def get_images_for_article(article_id, topic, index, min_similarity=0.03):
    """
    Encontra o melhor grupo de imagens para um artigo.

    Score final por grupo:
      raw    = (jaccard_similarity * 0.80) + (completude * 0.20)
      final  = raw * repetition_penalty(use_count)

    Permite repetição mas penaliza progressivamente:
      nunca usado  → score cheio
      1x usado     → 50% do score
      2x usado     → 25%
      3x+ usado    → 10%

    Retorna (urls_dict, score, matched_key) ou (None, 0, None).
    """
    if not index:
        return None, 0, None

    article_words = extract_words(topic)
    best_key   = None
    best_score = 0.0

    for key, entry in index.items():
        if "blog" not in entry:
            continue

        img_words  = set(entry.get("topic_words", []))
        sim        = similarity_score(article_words, img_words)
        completude = entry.get("completude", 0)
        raw_score  = (sim * 0.80) + (completude * 0.20)
        use_count  = entry.get("use_count", 0)
        final      = raw_score * repetition_penalty(use_count)

        if final > best_score:
            best_score = final
            best_key   = key

    if best_key is None or best_score < min_similarity:
        return None, 0, None

    entry = index[best_key]
    entry["use_count"] = entry.get("use_count", 0) + 1
    assigned = entry.get("assigned_to", [])
    if article_id not in assigned:
        assigned.append(article_id)
    entry["assigned_to"] = assigned

    urls = {
        "blog":      entry.get("blog"),
        "linkedin":  entry.get("linkedin"),
        "instagram": entry.get("instagram") or entry.get("meta"),
        "facebook":  entry.get("facebook") or entry.get("meta"),
        "tiktok":    entry.get("tiktok"),
    }
    return urls, round(best_score, 3), best_key


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def cmd_show(index):
    print(f"\n{'─'*70}")
    print(f"{'CHAVE':<20} {'TOPIC_SLUG':<38} {'COMP':>5} {'USOS':>5} {'ARTIGOS'}")
    print(f"{'─'*70}")
    for key, entry in sorted(index.items()):
        slug      = entry.get("topic_slug", "")[:36]
        comp      = entry.get("completude", 0)
        use_count = entry.get("use_count", 0)
        assigned  = ", ".join(entry.get("assigned_to", [])) or "—"
        print(f"{key:<20} {slug:<38} {comp:>5.2f} {use_count:>5}   {assigned[:30]}")
    print(f"{'─'*70}")
    used_c = sum(1 for e in index.values() if e.get("use_count", 0) > 0)
    print(f"Total: {len(index)} grupos | {used_c} já usados | {len(index)-used_c} nunca usados\n")


def cmd_reset(index, path):
    for entry in index.values():
        entry["use_count"]   = 0
        entry["assigned_to"] = []
    save_index(index, path)
    print(f"✅ Contadores zerados. {len(index)} grupos prontos para novo ciclo.")


def main():
    load_env_file()

    parser = argparse.ArgumentParser(description="Orbit Media Indexer")
    parser.add_argument("--wp_url",  default=os.environ.get("WORDPRESS_URL"))
    parser.add_argument("--wp_user", default=os.environ.get("WORDPRESS_USER"))
    parser.add_argument("--wp_pass", default=os.environ.get("WORDPRESS_PASSWORD"))
    parser.add_argument("--output",  default=INDEX_PATH)
    parser.add_argument("--reset",   action="store_true", help="Zera todos os flags 'used' sem rebuscar o WP")
    parser.add_argument("--show",    action="store_true", help="Exibe o índice atual sem buscar o WP")
    args = parser.parse_args()

    print(f"\n=== ORBIT MEDIA INDEXER ===")

    if args.show:
        index = load_index(args.output)
        if not index:
            print("[AVISO] Índice não encontrado. Rode sem --show para gerar.")
        else:
            cmd_show(index)
        return

    if args.reset:
        index = load_index(args.output)
        if not index:
            print("[AVISO] Índice não encontrado.")
        else:
            cmd_reset(index, args.output)
        return

    if not all([args.wp_url, args.wp_user, args.wp_pass]):
        print("[ERRO] Informe --wp_url, --wp_user e --wp_pass (ou defina no .env)")
        return

    # Preserva flags de uso de um índice anterior
    existing = load_index(args.output)

    items  = fetch_all_media(args.wp_url, args.wp_user, args.wp_pass)
    groups = build_index(items, existing_index=existing)

    from collections import Counter
    prefix_counts = Counter(k.rsplit("_", 1)[0] for k in groups)
    type_counts   = Counter(t for e in groups.values() for t in SOCIAL_TYPES if t in e)

    print(f"\n  Grupos por prefixo: { dict(sorted(prefix_counts.items())) }")
    print(f"  Imagens por tipo:   { dict(sorted(type_counts.items())) }")

    save_index(groups, args.output)
    print(f"\n✅ Concluído. Use 'from orbit_media_indexer import load_index, get_images_for_article'\n")


if __name__ == "__main__":
    main()
