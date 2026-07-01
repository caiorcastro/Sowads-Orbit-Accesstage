# -*- coding: utf-8 -*-
"""
image_gen_v3.py — EXPERIMENTAL. Imagem por artigo com CONTEXTO do conteúdo + variação real.

Fluxo por artigo:
  1) minimax gera 12 briefings de cena DIVERSOS, ancorados no RESUMO do artigo (o que aparece
     na tela/documentos reflete o tema) e no contexto do escritório Accesstage.
  2) minimax ESCOLHE o melhor: melhor representa o conteúdo E é o mais diferente dos já escolhidos
     no lote (evita repetição de composição/pessoas).
  3) gera a imagem (gemini-2.5-flash-image), pós-processo: corte 16:9 protegendo cabeças + barra da marca.

Uso: python3 tools/image_gen_v3.py [N]     (N = quantos artigos, padrão 10)
Saída: output/images_v3_sample/<slug>.png  (+ manifesto com a cena escolhida)
"""
import os, sys, io, csv, json, re, base64
import requests
from dotenv import load_dotenv
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from image_generator import call_image_api, slugify

load_dotenv(os.path.join(BASE, ".env"))
KEY = os.getenv("OPENROUTER_API_KEY")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
TEXT_MODEL = "minimax/minimax-m2.5"          # minimax: gera prompts e escolhe (barato)
IMG_MODEL  = "google/gemini-2.5-flash-image"
CSV = os.path.join(BASE, "output/articles/lote_veragi_lote2_combined.csv")
OUT = os.path.join(BASE, "output/images_v3_sample"); os.makedirs(OUT, exist_ok=True)

# Índices (0-based) de 10 artigos variados do lote2
PICK = [0, 1, 2, 5, 7, 8, 15, 19, 21, 25]

