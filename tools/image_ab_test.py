# -*- coding: utf-8 -*-
"""
image_ab_test.py — A/B de tela: modelo A (dashboard real encaixado via chroma-key) x modelo B (tela escura realista).
Mede o custo real (usage.cost do OpenRouter) de cada abordagem.

Uso: python3 tools/image_ab_test.py
Saída: output/images_ab/A_<tema>.png , B_<tema>.png , _custos.json
"""
import os, io, sys, json, base64
import requests, numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from image_gen_v3 import OFFICE, FRAMING, GAZE, BACKGROUND, HUMAN
load_dotenv(os.path.join(BASE, ".env"))
KEY = os.getenv("OPENROUTER_API_KEY")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
IMG_MODEL = "google/gemini-2.5-flash-image"
OUT = os.path.join(BASE, "output/images_ab"); os.makedirs(OUT, exist_ok=True)
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONTB = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
def f(sz, bold=False): return ImageFont.truetype(FONTB if (bold and os.path.exists(FONTB)) else FONT, sz)

COST = []  # lista de custos por chamada

def call_img(prompt):
    r = requests.post(OR_URL, headers={"Authorization": f"Bearer {KEY}"},
        json={"model": IMG_MODEL, "messages": [{"role": "user", "content": prompt}]}, timeout=120)
    d = r.json()
    cost = (d.get("usage") or {}).get("cost", 0.0); COST.append(cost)
    msg = d.get("choices", [{}])[0].get("message", {})
    for it in msg.get("images", []):
        url = (it.get("image_url") or {}).get("url", "") if isinstance(it, dict) else ""
        if url.startswith("data:image"): return base64.b64decode(url.split(",", 1)[1]), cost
    return None, cost

# ---- regras comuns (sem a parte de SCREENS, que muda por abordagem) ----
COMMON = FRAMING + " " + GAZE + " " + BACKGROUND + " " + HUMAN + " Photorealistic candid editorial DSLR, natural daytime office light. NO holograms, NO sci-fi, NO text overlays."

def finalize(png):
    img = Image.open(io.BytesIO(png)).convert("RGB"); w, h = img.size; tr = 16/9
    if w/h < tr: nh = int(w/tr); y = (h-nh)//2; img = img.crop((0, y, w, y+nh))
    elif w/h > tr: nw = int(h*tr); x = (w-nw)//2; img = img.crop((x, 0, x+nw, h))
    w, h = img.size; bw = max(10, int(w*0.026)); c1, c2 = (0x44,0x23,0x57), (0xdc,0x16,0x68)
    g = Image.new("RGB", (1, h))
    for y in range(h): g.putpixel((0,y), tuple(int(c1[i]+(c2[i]-c1[i])*(y/max(1,h-1))) for i in range(3)))
    img.paste(g.resize((bw, h)), (0, 0)); return img

# ---- dashboards (desenhados, PT-BR, fonte pequena, números reais) ----
def dash_roi():
    W, H = 1000, 640; im = Image.new("RGB", (W, H), (14, 22, 33)); d = ImageDraw.Draw(im)
    d.rectangle([0,0,W,70], fill=(20,30,45)); d.text((28,22), "ROI — Contas a Pagar", font=f(30,1), fill=(235,240,248))
    d.text((30,92), "Custo operacional: Antes x Depois da automação", font=f(19), fill=(150,165,185))
    # barras
    base_y = 430
    d.rectangle([90, base_y-230, 190, base_y], fill=(210,80,80)); d.text((70,base_y+12),"Manual", font=f(18), fill=(200,210,225))
    d.rectangle([260, base_y-90, 360, base_y], fill=(70,190,120)); d.text((225,base_y+12),"Automatizado", font=f(18), fill=(200,210,225))
    d.line([90,base_y,380,base_y], fill=(90,105,125), width=2)
    # KPIs
    d.text((560,120), "-38%", font=f(84,1), fill=(70,200,130)); d.text((565,215), "custo operacional", font=f(20), fill=(160,175,195))
    d.text((560,300), "Payback", font=f(20), fill=(160,175,195)); d.text((560,326), "6 meses", font=f(40,1), fill=(235,240,248))
    d.text((560,410), "Horas/mês economizadas", font=f(18), fill=(160,175,195)); d.text((560,436),"120 h", font=f(34,1), fill=(120,180,240))
    return im

