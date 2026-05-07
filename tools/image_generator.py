#!/usr/bin/env python3
"""
image_generator.py — Gera imagens de capa para artigos via OpenRouter.

Uso:
  python3 tools/image_generator.py --from_csv output/articles/<batch>.csv
  python3 tools/image_generator.py --from_csv output/articles/<batch>.csv --model google/gemini-2.5-flash-image

Saída:
  output/images/<slug>.png     ← uma imagem por artigo
  output/images/manifest.csv   ← slug → caminho local

Modelo padrão: google/gemini-2.5-flash-image  (~$0.0003 por 1k imagens)
"""
import os, re, sys, csv, time, base64, argparse, unicodedata
import requests
from dotenv import load_dotenv

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR    = os.path.join(BASE_DIR, "output", "images")
DEFAULT_MODEL = "google/gemini-2.5-flash-image"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

load_dotenv(os.path.join(BASE_DIR, ".env"))

# Estilo editorial natural — pessoas em ambiente real, sem fundo artificial
# O brand aparece como detalhe sutil (faixa lateral, reflexo em tela), não como fundo dominante
STYLE_SUFFIX = (
    "Candid editorial stock photography, photorealistic, natural DSLR quality. "
    "Setting: real modern corporate office or conference room with natural environmental depth. "
    "People: Brazilian or Latin American professionals, natural skin tones, realistic eyes. Expressions: calm, confident, with a natural subtle smile — approachable and professional, not exaggerated, not laughing, not posing. The kind of expression of someone who enjoys their work. "
    "Brand accent: one subtle vertical stripe or thin geometric band in deep purple #442357 or magenta #dc1668 on the far edge of the frame only — not as background. "
    "Composition: IMPORTANT — generate as a true 16:9 wide landscape frame. Person framed from waist or chest up, centered horizontally, with generous headroom — head and shoulders must never be cropped or touch the edges. Environment fills the rest of the frame naturally. "
    "Lighting: natural office light, no dramatic studio lighting, realistic shadows. "
    "Output format: 16:9 horizontal landscape, 1280x720 equivalent proportions, no text, no logos, no watermarks, no stock-photo feel."
)

# Mapeamento tema → cena ambiental com contexto real
TOPIC_VISUALS = {
    "contas a pagar":     "Finance professional at desk working on laptop, relaxed posture, natural slight smile, coffee cup nearby, bright open-plan office",
    "pagamento":          "Business professional at standing desk working on laptop, calm and confident, colleagues in background going about their day",
    "tesouraria":         "Treasury manager at dual monitors, leaning back slightly with quiet confidence, modern corporate office environment",
    "conciliação":        "Financial analyst at desk comparing data on screen, engaged and at ease, natural pleasant expression, finance department",
    "crédito":            "Two business professionals in glass-walled meeting room reviewing documents together, relaxed collaborative atmosphere",
    "recebíveis":         "Finance professional presenting to two colleagues in bright conference room, pointing at chart, engaged and natural",
    "antecipação":        "Entrepreneur working at laptop in modern office, window light, calm and satisfied expression reviewing results",
    "supply chain":       "Mixed team of three professionals around conference table with laptops, engaged in easy conversation, natural energy",
    "analytics":          "Data analyst at large monitor with charts, leaning forward with interest, natural pleasant expression, modern workspace",
    "dados":              "Professional woman at laptop in glass-walled office, city skyline behind, composed and confident, looking at screen",
    "edi":                "Two colleagues at shared desk reviewing system on laptop together, natural conversation, comfortable working dynamic",
    "api":                "Developer and finance professional at laptops side by side at long table, natural collaborative energy, tech office",
    "open finance":       "Executive at clean desk checking smartphone and laptop, composed and at ease, modern fintech office environment",
    "cnab":               "Operations professional at computer reviewing workflow, organized back-office, calm and efficient expression",
    "van bancária":       "Banking operations team at workstations, professional and at ease, well-lit operations center environment",
    "baas":               "Small fintech team in open-plan office, laptops on desks, natural working atmosphere, casual and engaged",
    "cash pooling":       "Senior executive and colleague in boardroom reviewing financial reports on table, natural confident demeanor",
    "integração":         "IT and finance professionals in meeting room with projected diagram, engaged discussion, collaborative and relaxed",
    "gestão financeira":  "Professional woman at clean corporate desk using financial platform on laptop, composed and confident posture",
    "software financeiro":"Team of three in training room, presenter at screen, others attentive and engaged, natural professional setting",
    "centralização":      "Manager with arms crossed overlooking finance operations floor, composed and assured, natural leadership presence",
    "tesoureiro":         "Treasury professional at executive desk reviewing reports on large screen, calm focus, organized professional workspace",
    "planejamento":       "Diverse team in modern boardroom with projections on screen, engaged in natural discussion, relaxed strategic meeting",
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:60]