OFFICE = (
    "Setting: a real modern Brazilian CORPORATE FINANCE office of a mid/large company (Accesstage's clients) in "
    "São Paulo — professional, warm, human, credible. Glass meeting rooms, light-wood and neutral tones, a few "
    "plants, natural daylight, São Paulo skyline with buildings visible BEHIND the people through the windows (as "
    "background context, never empty sky). Real Brazilian professionals of varied age, gender and skin tone, "
    "business-casual. NOT futuristic, NOT cold, NO neon, NO holograms."
)
# Enquadramento copiado das referências aprovadas da Accesstage (stock editorial nível dos olhos)
FRAMING = (
    "CAMERA & FRAMING (critical — match professional editorial stock photos): camera at EYE LEVEL, lens pointed "
    "straight ahead — NEVER tilted up, NO ceiling in frame, NO upward angle. MEDIUM SHOT: the main person is LARGE "
    "in the frame, framed from mid-chest/waist up, BOTH shoulders and upper torso clearly visible, the ENTIRE head "
    "and hair FULLY inside the frame with a small clear SAFE gap above — the head must NEVER touch or exceed the top "
    "edge and must NEVER be cropped. "
    "Subject centered or on a third — NOT pushed to an edge, NOT dumped at the bottom. Foreground anchored by a "
    "desk, laptop or seated colleagues. São Paulo skyline sits BEHIND the subject filling the upper third with "
    "buildings — never the main subject, never empty sky. Native WIDE 16:9 landscape, full-bleed edge to edge, "
    "NO white borders, NO letterboxing, NO empty band at top or bottom."
)
GAZE = (
    "GAZE & EXPRESSION (critical): the main person is ALERT and ENGAGED — eyes OPEN and clearly FOCUSED on the "
    "laptop/monitor screen, or on a colleague, or confidently toward camera. Natural confident expression or a "
    "subtle genuine smile. ABSOLUTELY NOT: eyes downcast, eyes half-closed, looking at nothing, staring into "
    "space, daydreaming, blank or tired look, head drooping down."
)
SCREENS = (
    "SCREENS must look like a REAL working screen: a DARKER, muted professional dashboard (NOT a blinding white "
    "screen), realistic SMALL fonts and fine UI details, only SUBTLE minimal reflections. DEVICE LOGIC (critical, "
    "check it): the screen is on the CORRECT face of the device, oriented toward the person using it — a laptop "
    "screen faces its user, a tablet/phone faces the holder. NEVER show a screen on the BACK/rear of a device, NEVER "
    "rotate a device so its screen faces the camera unnaturally. GEOMETRY (check this): the person(s) AND the camera "
    "are on the SAME side as the screen face — the person sits IN FRONT of the device facing its screen and roughly "
    "toward the camera; we see the screen from the front at an angle. NEVER place a person BEHIND the device looking "
    "at the closed back/lid while the screen faces the camera. For TWO people sharing, use a DESKTOP MONITOR on the "
    "desk that both view from the front (like real editorial stock), NOT a shared laptop. Prefer a natural 3/4 angle "
    "so we see BOTH the person's face and the correctly-oriented screen foreshortened. Any on-screen label is SMALL "
    "and in Portuguese (like a real UI), matching the topic — NO giant banner titles, NO huge text, NO English, NO "
    "gibberish. A laptop/monitor in the foreground must be fully inside the frame."
)
BACKGROUND = (
    "BACKGROUND: at most 1-2 people far behind, heavily blurred (strong shallow depth of field), NOT interacting "
    "with their hands (avoid anatomy artifacts). Lighting on the subject and the background must be CONSISTENT."
)
HUMAN = (
    "MOOD — real workday, candid and human (NOT stiff corporate stock, NOT posed): capture a genuine in-between "
    "MOMENT as if a documentary photographer caught it — mid-gesture, mid-conversation, a real reaction, a natural "
    "laugh or genuine focused concentration; people interacting with each other or truly absorbed, NEVER posing, "
    "NEVER a fixed fake smile. Lived-in scene: a slightly used desk (a few papers, a mug, a phone, a notebook), "
    "relaxed natural posture. Editorial feel with soft NATURAL DAYTIME window light (a normal work day, NOT a "
    "dramatic sunset/golden hour, NOT moody), gentle fill, filmic but neutral daytime color, subtle depth-of-field "
    "bokeh, natural real skin texture (not airbrushed). Natural asymmetry and a foreground element (a plant, a "
    "monitor edge, a colleague's shoulder) for depth."
)
GLOBAL_RULES = (
    "Photorealistic candid editorial photography, premium DSLR, believable realistic faces and correct hands, "
    "natural coherent office lighting. " + FRAMING + " " + GAZE + " " + SCREENS + " " + BACKGROUND + " " + HUMAN +
    " NO holograms, NO floating UI, NO glowing 3D, NO sci-fi, NO text overlays, NO bank brands."
)
COMPOSITIONS = ("dupla conversando; pessoa sozinha na mesa; pessoa em pé na janela com skyline; sala de reunião "
    "com 3-4 pessoas; retrato natural sorrindo; pessoa de perfil na mesa; apresentação em tela de parede; "
    "close das mãos com documento e a pessoa parcialmente visível; pequena equipe em pé; pessoa caminhando pelo "
    "corredor; over-the-shoulder no monitor; pessoa recostada analisando; duas pessoas de pé junto a um monitor")

