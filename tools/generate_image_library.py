#!/usr/bin/env python3
"""
generate_image_library.py — Gera biblioteca de 60 imagens editoriais para o cliente.

Uso:
  python3 tools/generate_image_library.py
  python3 tools/generate_image_library.py --output_dir output/images/biblioteca
  python3 tools/generate_image_library.py --start 21  # retoma a partir da imagem 21

Saída: output/images/ (ou --output_dir) com arquivos nomeados descritivamente.
"""
import os, re, sys, io, time, base64, argparse
import requests
from dotenv import load_dotenv
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"

STYLE = (
    "Photorealistic editorial photography, premium DSLR quality, warm natural tones. "
    "Setting: modern corporate office in São Paulo, Brazil. São Paulo city skyline visible through large windows where applicable. "
    "Glass partitions, tropical plants, light-wood furniture, colleagues naturally in background. "
    "People: Brazilian professionals, natural diversity — skin tones from fair/olive to warm medium-brown, "
    "natural hair, genuine expressions, engaged in activity — NOT posing for camera. "
    "Lighting: warm soft natural window light, realistic office ambient. No studio flash. "
    "BRAND ACCENT: one single thin vertical stripe — deep Accesstage purple or hot magenta — on ONE far edge only, "
    "like a thin architectural column. Subtle and elegant. No numbers or text on stripe. "
    "NO watermarks. NO text overlays. NO logos. Output: wide horizontal composition."
)

