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

# Brand colors Accesstage/Veragi
BRAND_COLOR_MAIN = "#442357"   # roxo profundo
BRAND_COLOR_ACC  = "#dc1668"   # magenta/rosa

# Estilo visual consistente injetado em todos os prompts
STYLE_SUFFIX = (
    "Professional fintech corporate illustration, abstract and geometric, "
    f"deep purple ({BRAND_COLOR_MAIN}) and magenta ({BRAND_COLOR_ACC}) color palette, "
    "clean minimal design, no text, no people, no logos, no faces, "
    "high resolution, 16:9 aspect ratio, editorial blog header image."
)

# Mapeamento tema → conceito visual
TOPIC_VISUALS = {
    "contas a pagar":     "Abstract payment flow: geometric document icons, approval checkmarks, automated pipeline connecting nodes",
    "pagamento":          "Digital payment network: flowing data streams, transaction nodes, secure vault icon",
    "tesouraria":         "Corporate treasury visualization: multi-bank connections, balance scales, cash flow rivers between nodes",
    "conciliação":        "Data reconciliation: parallel data streams merging, balance checkpoints, synchronized nodes",
    "crédito":            "Capital flow network: receivables growing upward, connected supply chain nodes, credit bridge",
    "recebíveis":         "Receivables acceleration: upward growth arrows, funding flow, financial acceleration tunnel",
    "antecipação":        "Acceleration of capital: compressed time arrow, cash flow acceleration, forward momentum",
    "supply chain":       "Supply chain finance: interconnected company nodes, credit bridge, financial health shield",
    "analytics":          "Predictive data dashboard: abstract 3D charts, neural network patterns, decision tree glowing",
    "dados":              "Data intelligence: floating data particles forming insights, abstract neural visualization",
    "edi":                "Digital file exchange: secure data highway, structured protocol nodes, bank connections",
    "api":                "API connectivity: abstract mesh of connected nodes, real-time data streams, open finance bridge",
    "open finance":       "Open finance ecosystem: bank icons connected by glowing API bridges, data sovereignty shield",
    "cnab":               "Financial file standardization: structured data blocks, bank-to-company secure channel",
    "van bancária":       "Banking VAN: secure file transmission tube, document packets flowing between entities",
    "baas":               "Banking as a Service: cloud platform with embedded financial modules, scalable tech architecture",
    "cash pooling":       "Cash pooling centralization: multiple entities funneling resources into central hub, efficiency rings",
    "integração":         "System integration: interconnected platforms, seamless data bridges, modular architecture",
    "gestão financeira":  "Financial management platform: centralized dashboard abstraction, control tower over data flows",
    "software financeiro":"Corporate financial software: abstract UI modules floating, integrated workflow visualization",
    "centralização":      "Centralized control: hub-and-spoke architecture, unified command center, converging streams",
    "tesoureiro":         "Treasury operations: multi-account overview, cash position matrix, strategic allocation map",
    "planejamento":       "Financial planning: strategic roadmap visualization, scenario branches, forecast horizon",
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