def chat(messages, model=TEXT_MODEL, max_tokens=1400, temp=0.8):
    r = requests.post(OR_URL, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
        "X-Title": "Orbit ImgV3"}, json={"model": model, "messages": messages,
        "temperature": temp, "max_tokens": max_tokens}, timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def extract_json(txt):
    m = re.search(r"\[.*\]", txt, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception:
        try: return json.loads(m.group(0).replace("\n", " "))
        except Exception: return None

def gen_12(title, resumo):
    sys_p = "Você é diretor de fotografia de conteúdo editorial B2B financeiro. Responde só com JSON."
    usr = f"""Artigo (blog Accesstage / plataforma Veragi):
TÍTULO: "{title}"
RESUMO: {resumo}

{OFFICE}

Gere EXATAMENTE 12 briefings de cena fotográfica (em INGLÊS, 1-2 frases cada), TODOS ancorados no tema
específico deste artigo — a atividade da pessoa e o que aparece na tela/documentos deve refletir o assunto.
As 12 devem ser COMPOSIÇÕES DIFERENTES entre si; varie usando estes tipos: {COMPOSITIONS}.
REGRAS OBRIGATÓRIAS em CADA cena:
- Câmera ao NÍVEL DOS OLHOS, PLANO MÉDIO (pessoa grande, do peito pra cima, ombros visíveis), sujeito centrado.
- NUNCA descreva texto legível, títulos ou palavras em telas/documentos (proibido 'titled', 'labeled', nomes em
  tela). Descreva a tela só como 'clean simple dashboard/chart' — sem texto.
- Pessoas brasileiras reais, contexto corporativo humano, sem futurismo, sem holograma.
Responda só com um array JSON de 12 strings."""
    for _ in range(2):
        try:
            arr = extract_json(chat([{"role":"system","content":sys_p},{"role":"user","content":usr}]))
            if arr and len(arr) >= 8:
                return [str(x).strip() for x in arr][:12]
        except Exception as e:
            print("   (retry gen:", str(e)[:60], ")")
    return None

def pick_best(title, resumo, options, chosen, seq=0):
    chosen_txt = "\n".join(f"- {c}" for c in chosen) if chosen else "(nenhuma ainda)"
    opts = "\n".join(f"{i}. {o}" for i, o in enumerate(options))
    usr = f"""Artigo: "{title}"
RESUMO: {resumo}

Cenas JÁ escolhidas para OUTROS artigos deste lote (EVITE algo parecido em composição/nº de pessoas/cenário):
{chosen_txt}

Opções de cena para ESTE artigo:
{opts}

Escolha a ÚNICA opção que (a) melhor representa o conteúdo deste artigo e (b) é a MAIS diferente das já
escolhidas acima. Pense curto e responda por último SÓ com JSON numa linha: {{"idx": <n>, "tag": "<4-6 palavras da composição>"}}"""
    try:
        txt = chat([{"role":"user","content":usr}], max_tokens=1200, temp=0.3) or ""
        matches = re.findall(r"\{[^{}]*\"idx\"[^{}]*\}", txt, re.S)
        o = json.loads(matches[-1]) if matches else json.loads(re.findall(r"\{.*\}", txt, re.S)[-1])
        idx = int(o["idx"]);
        return (idx if 0 <= idx < len(options) else seq % len(options)), o.get("tag", "")
    except Exception as e:
        print("   (pick fallback:", str(e)[:50], ")"); return seq % len(options), ""

def finalize(png, target_ratio=16/9):
    img = Image.open(io.BytesIO(png)).convert("RGB"); w, h = img.size
    # corte 16:9 CENTRALIZADO (nunca ancorar no topo — isso mantinha teto/branco e derrubava o sujeito)
    if w / h < target_ratio:                       # alto demais -> tira topo E base igualmente
        new_h = int(w / target_ratio); y = (h - new_h) // 2
        img = img.crop((0, y, w, y + new_h))
    elif w / h > target_ratio:                     # largo demais -> tira laterais igualmente
        new_w = int(h * target_ratio); x = (w - new_w) // 2
        img = img.crop((x, 0, x + new_w, h))
    w, h = img.size
    bw = max(10, int(w * 0.026)); c1, c2 = (0x44,0x23,0x57), (0xdc,0x16,0x68)
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y/max(1,h-1); grad.putpixel((0,y), tuple(int(c1[i]+(c2[i]-c1[i])*t) for i in range(3)))
    img.paste(grad.resize((bw, h)), (0, 0))
    out = io.BytesIO(); img.save(out, "PNG"); return out.getvalue()

def gen_from_manifest():
    data = json.load(open(os.path.join(OUT, "_manifest.json"), encoding="utf-8"))
    for k, m in enumerate(data, 1):
        print(f"[{k}/{len(data)}] {m['title'][:55]} — [{m['tag']}]")
        raw = call_image_api(f"{m['scene']} {OFFICE} {GLOBAL_RULES}", KEY, IMG_MODEL)
        if not raw: print("   ✗ imagem falhou"); continue
        with open(os.path.join(OUT, f"{m['slug']}.png"), "wb") as f: f.write(finalize(raw))
        print(f"   ✓ {m['slug']}.png")
    print(f"\n✓ {len(data)} imagens (reaproveitando escolhas do minimax)")

def main():
    if "--test" in sys.argv:
        # Teste de ENQUADRAMENTO (espelha a referência 3: pessoa sentada ao laptop, plano médio, nível dos olhos)
        scene = ("Two Brazilian finance colleagues at a desk in a São Paulo corporate office having a real working "
                 "conversation — the woman mid-gesture explaining something on an open laptop that shows clean "
                 "abstract chart shapes with no text, the man beside her listening and reacting with a natural "
                 "half-smile; candid caught moment, not posed, both engaged with each other; a lived-in desk with a "
                 "few papers, a coffee mug and a phone; warm directional window light, São Paulo skyline softly "
                 "blurred behind them.")
        raw = call_image_api(f"{scene} {OFFICE} {GLOBAL_RULES}", KEY, IMG_MODEL)
        if raw:
            with open(os.path.join(OUT, "_TEST_enquadramento.png"), "wb") as f: f.write(finalize(raw))
            print("✓ teste salvo: output/images_v3_sample/_TEST_enquadramento.png")
        else:
            print("✗ falhou")
        return
    if "--test3" in sys.argv:
        # 3 temas distintos: composição variada + tela com rótulo PT-BR do tema + gancho visual
        tests = [
            ("roi", "Two Brazilian finance colleagues sitting side by side IN FRONT of a DESKTOP MONITOR on the desk "
             "(the monitor screen faces them and the camera); the woman mid-gesture pointing at the monitor "
             "explaining, the man beside her leaning in reacting with a natural half-smile; candid working moment; we "
             "see both faces in 3/4 and the monitor showing a real DARK dashboard with a small before/after bar "
             "chart, a subtle green up arrow and a tiny Portuguese label 'ROI Contas a Pagar' in small UI font; "
             "lived-in desk with papers and a mug."),
            ("lgpd", "OVER-THE-SHOULDER view from behind and slightly beside a seated Brazilian woman finance "
             "professional: we see the back of her shoulder and her head in profile, and BEYOND her, her open laptop "
             "whose screen correctly faces her (so the camera behind her also reads it) — the laptop screen shows a "
             "real DARK access-control dashboard with a small padlock icon and a tiny Portuguese label 'Acessos e "
             "Dados' in small UI font; an ID badge on the desk; natural daytime light; a colleague softly blurred "
             "through glass. The screen faces AWAY from the camera in the same direction the woman looks (correct)."),
            ("selic", "Natural 3/4 side angle of a Brazilian man finance professional seated at his desk looking at "
             "his desktop MONITOR (correctly facing him); we see his face in 3/4 and the monitor at an angle showing "
             "a real DARK dashboard with a line chart rising steeply and a tiny Portuguese label 'Selic' in small UI "
             "font; analytical focused expression; São Paulo skyline softly blurred behind through the window."),
        ]
        for name, scene in tests:
            print(f"[test3] {name} …")
            raw = call_image_api(f"{scene} {OFFICE} {GLOBAL_RULES}", KEY, IMG_MODEL)
            if not raw: print("   ✗ falhou"); continue
            with open(os.path.join(OUT, f"_TEST3_{name}.png"), "wb") as f: f.write(finalize(raw))
            print(f"   ✓ _TEST3_{name}.png")
        return
    if "--from_manifest" in sys.argv:
        return gen_from_manifest()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    n = int(args[0]) if args else 10
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    picks = [rows[i] for i in PICK[:n]]
    chosen, manifest = [], []
    for k, row in enumerate(picks, 1):
        title = row.get("post_title", "").strip()
        resumo = (row.get("meta_description") or row.get("original_theme") or "").strip()
        slug = slugify(title)
        print(f"\n[{k}/{len(picks)}] {title[:58]}")
        opts = gen_12(title, resumo)
        if not opts:
            print("   ✗ não gerou prompts"); continue
        idx, tag = pick_best(title, resumo, opts, chosen, seq=k-1)
        scene = opts[idx]; chosen.append(tag or scene[:50])
        print(f"   → minimax escolheu #{idx}: [{tag}]")
        print(f"     {scene[:100]}")
        manifest.append({"slug": slug, "title": title, "idx": idx, "tag": tag, "scene": scene})
        if dry:
            continue
        raw = call_image_api(f"{scene} {OFFICE} {GLOBAL_RULES}", KEY, IMG_MODEL)
        if not raw: print("   ✗ imagem falhou"); continue
        with open(os.path.join(OUT, f"{slug}.png"), "wb") as f: f.write(finalize(raw))
        print(f"   ✓ {slug}.png")
    with open(os.path.join(OUT, "_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    tags = [m["tag"] or m["scene"][:30] for m in manifest]
    print(f"\n{'DRY — ' if dry else ''}{len(manifest)} escolhas | diversidade de composições:")
    for t in tags: print("   •", t)

if __name__ == "__main__":
    main()