def dash_lgpd():
    W, H = 1000, 640; im = Image.new("RGB", (W, H), (14, 22, 33)); d = ImageDraw.Draw(im)
    d.rectangle([0,0,W,70], fill=(20,30,45)); d.text((28,22), "Acessos e Dados — LGPD", font=f(30,1), fill=(235,240,248))
    # cadeado
    lx, ly = 120, 170; d.rectangle([lx,ly,lx+90,ly+80], fill=(90,120,200)); d.arc([lx+15,ly-55,lx+75,ly+25], 180,360, fill=(90,120,200), width=12)
    d.ellipse([lx+38,ly+25,lx+52,ly+39], fill=(20,30,45))
    rows = [("Diretoria","Total",(70,190,120)), ("Tesouraria","Restrito",(230,180,70)), ("Contas a Pagar","Aprovação",(120,180,240)), ("Auditoria","Somente leitura",(180,140,220))]
    y = 150
    for name, perm, col in rows:
        d.text((320,y), name, font=f(24), fill=(220,228,240))
        d.rounded_rectangle([640,y-4,880,y+30], radius=14, fill=(28,40,58)); d.text((656,y), perm, font=f(18), fill=col)
        y += 62
    d.text((320,430), "Perfis, alçadas e trilha de auditoria", font=f(18), fill=(150,165,185))
    return im

def dash_selic():
    W, H = 1000, 640; im = Image.new("RGB", (W, H), (14, 22, 33)); d = ImageDraw.Draw(im)
    d.rectangle([0,0,W,70], fill=(20,30,45)); d.text((28,22), "Selic x Gestão de Caixa", font=f(30,1), fill=(235,240,248))
    # linha subindo
    pts = [(90,470),(190,440),(290,455),(390,400),(490,410),(590,340),(690,300),(790,210),(870,160)]
    d.line([70,480,900,480], fill=(90,105,125), width=2); d.line([70,110,70,480], fill=(90,105,125), width=2)
    d.line(pts, fill=(120,180,240), width=5)
    for p in pts: d.ellipse([p[0]-4,p[1]-4,p[0]+4,p[1]+4], fill=(150,200,255))
    d.polygon([(870,160),(858,178),(882,178)], fill=(120,180,240))
    d.text((620,120), "13,75%", font=f(56,1), fill=(120,180,240)); d.text((622,185), "Selic a.a.", font=f(20), fill=(160,175,195))
    return im

DASH = {"roi": dash_roi, "lgpd": dash_lgpd, "selic": dash_selic}

# ---- chroma-key: acha o quad verde e encaixa o dashboard em perspectiva ----
def find_green_quad(img):
    a = np.asarray(img.convert("RGB")).astype(int); r, g, b = a[...,0], a[...,1], a[...,2]
    mask = (g > 90) & (g > r + 40) & (g > b + 40)
    ys, xs = np.where(mask)
    if len(xs) < 800: return None
    s, dd = xs+ys, xs-ys
    return [(int(xs[np.argmin(s)]),int(ys[np.argmin(s)])), (int(xs[np.argmax(dd)]),int(ys[np.argmax(dd)])),
            (int(xs[np.argmax(s)]),int(ys[np.argmax(s)])), (int(xs[np.argmin(dd)]),int(ys[np.argmin(dd)]))]

def coeffs(dst, src):
    # mapeia dst(x,y) -> src(u,v) para PIL PERSPECTIVE
    A = []; B = []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u*x, -u*y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v*x, -v*y]); B.append(v)
    res = np.linalg.solve(np.array(A, float), np.array(B, float))
    return tuple(res)