# 60 imagens com máxima variedade de pose, tema, número de pessoas e contexto
LIBRARY = [
    # ── SOLO · MESA / WORKSTATION ──────────────────────────────────────────────
    ("solo-01-mulher-dashboard-manha",
     "Brazilian woman with natural curly hair at MacBook reviewing financial analytics dashboard, warm morning light, steaming coffee mug, notebook beside laptop, soft smile of someone in control, open-plan office colleagues blurred behind"),

    ("solo-02-homem-dual-monitor-relaxado",
     "Brazilian man in striped shirt and tie at dual monitors showing Excel spreadsheets and charts, leaning back in executive chair with relaxed confidence, one hand on armrest, slight smile, plants and colleagues visible behind"),

    ("solo-03-mulher-tablet-de-pe",
     "Brazilian woman in blue blazer standing at her desk holding tablet with financial dashboard, reviewing data while standing, dynamic posture, São Paulo skyline clearly behind through floor-to-ceiling windows"),

    ("solo-04-homem-laptop-entardecer",
     "Brazilian man at laptop in corner office, late afternoon golden light from window beside him casting warm glow, city skyline at dusk behind, thoughtful evaluative expression, coffee cup and documents on desk"),

    ("solo-05-mulher-standing-desk-digitando",
     "Brazilian woman at height-adjustable standing desk typing on laptop, active upright posture, headphones around neck, bright open-plan office with colleagues at desks in background, energetic midday atmosphere"),

    ("solo-06-homem-relatorio-impresso",
     "Brazilian man at tidy desk reviewing printed financial report, marking with pen, organized desk with laptop closed beside, focused methodical expression, quiet executive office, afternoon light"),

    ("solo-07-mulher-graficos-na-tela",
     "Brazilian woman at workstation with large monitor showing colorful financial charts and KPI panels, leaning forward with engaged analytical posture, one hand on chin, open office floor behind her"),

    ("solo-08-homem-executivo-ao-telefone",
     "Brazilian male executive at clean minimalist desk on phone call, one hand gesturing naturally while speaking, confident and composed, city panorama visible through large window behind him"),

    ("solo-09-mulher-caderno-laptop",
     "Brazilian woman at desk with laptop and open notebook, writing notes while reading screen, focused and organized expression, warm desk lamp and coffee mug, quiet open-plan office background"),

    ("solo-10-homem-smartphone-alerta",
     "Brazilian man in modern open office checking smartphone with alert/notification visible on screen, standing beside his desk, quick attentive glance down at phone, colleagues and glass walls behind"),

    # ── SOLO · EM MOVIMENTO / DE PÉ ────────────────────────────────────────────
    ("movimento-01-cfo-andando-tablet",
     "Brazilian CFO walking purposefully through bright open-plan office carrying tablet, colleagues visible at desks on both sides, motion blur suggesting forward movement, professional and decisive energy"),

    ("movimento-02-mulher-corredor-smartphone",
     "Brazilian woman walking through glass-walled corporate corridor checking smartphone, brisk professional stride, reflections in glass walls, São Paulo building visible at end of corridor"),

    ("movimento-03-homem-janela-panoramica",
     "Brazilian man standing at floor-to-ceiling panoramic window overlooking São Paulo skyline, hands clasped behind back, contemplative strategic posture, warm natural backlight silhouetting him slightly"),

    ("movimento-04-mulher-janela-bracos-cruzados",
     "Brazilian woman leaning against glass wall beside window, arms loosely crossed, looking at São Paulo skyline with confident expression, blazer, natural relaxed leadership posture"),

    ("movimento-05-homem-cafe-break",
     "Brazilian man at sleek office kitchen counter making espresso, relaxed natural smile, brief mental break from work, modern corporate kitchen with plants and glass walls, colleagues visible in background"),

    ("movimento-06-mulher-quadro-branco",
     "Brazilian woman at large whiteboard drawing financial flow diagram with marker, one hand pointing at diagram as if explaining to herself, focused creative energy, meeting room with chairs visible"),

    ("movimento-07-homem-escada-moderna",
     "Brazilian man in suit walking up modern open staircase in corporate office building, one hand on railing, looking ahead with purposeful expression, atrium with plants and glass walls"),

    ("movimento-08-mulher-lobby-chegando",
     "Brazilian woman entering bright corporate office lobby, briefcase in hand, confident professional stride, large glass facade with São Paulo street barely visible outside, security desk and plants"),

    # ── DUPLA · COLABORAÇÃO ────────────────────────────────────────────────────
    ("dupla-01-mesa-laptop-revisando",
     "Two Brazilian finance professionals — man and woman — side-by-side at desk reviewing laptop screen together, one pointing at data on screen, natural engaged conversation, open office behind them"),

    ("dupla-02-standing-desk-documentos",
     "Brazilian man and woman standing at high desk going through printed documents spread on surface, both leaning in, natural collaborative discussion, bright office with São Paulo view"),

    ("dupla-03-cafe-lounge-proposta",
     "Two Brazilian women at café-style table in office lounge area, laptops open reviewing proposal, casual but professional atmosphere, warm lighting, plants and soft seating area"),

    ("dupla-04-monitores-comparando",
     "Two Brazilian finance professionals sitting side-by-side at adjacent monitors comparing data on both screens, one explaining to the other with natural hand gesture, organized desk setup"),

    ("dupla-05-aperto-maos-janela",
     "Brazilian man and woman shaking hands confidently after successful meeting, city skyline visible through large windows behind them, professional satisfaction visible in both expressions"),

    ("dupla-06-corredor-caminhando-conversando",
     "Brazilian man and woman walking together through corporate corridor in natural mid-conversation, both carrying documents, collegial energy, glass offices visible on both sides"),

    ("dupla-07-mentoria-mesa",
     "Senior Brazilian finance professional mentoring junior colleague at desk, senior leaning in pointing at laptop screen, junior taking notes, attentive learning atmosphere, warm office light"),

    ("dupla-08-quadro-mapeando",
     "Two Brazilian professionals at whiteboard mapping out process together, one writing, one pointing and suggesting, engaged creative collaboration, meeting room with table and chairs behind"),

    ("dupla-09-videochamada-laptop",
     "Brazilian professional at desk on video call, laptop screen showing blurred remote colleagues, natural conversational gesture with one hand, focused and engaged expression, office light"),

    ("dupla-10-contrato-mesa",
     "Two Brazilian professionals reviewing printed contract on meeting table, both leaning over document, one pointing at specific clause, professional evaluative discussion, pens and glasses on table"),

    # ── GRUPO · REUNIÕES ───────────────────────────────────────────────────────
    ("grupo-01-mesa-redonda-3-laptops",
     "Three Brazilian professionals at round table with laptops open, engaged group discussion, one speaking while two listen and take notes, São Paulo skyline through window, warm meeting room"),

    ("grupo-02-reuniao-rapida-alta",
     "Three Brazilian professionals in standing quick-sync meeting at high café-style table, no chairs, casual upright energy, all three engaged in natural discussion, bright open office"),

    ("grupo-03-sala-projetor",
     "Four Brazilian professionals in glass-walled conference room, one presenting at projected screen showing dashboard, three seated at table with laptops, engaged strategic discussion"),

    ("grupo-04-sala-vidro-discussao",
     "Four people in glass meeting room visible from outside through glass wall, animated professional discussion, documents on table, city skyline behind them through exterior windows"),

    ("grupo-05-celebracao-equipe",
     "Small Brazilian finance team celebrating successful close — three professionals in natural fist-bump or brief celebratory gesture, genuine smiles, office background, authentic moment"),

    ("grupo-06-briefing-manha-tela",
     "Finance team morning briefing — four professionals standing around a wall-mounted screen showing KPI dashboard, one pointing at metric, others with coffee cups, energetic start-of-day atmosphere"),

    ("grupo-07-lounge-laptops",
     "Mixed team of three in casual office lounge area, laptops on low table between them, relaxed but engaged working session, plants, soft seating, natural afternoon light"),

    ("grupo-08-slides-apresentacao",
     "Three professionals reviewing presentation slides together — one standing scrolling through deck on laptop, two leaning in from either side, collaborative pre-meeting review energy"),

    # ── CONTEXTOS FINANCEIROS ESPECÍFICOS ─────────────────────────────────────
    ("financeiro-01-dashboard-tela-grande",
     "Financial analytics dashboard displayed on large wall-mounted screen in modern operations room, one Brazilian professional standing in front reviewing metrics, hands behind back, professional and confident"),

    ("financeiro-02-maos-teclado-dashboard",
     "Close-medium shot: Brazilian professional's hands actively typing on keyboard with financial dashboard clearly visible on monitor in background, focused productive moment, desk in sharp focus"),

    ("financeiro-03-ombro-cfo-analytics",
     "Over-shoulder shot of Brazilian CFO at large curved monitor reviewing real-time financial analytics with multiple KPI panels, viewer sees both the professional and the detailed dashboard simultaneously"),

    ("financeiro-04-open-plan-financeiro",
     "Wide shot of modern São Paulo financial operations floor — multiple Brazilian professionals at workstations, organized open plan, screens visible with financial data, professional and efficient atmosphere"),

    ("financeiro-05-smartphone-app-financeiro",
     "Brazilian professional's hands holding smartphone with financial management app visible on screen, standing in office, São Paulo skyline softly blurred behind through window"),

    ("financeiro-06-documentos-pessoa-fundo",
     "Organized stack of financial reports and documents in foreground, Brazilian professional working at laptop blurred in background in warm office light, depth-of-field composition"),

    ("financeiro-07-tablet-grafico-de-pe",
     "Brazilian woman standing near window holding tablet displaying upward trend chart, reviewing with one finger pointing at data point, São Paulo skyline behind, analytical confident expression"),

    ("financeiro-08-multiplos-bancos-monitor",
     "Brazilian treasury professional at wide monitor showing multiple banking portal tabs consolidated into unified view, methodical efficient expression, headset on desk, organized workspace"),

    ("financeiro-09-trabalho-noturno",
     "Brazilian finance professional working late at night at desk, monitor glow illuminating face, city lights visible through dark window behind, dedicated focused expression, coffee mug"),

    ("financeiro-10-lobby-banco",
     "Brazilian professional in suit at meeting in modern bank branch lobby, seated across small table from representative, professional and composed, modern banking environment"),

    # ── EXECUTIVO · LIDERANÇA ──────────────────────────────────────────────────
    ("exec-01-sala-diretoria-cabeceira",
     "Brazilian CFO at head of long executive boardroom table, two colleagues seated on either side reviewing documents, leadership presence, warm executive lighting, city panorama behind"),

    ("exec-02-elevador-smartphone",
     "Brazilian executive in elevator checking smartphone, brief focused look down at screen, glass elevator with office floors visible, modern corporate building"),

    ("exec-03-lider-guiando-equipe",
     "Brazilian team leader walking finance team through open-plan office, gesturing toward something ahead, three colleagues following attentively, dynamic leadership in motion"),

    ("exec-04-corredor-conversa-informal",
     "Two Brazilian senior executives in informal hallway conversation, standing beside glass office wall, relaxed professional exchange, suits and blazers, genuine collegial energy"),

    ("exec-05-relatorio-anual-fisico",
     "Brazilian CFO at executive desk reviewing printed annual report with reading glasses, highlighter in hand, concentrated expression of careful analysis, warm executive office light"),

    ("exec-06-po-de-pe-frente-cidade",
     "Brazilian executive standing confidently, full posture, in front of large floor-to-ceiling window with panoramic São Paulo skyline behind, arms relaxed at sides, natural leadership presence"),

    # ── CONTEXTOS VARIADOS ─────────────────────────────────────────────────────
    ("variado-01-telhado-reuniao",
     "Two Brazilian professionals in casual outdoor meeting on corporate building rooftop terrace, São Paulo skyline as backdrop, tablets on table between them, relaxed strategic discussion"),

    ("variado-02-home-office-hibrido",
     "Brazilian professional at well-organized home office setup, professional blazer, video call visible on laptop, bookshelf in background, bright natural window light, hybrid work environment"),

    ("variado-03-almoco-corporativo",
     "Three Brazilian finance team members at corporate restaurant lunch, natural conversation, professional but relaxed, food visible, casual team bonding moment"),

    ("variado-04-jardim-terraço-laptop",
     "Brazilian professional at corporate terrace/garden working on laptop, comfortable modern outdoor furniture, greenery around, São Paulo buildings visible in distance, pleasant natural light"),

    ("variado-05-coworking-moderno",
     "Brazilian finance professional at modern coworking desk, surrounded by other professionals working independently, open creative space, mix of traditional and startup aesthetic"),

    ("variado-06-saindo-reuniao",
     "Two Brazilian professionals exiting glass-walled meeting room, one holding folder, both in natural post-meeting conversation, corridor extending behind them, light professional energy"),

    ("variado-07-apresentacao-informal",
     "Brazilian professional giving informal standing presentation to small group of 3 colleagues gathered around desk without chairs, showing laptop screen, engaged and direct communication style"),

    ("variado-08-pausa-cafe-reflexao",
     "Brazilian woman finance professional at floor-to-ceiling window with coffee cup in both hands, looking at São Paulo skyline in moment of quiet reflection and strategic thought, warm morning light"),

    ("variado-09-equipe-corredor-movimento",
     "Small Brazilian finance team of three walking together through modern office corridor, all in motion, natural conversation mid-stride, dynamic energy, glass offices on both sides"),

    ("variado-10-profissional-portaria-predio",
     "Brazilian finance professional in business attire walking confidently through modern corporate building entrance, glass facade, natural daylight, São Paulo street subtle in background"),
]


