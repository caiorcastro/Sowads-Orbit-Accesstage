# -*- coding: utf-8 -*-
"""
image_gen_v2.py — EXPERIMENTAL. Testa otimizações de imagem sem tocar no gerador de produção.
Melhorias: mata holograma/3D flutuante, varia arquétipos de cena, corrige enquadramento,
telas sem texto legível, luz variada; e aplica a barra lateral da marca por PÓS-PROCESSO
(gradiente exato do site: #442357 -> #dc1668).

Uso: python3 tools/image_gen_v2.py
Saída: output/images_v2_sample/<slug>.png  (+ _SEM-marca para comparar)
"""
import os, sys, base64
from dotenv import load_dotenv
from PIL import Image
import io

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from image_generator import call_image_api, slugify  # reutiliza a chamada de API que já funciona

load_dotenv(os.path.join(BASE, ".env"))
KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "google/gemini-2.5-flash-image"
OUT = os.path.join(BASE, "output", "images_v2_sample")
os.makedirs(OUT, exist_ok=True)

# Estilo v2 — realismo, sem sci-fi, enquadramento e telas limpas. SEM pedir faixa (vem no pós-processo).
STYLE_V2 = (
    "Photorealistic candid editorial photography, premium DSLR quality, natural realistic people "
    "(believable faces and correct hands), Brazilian corporate finance context. "
    "STRICT NEGATIVES: absolutely NO holograms, NO floating UI, NO glowing 3D projections, NO transparent "
    "floating screens, NO sci-fi, NO futuristic overlays. Only real physical monitors, laptops and paper. "
    "Screens and documents show ABSTRACT charts and graphs only — NO legible text, NO words, NO letters, "
    "NO numbers anywhere (avoid rendering gibberish text). "
    "COMPOSITION 16:9: full head with generous headroom, subject NOT touching the frame edges, nothing "
    "important cropped, clean calm margins. Keep a calm uncluttered vertical strip along the LEFT edge. "
    "LIGHTING: natural and realistic — vary between soft cool daylight and warm afternoon; do NOT always use sunset. "
    "No text overlays, no captions, no logos."
)

# Arquétipos de cena — rotacionar quebra o 'tudo igual/mesmas pessoas'
ARCHETYPES = {
    "macro_still": "Close-up macro still-life on a finance desk: a hand resting near a laptop keyboard, a coffee "
                   "cup, a printed chart document and a pen. NO face, NO people. Shallow depth of field.",
    "two_person":  "Two Brazilian finance colleagues in a glass-walled meeting room reviewing a printed report "
                   "together, one gesturing naturally, candid conversation, nobody looking at the camera.",
    "flat_lay":    "Clean top-down flat-lay of a finance desk seen from directly above: an open laptop showing an "
                   "abstract chart, a notebook, pen, eyeglasses, a coffee cup and a small plant, editorial product style.",
}

# 3 temas-piores + arquétipo distinto para cada, para demonstrar variedade
SAMPLES = [
    ("inteligencia-artificial-na-gestao-financeira", "macro_still",
     "an article about artificial intelligence assisting financial management"),
    ("o-que-e-spread-bancario", "two_person",
     "an article explaining bank spread and its effect on a company's financial cost"),
    ("glossario-do-financeiro-corporativo", "flat_lay",
     "an article that is a glossary of corporate finance terms"),
]

def add_brand_bar(png_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    bw = max(10, int(w * 0.028))          # barra fina ~2.8% da largura
    c1, c2 = (0x44, 0x23, 0x57), (0xdc, 0x16, 0x68)   # #442357 -> #dc1668
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        grad.putpixel((0, y), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    img.paste(grad.resize((bw, h)), (0, 0))
    out = io.BytesIO(); img.save(out, "PNG")
    return out.getvalue()

def main():
    for slug, arch, hook in SAMPLES:
        prompt = f"{ARCHETYPES[arch]} This illustrates {hook}. {STYLE_V2}"
        print(f"[{slug}] arquétipo={arch} …")
        raw = call_image_api(prompt, KEY, MODEL)
        if not raw:
            print(f"  ✗ falhou"); continue
        # salva versão SEM marca (para comparar) e COM marca
        with open(os.path.join(OUT, f"{slug}__SEM-marca.png"), "wb") as f:
            f.write(raw)
        branded = add_brand_bar(raw)
        with open(os.path.join(OUT, f"{slug}.png"), "wb") as f:
            f.write(branded)
        print(f"  ✓ salvo ({len(branded)//1024} KB)")

if __name__ == "__main__":
    main()
