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

# Estilo visual da Accesstage: foto real de pessoa + fundo gradiente roxo/magenta
# Referência: hero do blog.accesstage.com.br — pessoa profissional sobre gradiente marca
STYLE_SUFFIX = (
    "Editorial blog header photo, photorealistic, high-quality professional photography. "
    "Subject: confident Brazilian or Latin American professional in business attire, "
    "arms crossed or working, slight smile, sharp focus. "
    "Background: smooth gradient from deep purple #442357 to vivid magenta #dc1668, "
    "with subtle abstract geometric shapes (rectangles, lines) as background accents. "
    "Composition: subject positioned right-of-center or center, generous negative space on left for text overlay. "
    "Lighting: professional studio-quality, soft shadows, vibrant colors. "
    "16:9 aspect ratio, no text, no logos, no watermarks."
)

# Mapeamento tema → persona e postura da foto
TOPIC_VISUALS = {
    "contas a pagar":     "Businesswoman at laptop, reviewing digital invoice on screen, focused expression, slight smile of control and confidence",
    "pagamento":          "Finance professional holding smartphone showing a payment confirmation screen, other hand gesturing approval",
    "tesouraria":         "Senior male executive with arms crossed, confident posture, multiple financial screens visible behind him",
    "conciliação":        "Female financial analyst pointing at two aligned data sets on screen, expression of precision and focus",
    "crédito":            "Smiling Latin American businesswoman extending hand for a handshake, signaling deal closure, trustworthy posture",
    "recebíveis":         "Young professional man presenting upward growth chart on tablet, enthusiastic and engaged expression",
    "antecipação":        "Confident entrepreneur woman looking forward with energy, holding a tablet showing positive financial trend",
    "supply chain":       "Diverse business team of three professionals leaning over a table reviewing documents together, collaborative energy",
    "analytics":          "Data scientist woman pointing at a glowing analytics dashboard on large screen, team engaged in background",
    "dados":              "Professional woman holding a tablet with data visualizations, looking at camera with confident calm expression",
    "edi":                "Two IT professionals — man and woman — reviewing a technical diagram on laptop, collaborative and focused",
    "api":                "Young male developer smiling at laptop in modern fintech office, open-plan background with colleagues",
    "open finance":       "Executive man using smartphone banking app with confidence, standing in modern glass-walled office corridor",
    "cnab":               "Operations professional woman at computer reviewing bank file exchange workflow, systematic and precise expression",
    "van bancária":       "Banking professional man at workstation reviewing secure document transmission, serious and reliable expression",
    "baas":               "Startup fintech team — three young professionals — working on laptops at a collaborative open workspace",
    "cash pooling":       "CFO-type executive man in suit reviewing consolidated group treasury report, boardroom with glass walls",
    "integração":         "Two professionals — man and woman — connecting systems on laptop and tablet, engaged and optimistic expressions",
    "gestão financeira":  "Brazilian executive woman confidently using financial platform on laptop, modern minimalist office setting",
    "software financeiro":"Finance manager presenting new software on screen to attentive team, training session atmosphere",
    "centralização":      "Executive man standing arms crossed before multi-screen financial control dashboard, commanding and assured",
    "tesoureiro":         "Senior treasury professional woman reviewing consolidated cash position on large monitor, focused and in control",
    "planejamento":       "Strategy team around whiteboard with financial charts, engaged discussion, diverse group, modern boardroom",
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