def call_api(prompt: str, api_key: str) -> bytes | None:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://sowads.com.br",
        "X-Title": "Sowads Orbit Image Library",
    }
    try:
        r = requests.post(OPENROUTER_URL, headers=headers, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": f"{prompt}. {STYLE}"}],
            "size": "1792x1024",
        }, timeout=120)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"    ✗ API error: {e}")
        return None

    choices = data.get("choices", [])
    if not choices:
        return None
    msg = choices[0].get("message", {})

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
    return None


def crop_to_landscape(img_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(img_bytes))
    w, h = img.size
    if w == h:
        target_h = int(w * 9 / 16)
        top = (h - target_h) // 4
        img = img.crop((0, top, w, top + target_h))
        img = img.resize((1280, 720), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    return img_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", default=os.path.join(BASE_DIR, "output", "images"))
    parser.add_argument("--start", type=int, default=1, help="Começa a partir da imagem N (para retomar)")
    parser.add_argument("--delay", type=float, default=3.0)
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        print("Erro: OPENROUTER_API_KEY não encontrada no .env")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    total = len(LIBRARY)
    print(f"🖼  Biblioteca Accesstage — {total} imagens")
    print(f"   Modelo : {MODEL}")
    print(f"   Saída  : {args.output_dir}")
    print()

    ok = skipped = errors = 0

    for idx, (slug, prompt) in enumerate(LIBRARY, 1):
        if idx < args.start:
            continue

        out_path = os.path.join(args.output_dir, f"{slug}.png")

        if os.path.exists(out_path):
            print(f"  [{idx:02d}/{total}] ⏭  {slug}")
            skipped += 1
            continue

        print(f"  [{idx:02d}/{total}] ⏳ {slug}")
        t0 = time.time()
        img_bytes = call_api(prompt, api_key)

        if img_bytes:
            img_bytes = crop_to_landscape(img_bytes)
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            elapsed = time.time() - t0
            size_kb = len(img_bytes) // 1024
            print(f"  [{idx:02d}/{total}] ✅ {slug}  ({size_kb}KB, {elapsed:.0f}s)")
            ok += 1
        else:
            print(f"  [{idx:02d}/{total}] ✗  Falhou: {slug}")
            errors += 1

        if idx < total:
            time.sleep(args.delay)

    print()
    print(f"✅ {ok} geradas | ⏭ {skipped} já existiam | ✗ {errors} erros")
    print(f"📂 {args.output_dir}")


if __name__ == "__main__":
    main()