def build_prompt(title: str) -> str:
    title_lower = title.lower()
    visual_concept = next(
        (v for k, v in TOPIC_VISUALS.items() if k in title_lower),
        "Abstract fintech B2B visualization: geometric corporate data flows, digital transformation, financial intelligence"
    )
    return f"{visual_concept}. {STYLE_SUFFIX}"


def call_image_api(prompt: str, api_key: str, model: str):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://sowads.com.br",
        "X-Title": "Sowads Orbit Image Generator",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"    ✗ Erro na API: {e}")
        return None

    choices = data.get("choices", [])
    if not choices:
        print(f"    ✗ Sem choices na resposta: {list(data.keys())}")
        return None

    msg = choices[0].get("message", {})

    # Formato principal (OpenRouter + Gemini image): msg["images"][0]["image_url"]["url"]
    for item in msg.get("images", []):
        if isinstance(item, dict):
            url = item.get("image_url", {}).get("url", "") or item.get("url", "")
            if url.startswith("data:image"):
                return base64.b64decode(url.split(",", 1)[1])
            if url.startswith("http"):
                return requests.get(url, timeout=30).content
            b64 = item.get("b64_json") or item.get("base64", "")
            if b64:
                return base64.b64decode(b64)
        elif isinstance(item, str):
            return base64.b64decode(item)

    # Fallback: content como lista com image_url
    content = msg.get("content", "")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "image_url":
                url = item.get("image_url", {}).get("url", "")
                if url.startswith("data:image"):
                    return base64.b64decode(url.split(",", 1)[1])
                if url.startswith("http"):
                    return requests.get(url, timeout=30).content

    # Fallback: data URI na string
    if isinstance(content, str):
        match = re.search(r"data:image/\w+;base64,([A-Za-z0-9+/=]+)", content)
        if match:
            return base64.b64decode(match.group(1))

    print(f"    ✗ Imagem não encontrada. msg keys: {list(msg.keys())}")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from_csv", required=True, help="CSV de artigos gerados")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modelo OpenRouter")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay entre imagens (s)")
    parser.add_argument("--skip_existing", action="store_true", default=True,
                        help="Pula artigos que já têm imagem (padrão: True)")
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        print("Erro: OPENROUTER_API_KEY não encontrada no .env")
        sys.exit(1)

    if not os.path.exists(args.from_csv):
        print(f"CSV não encontrado: {args.from_csv}")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)

    with open(args.from_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"🖼  Gerando imagens para {len(rows)} artigos")
    print(f"   Modelo : {args.model}")
    print(f"   Saída  : {OUT_DIR}")
    print()

    manifest = []
    ok = 0
    skipped = 0
    errors = 0

    for idx, row in enumerate(rows, 1):
        title    = row.get("post_title", "").strip()
        slug     = slugify(title)
        out_path = os.path.join(OUT_DIR, f"{slug}.png")

        if args.skip_existing and os.path.exists(out_path):
            print(f"  [{idx:02d}] ⏭  Já existe: {slug}.png")
            manifest.append({"slug": slug, "title": title, "path": out_path, "status": "existing"})
            skipped += 1
            continue

        prompt = build_prompt(title)
        print(f"  [{idx:02d}] ⏳ {title[:55]}...")
        t0 = time.time()

        img_bytes = call_image_api(prompt, api_key, args.model)

        if img_bytes:
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            elapsed = time.time() - t0
            size_kb = len(img_bytes) // 1024
            print(f"  [{idx:02d}] ✅ {slug}.png  ({size_kb} KB, {elapsed:.1f}s)")
            manifest.append({"slug": slug, "title": title, "path": out_path, "status": "ok"})
            ok += 1
        else:
            print(f"  [{idx:02d}] ✗  Falhou: {title[:50]}")
            manifest.append({"slug": slug, "title": title, "path": "", "status": "error"})
            errors += 1

        if idx < len(rows):
            time.sleep(args.delay)

    # Salva manifesto
    manifest_path = os.path.join(OUT_DIR, "manifest.csv")
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["slug", "title", "path", "status"])
        w.writeheader()
        w.writerows(manifest)

    print()
    print(f"✅ {ok} geradas | ⏭  {skipped} já existiam | ✗ {errors} erros")
    print(f"📂 Manifesto: {manifest_path}")


if __name__ == "__main__":
    main()