def composite(photo, dash, quad):
    w, h = dash.size; src = [(0,0),(w,0),(w,h),(0,h)]
    c = coeffs(quad, src)
    warped = dash.transform(photo.size, Image.PERSPECTIVE, c, Image.BICUBIC)
    m = Image.new("L", (w, h), 255).transform(photo.size, Image.PERSPECTIVE, c, Image.BICUBIC)
    # leve reflexo/vidro: reduz opacidade só um tico
    photo = photo.convert("RGB"); photo.paste(warped, (0, 0), m); return photo

SCENES = {
 "roi": "Two Brazilian finance colleagues side by side IN FRONT of a desktop monitor on the desk (screen faces them and the camera); the woman gestures toward the monitor explaining, the man leaning in with a natural half-smile; a lived-in desk with a mug.",
 "lgpd": "OVER-THE-SHOULDER from behind and beside a seated Brazilian woman finance professional; we see the back of her shoulder and her head in profile and, beyond her, her open laptop whose screen faces her (camera behind reads it); an ID badge on the desk; a colleague blurred through glass.",
 "selic": "A Brazilian man finance professional seated at his desk looking at his desktop MONITOR (screen faces him and the camera), analytical focused expression; São Paulo skyline softly blurred behind.",
}

def run():
    manifest = {"A": {}, "B": {}}
    # MODELO B — tela escura realista, ilegível
    b_screen = ("The screen shows a REALISTIC DARK financial dashboard UI with many small muted elements, slightly out "
                "of focus and with subtle reflection — it is NOT trying to display any specific readable text (real "
                "screens are unreadable from this distance). Correct device geometry, screen fully in frame.")
    for tema, scene in SCENES.items():
        png, _ = call_img(f"{scene} {b_screen} {OFFICE} {COMMON}")
        if png: finalize(png).save(os.path.join(OUT, f"B_{tema}.png")); manifest["B"][tema] = "ok"
        print(f"B_{tema}: {'ok' if png else 'FALHOU'}")
    b_cost = sum(COST)

    # MODELO A — chroma-key + encaixe do dashboard
    a_screen = ("The monitor/laptop screen is a COMPLETELY UNIFORM SOLID BRIGHT CHROMA-KEY GREEN rectangle (pure green "
                "RGB 0,190,70), no content, no icons, no reflections, filling the ENTIRE screen edge to edge. Correct "
                "device geometry, the whole screen flat and fully visible in frame.")
    for tema, scene in SCENES.items():
        png, _ = call_img(f"{scene} {a_screen} {OFFICE} {COMMON}")
        if not png: print(f"A_{tema}: FALHOU geração"); continue
        photo = Image.open(io.BytesIO(png)).convert("RGB")
        quad = find_green_quad(photo)
        if not quad: print(f"A_{tema}: sem tela verde detectada"); finalize(png).save(os.path.join(OUT, f"A_{tema}.png")); continue
        comp = composite(photo, DASH[tema](), quad)
        buf = io.BytesIO(); comp.save(buf, "PNG")
        finalize(buf.getvalue()).save(os.path.join(OUT, f"A_{tema}.png")); manifest["A"][tema] = "ok"
        print(f"A_{tema}: ok (quad {quad})")
    a_cost = sum(COST) - b_cost

    n_b = len(SCENES); n_a = len(SCENES)
    report = {"modelo_B": {"imgs": n_b, "custo_total_usd": round(b_cost,4), "custo_por_img_usd": round(b_cost/n_b,4)},
              "modelo_A": {"imgs": n_a, "custo_total_usd": round(a_cost,4), "custo_por_img_usd": round(a_cost/n_a,4),
                           "obs": "overlay do dashboard é pós-processo local, custo de API zero"},
              "por_chamada": [round(c,4) for c in COST]}
    json.dump(report, open(os.path.join(OUT, "_custos.json"), "w"), indent=2, ensure_ascii=False)
    print("\n== CUSTO ==", json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    run()
