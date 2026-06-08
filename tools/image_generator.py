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
import os, re, sys, csv, time, base64, argparse, unicodedata, io
import requests
from dotenv import load_dotenv
from PIL import Image

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR    = os.path.join(BASE_DIR, "output", "images")
DEFAULT_MODEL = "google/gemini-2.5-flash-image"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

load_dotenv(os.path.join(BASE_DIR, ".env"))

# Estilo editorial natural — pessoas em ambiente real, sem fundo artificial
# O brand aparece como detalhe sutil (faixa lateral, reflexo em tela), não como fundo dominante
STYLE_SUFFIX = (
    "Photorealistic candid editorial photography, premium DSLR quality, warm natural tones. "
    "MANDATORY SETTING: modern open-plan corporate office in São Paulo, Brazil — São Paulo city skyline ALWAYS clearly visible through large floor-to-ceiling windows (distinctive São Paulo buildings required). "
    "Glass partitions, tropical plants, light-wood furniture, realistic corporate environment. Colleagues naturally at their desks in the background, blurred by shallow depth of field. The office feels lived-in and real. "
    "PEOPLE: Brazilian professionals with natural diversity — skin tones ranging from fair/olive to warm medium-brown. Natural hair textures. Expressive genuine faces, NOT posing for camera, engaged in work at 3/4 angle. "
    "COMPOSITION: wide and spacious — subjects comfortably framed with generous headroom and breathing room around them. Full head always visible. Shoulders and upper torso in frame. NOT too tight or cropped. "
    "SCREENS: realistic financial software — actual-looking Excel charts, banking dashboards, ERP screens. Not blank. "
    "PROPS: MacBook or Dell laptop, coffee mug, printed documents, notebook. "
    "LIGHTING: warm soft natural window light from the side, realistic office ambient fill. No studio flash. "
    "BRAND ACCENT: one single thin vertical stripe — either deep Accesstage purple or hot magenta pink — placed on ONE far edge only (left OR right), like a thin architectural column or wall accent. Subtle, elegant, not dominant. Only one stripe total. No numbers or text on the stripe."
)

# Mapeamento tema → cena ambiental com contexto real
TOPIC_VISUALS = {
    # ── Módulo Contas a Pagar ───────────────────────────────────────────────────
    "contas a pagar":     "Brazilian finance professional at desk with laptop, calm natural smile, relaxed confident posture, bright open-plan corporate office São Paulo",
    "pagamento":          "Finance manager at desk reviewing documents on laptop, composed and confident expression, natural slight smile, modern corporate office environment",
    "comprovante":        "Finance analyst at neat desk holding printed document while checking laptop screen simultaneously, natural bifocal expression of comparison, organized desk with coffee cup",
    "aprovação":          "Mid-level finance manager at glass-walled office desk, reviewing approval workflow on dual monitors, leaning back in chair with pen in hand, calm authoritative posture",
    "auditoria":          "Finance compliance professional at desk with organized folders and laptop open, reviewing detailed reports, focused expression, quiet corporate office late afternoon light",
    "retrabalho":         "Finance professional at cluttered-turning-organized desk, closing a paper folder while laptop shows clean dashboard, transitional relief expression, before-after moment captured",

    # ── Módulo Tesouraria ───────────────────────────────────────────────────────
    "tesouraria":         "Treasury professional at desk with laptop, calm and strategic expression, natural confident smile, corporate office São Paulo with city view",
    "tesoureiro":         "Treasury manager at desk reviewing reports, calm focus and natural smile, organized professional workspace, city skyline background",
    "fechamento":         "Finance analyst at desk with dual monitors, engaged and at ease, natural pleasant expression, organized corporate finance department",
    "multibanco":         "Treasury manager at workstation with multiple bank portals open on wide monitor, efficiently switching views, calm mastery expression, modern finance operations center",
    "extrato":            "Finance professional comparing two screens side by side — one showing bank statement, other showing reconciliation dashboard, engaged analytical expression",
    "saldo":              "Treasury professional reviewing consolidated balance position on large monitor, satisfied expression reviewing green numbers, executive office environment",
    "caixa":              "Finance professional at desk with laptop, calm and composed expression, natural confident smile, bright modern corporate office São Paulo",
    "fluxo":              "Finance director at conference room table reviewing cash flow projections on tablet, two analysts visible in background at screens, collaborative strategic meeting",
    "descasamento":       "Treasurer at dual monitors analyzing timeline chart showing cash gaps, focused problem-solving expression, one hand on keyboard, other on chin, quiet executive office",
    "posição":            "Treasury team leader at workstation reviewing morning position report, cup of espresso steaming nearby, composed and prepared expression, Brazilian corporate office 7am light",

    # ── Módulo Crédito / Risco Sacado ──────────────────────────────────────────
    "crédito":            "Two finance professionals in glass-walled meeting room reviewing credit analysis documents together, engaged discussion over laptop, collaborative professional atmosphere",
    "recebíveis":         "Finance manager presenting receivables dashboard to two colleagues in bright conference room, pointing at chart with natural gesture, engaged and clear",
    "antecipação":        "Finance director at modern office desk reviewing receivables anticipation proposal on laptop, calm satisfied expression after analysis, window light, São Paulo corporate",
    "risco sacado":       "Finance and procurement professionals around small meeting table reviewing supply chain finance documents, focused collaborative discussion, modern fintech office",
    "supply chain":       "Mixed team of three finance professionals around conference table with laptops, one presenting on tablet, engaged in natural supply chain finance discussion",
    "inadimplência":      "Credit risk analyst at large monitor showing predictive analytics dashboard, calm analytical posture, organized corporate office, forward lean of focus",
    "fornecedor":         "Finance professional in video call with supplier visible on monitor, reviewing shared document on laptop, professional and collaborative, corporate office environment",
    "concentração":       "Risk manager reviewing portfolio diversification chart on dual monitors, calm evaluative expression, organized executive desk, professional finance environment",

    # ── Módulo Analytics ────────────────────────────────────────────────────────
    "analytics":          "Data-driven CFO at large curved monitor showing real-time financial analytics dashboard with multiple KPI panels, leaning forward with engaged strategic expression",
    "dados":              "Finance analytics professional at glass-walled office, city skyline behind, laptop showing data visualization, composed and confident, late morning natural light",
    "kpi":                "Finance director reviewing KPI dashboard on wall-mounted screen during standing meeting, one colleague pointing at metric, engaged and action-oriented discussion",
    "relatório":          "CFO at executive desk reviewing comprehensive financial report on large monitor, calm confidence of someone with full information, warm corporate office morning",
    "dashboard":          "Finance team lead at dual monitors with live dashboard, explaining a metric to one colleague standing beside, natural collaborative energy, modern analytics office",
    "planejamento":       "Finance planning team around boardroom table, laptops open, projections on screen, engaged strategic planning session, composed and forward-looking atmosphere",
    "preditivo":          "Finance analyst reviewing predictive scenario model on large monitor, calm analytical expression, organized desk with multiple data sources visible on screens",
    "performance":        "Finance director reviewing quarterly performance results on large monitor, satisfied evaluative posture, executive office with city view, afternoon light",

    # ── Integrações Bancárias ──────────────────────────────────────────────────
    "edi":                "IT and finance professional at shared workstation reviewing EDI file exchange on monitor, natural collaborative discussion, organized tech-finance hybrid office",
    "api":                "Developer and finance professional at adjacent desks working on integration setup, natural side-by-side collaboration, modern open fintech office environment",
    "open finance":       "Finance innovation executive at clean desk reviewing open finance implementation on laptop and smartphone simultaneously, composed and forward-looking",
    "cnab":               "Operations specialist at computer reviewing CNAB file structure with organized workflow screen, calm efficient expression, organized back-office environment",
    "van bancária":       "Financial operations team at workstations in well-lit operations center, professionals at monitors reviewing file transfers, professional and calm atmosphere",
    "baas":               "Fintech product team in bright open-plan office discussing BaaS integration, laptops on desks, engaged and collaborative, casual professional energy",
    "integração":         "IT architect and finance director at meeting room table reviewing system integration diagram projected on screen, engaged professional discussion",
    "migração":           "Senior IT and finance professionals reviewing migration timeline on projected diagram, collaborative planning posture around conference table, organized and strategic",
    "segurança":          "IT security and finance compliance officer reviewing encrypted file transfer protocol on dual monitors, focused professional expression, secure operations environment",
    "erp":                "Finance systems team reviewing ERP integration dashboard, one professional at keyboard, other reviewing printed workflow, collaborative and technical office setting",

    # ── Cash Pooling ────────────────────────────────────────────────────────────
    "cash pooling":       "Senior CFO and treasury director in executive boardroom reviewing cash pooling structure diagram on table, natural confident strategic demeanor, morning light",
    "pooling":            "Group treasury executive reviewing consolidated group cash position on large monitor, calm strategic posture, executive office with company brand visible on wall",
    "saldos ociosos":     "Treasury manager at workstation reviewing group balance optimization chart, calm satisfied expression of found efficiency, modern corporate treasury environment",
    "grupos empresariais":"Group CFO at executive conference table reviewing multi-entity financial structure with two colleagues, organized documents, professional collaborative atmosphere",

    # ── Estratégia / Governança / Liderança ─────────────────────────────────────
    "estratégico":        "Brazilian CFO standing at panoramic office window looking at city skyline, strategic and composed posture, transitioning from operational to strategic leadership moment",
    "governança":         "Board-level finance executives at long conference table reviewing compliance and governance framework, professional and authoritative atmosphere, organized corporate boardroom",
    "cfo":                "Brazilian CFO at executive desk with city view, reviewing financial platform on laptop with calm decisive expression, leadership presence, morning executive office",
    "compliance":         "Finance compliance officer at organized desk reviewing regulatory documentation on laptop, methodical and calm professional expression, quiet corporate office",
    "centro de serviços": "Financial shared services center with open floor of finance professionals at workstations, team lead standing reviewing workflow with one colleague, professional and efficient",
    "implantação":        "Finance project lead and IT manager at conference table reviewing implementation timeline on laptop, organized planning documents visible, collaborative professional setting",
    "transformação":      "Finance leadership team in modern boardroom reviewing digital transformation roadmap on projected screen, engaged strategic discussion, forward-looking atmosphere",

    # ── Legado (manter compatibilidade) ─────────────────────────────────────────
    "pagamento":          "Finance professional at standing desk reviewing payment approvals on laptop, calm and confident, modern corporate floor",
    "conciliação":        "Financial analyst at desk comparing data on screen, engaged and at ease, natural pleasant expression, finance department modern office",
    "gestão financeira":  "Finance director at clean corporate desk using financial management platform on laptop, composed and confident, São Paulo corporate office",
    "software financeiro":"Finance team in training session, presenter at large screen, professionals attentive and engaged, natural professional setting",
    "centralização":      "Finance operations manager overseeing centralized dashboard on large monitor, composed and assured, modern finance operations floor",
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:60]


# Visual concepts específicos para cada artigo do batch4
# Rotação planejada: A=solo, B=dupla, C=reunião 3-4, D=executivo de pé, E=documentos, F=apresentação, G=movimento
BATCH4_VISUALS = {
    "Como Eliminar Retrabalho no Contas a Pagar com Automação de Comprovantes e Conciliação":
        "Brazilian woman with curly natural hair working at desk with MacBook showing payment approval workflow with multiple transactions on screen, coffee mug nearby, printed documents beside laptop, colleagues naturally at their desks blurred in background, warm open-plan São Paulo office",  # A-solo
    "Gestão de Múltiplos Portais Bancários no Contas a Pagar: Como Centralizar e Ganhar Controle":
        "Two Brazilian finance professionals side-by-side at wide desk, one pointing at monitor showing unified banking dashboard with multiple institution tabs consolidated, natural engaged conversation, colleagues visible in open office background",  # B-dupla
    "Como Definir Políticas de Aprovação de Pagamentos por Valor, Tipo e Perfil de Usuário":
        "Woman standing presenting approval policy rules on wall screen to two seated colleagues with laptops and notebooks, meeting room with São Paulo skyline through window, engaged natural discussion energy",  # F-apresentação
    "Como Antecipar Descasamentos de Caixa com Cinco Dias de Antecedência na Tesouraria":
        "Brazilian male treasurer at dual monitors showing 5-day cash flow projection chart with timeline and gap indicators, leaning forward analyzing data with focused expression, financial charts clearly visible, open office colleagues at desks in background",  # A-solo
    "Reconciliação de Posição de Caixa em Tempo Real: Por Que o Fechamento do Dia Já Não Basta":
        "Finance analyst at dual side-by-side monitors showing real-time bank reconciliation with live data streams and balance charts, organized desk with documents and coffee, end-of-day focused expression, colleagues visible in background",  # A-solo
    "Como Reduzir a Dependência de Processos Manuais na Tesouraria sem Parar a Operação":
        "Two finance professionals at desk discussing — one showing laptop screen with automated workflow comparison chart replacing manual steps, natural consultative conversation, modern corporate office, documents and coffee on table",  # B-dupla
    "Gestão de Caixa em Grupos Empresariais: Como Eliminar Saldos Ociosos entre CNPJs":
        "Three treasury professionals around conference table with laptops showing group consolidated cash position by entity with idle balance indicators, one pointing at screen explaining the chart, São Paulo cityscape through window",  # C-reunião
    "Como a Visão Multibanco Transforma o Processo de Fechamento Diário da Tesouraria":
        "CFO at workstation with wide monitor showing unified multibanco dashboard with multiple bank institution data consolidated into one view, confident morning review expression, coffee mug, open office with colleagues in background",  # A-solo
    "Como Negociar Prazo com Fornecedores Usando Supply Chain Finance sem Comprometer o Caixa":
        "Finance and procurement professionals sitting across small meeting table reviewing supply chain finance proposal on laptop, documents spread between them, notebooks open, natural negotiation energy, São Paulo meeting room",  # B-dupla
    "Risco de Concentração em Recebíveis: Como Identificar e Diversificar a Carteira da sua Empresa":
        "Risk analyst at monitor showing receivables portfolio concentration donut chart with client percentage breakdowns highlighted in red, professional focused review expression, organized desk with documents, colleagues in open office behind",  # A-solo
    "Antecipação de Recebíveis vs Desconto de Duplicatas: Qual Protege Mais o Fluxo de Caixa":
        "Three finance professionals around table with laptops open, one screen showing side-by-side comparison chart of two financial instruments with cash flow impact, engaged analytical discussion with notebooks, São Paulo conference room",  # C-reunião
    "Como Avaliar a Saúde Financeira de Fornecedores Antes de Aprovar Crédito na Cadeia":
        "Two Brazilian finance professionals across small table reviewing supplier risk dashboard on laptop showing financial health indicators and credit scores, collaborative evaluation posture, meeting room with documents between them",  # B-dupla
    "Como Transformar Relatórios Financeiros em Decisões Estratégicas com Dados em Tempo Real":
        "Brazilian woman finance director with natural hair at wide monitor showing real-time financial dashboard with multiple KPI panels and trend charts, confident analytical expression, reviewing with purpose, open office colleagues working in background",  # A-solo
    "Custo de Capital vs Custo Operacional: Como o Analytics Financeiro Revela o Resultado Real":
        "CFO standing presenting cost analysis waterfall chart on projected screen to seated finance team of three around table with laptops, São Paulo skyline through window, engaged team discussion with notebooks",  # F-apresentação
    "Como Medir a Performance da Tesouraria com KPIs que Vão Além do Saldo em Conta":
        "Treasury manager at dual monitors with KPI performance dashboard showing treasury metrics — cash conversion cycle, liquidity ratios, bank fee trends, leaning back with satisfied review expression, colleagues visible in open office",  # A-solo
    "Previsão de Inadimplência com Analytics: Como Agir Antes que o Problema Chegue ao Caixa":
        "Finance risk executive standing at desk leaning on surface reviewing predictive analytics chart on large monitor showing default probability forecast with trend line, city skyline through window behind, professional commanding posture",  # D-executivo de pé
    "Como Migrar de EDI para API sem Interromper a Operação Bancária da sua Empresa":
        "IT architect and finance professional side-by-side at workstation reviewing migration timeline Gantt chart on monitor comparing EDI vs API integration status, natural technical discussion, tech-finance collaborative office",  # B-dupla
    "Open Finance B2B: O que Muda na Prática para Empresas com Múltiplos Relacionamentos Bancários":
        "Forward-thinking finance executive at laptop reviewing Open Finance connected institutions interface showing multiple bank relationships data, modern São Paulo office, natural light, forward-looking expression",  # A-solo
    "CNAB na Prática: Como Montar o Arquivo Correto para Cada Instituição e Evitar Rejeições":
        "Operations specialist at desktop computer reviewing CNAB file structure with bank-specific field specifications on screen, organized methodical expression, neat back-office desk with printed documentation, focused systematic work",  # A-solo
    "Como Escolher a VAN Bancária Adequada para o Volume e Complexidade da sua Operação":
        "Three finance and IT professionals around meeting table reviewing VAN banking provider comparison matrix on laptop screen, documents spread on table, technical evaluative discussion, modern conference room São Paulo",  # C-reunião
    "Integração entre ERP e Instituições Financeiras: Quando a API Supera o Arquivo CNAB":
        "Finance and technology professional at adjacent desks reviewing API integration performance dashboard on screens showing transaction speed comparison vs CNAB, natural side-by-side collaboration, tech office",  # B-dupla
    "Como Garantir Segurança na Troca de Arquivos Financeiros: O Papel da VAN Certificada":
        "IT security professional at dual monitors showing encrypted file transfer security dashboard with certification status indicators, focused professional expression, organized secure operations office, colleagues in background",  # A-solo
    "Cash Pooling em Grupos com Empresas em Múltiplos Estados: Como Estruturar sem Passivo Fiscal":
        "Group treasury team of four around boardroom table with laptops showing multi-entity cash pooling structure diagram by state, notebooks open, organized strategic planning discussion, executive boardroom",  # C-reunião
    "Como Calcular o Retorno Financeiro de um Programa de Cash Pooling Antes de Implantar":
        "CFO standing at executive desk leaning over reviewing cash pooling ROI projection on large monitor showing before/after scenario comparison, confident evaluative posture, São Paulo city view through window",  # D-executivo de pé
    "Cash Pooling e Relacionamento com Instituições: Como Concentrar Saldo sem Perder Condições":
        "Treasury director and colleague side-by-side reviewing consolidated institutional balance comparison spreadsheet on laptop, discussion about negotiated conditions visible in documents between them, professional collaborative meeting room",  # B-dupla
    "Da Operação ao Estratégico: Como a Plataforma Financeira Libera o CFO do Operacional Diário":
        "Brazilian CFO standing at floor-to-ceiling window overlooking São Paulo city, hands clasped behind back, strategic and composed leadership posture, financial platform screen visible on desk behind them, natural contemplative leadership moment",  # D-executivo de pé
    "Como Estruturar um Centro de Serviços Financeiros com Tecnologia de Integração Bancária":
        "Finance shared services team of four in bright meeting room, team lead at whiteboard with CSC workflow diagram, three colleagues with laptops engaged in discussion, organized planning session, São Paulo conference room",  # C-reunião
    "Por que Grandes Empresas Estão Unificando Tesouraria e Contas a Pagar em Uma Única Plataforma":
        "Two senior finance executives at conference table reviewing unified platform dashboard on laptop showing treasury and AP modules integrated in single view, one explaining to the other, professional strategic conversation",  # B-dupla
    "Como Implantar uma Plataforma de Gestão Financeira sem Parar o Financeiro durante a Transição":
        "Finance project lead walking purposefully through modern open-plan office carrying tablet showing implementation roadmap, colleagues at their desks naturally in background, purposeful professional in-motion captured",  # G-movimento
    "Governança Financeira Corporativa: Como Tecnologia e Processos Reduzem Riscos Operacionais":
        "Three board-level finance executives reviewing governance compliance framework printed reports at long conference table with laptops, professional authoritative discussion, executive boardroom São Paulo",  # C-reunião
}


def generate_scene_for_title(title: str, excerpt: str, api_key: str) -> str:
    """Usa LLM de texto para gerar descrição de cena fotográfica específica ao tema do artigo."""
    context = f'TÍTULO: "{title}"\nRESUMO: {excerpt[:300]}' if excerpt else f'TÍTULO: "{title}"'
    prompt = f"""Você é um diretor de fotografia criando o briefing de uma foto editorial para o blog da Accesstage (fintech B2B, produto Veragi, público: CFOs e tesoureiros de grandes empresas brasileiras).

{context}

Gere UMA descrição de cena fotográfica em inglês, curta (2-3 frases), que:
1. Mostre o profissional executando a ação ESPECÍFICA descrita no artigo (ex: se é sobre antecipação de recebíveis, mostre alguém revisando uma tela com gráfico de recebíveis antecipados e fluxo de caixa)
2. Inclua um elemento visual concreto do tema — o que APARECE na tela ou nos documentos deve refletir o conteúdo real do artigo
3. A cena deve ser diferente de outros artigos — use a especificidade do título para criar algo único
4. 1-3 pessoas máximo. A pessoa principal em ângulo 3/4, engajada, não posando para a câmera

Responda APENAS com a descrição da cena em inglês. Sem explicações. Sem aspas."""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://sowads.com.br",
        "X-Title": "Sowads Orbit Image Generator",
    }
    try:
        r = requests.post(OPENROUTER_URL, headers=headers, json={
            "model": "google/gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 180,
        }, timeout=20)
        r.raise_for_status()
        scene = r.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")
        return scene
    except Exception:
        title_lower = title.lower()
        return next(
            (v for k, v in TOPIC_VISUALS.items() if k in title_lower),
            "Brazilian finance professional at desk actively working on financial platform, engaged natural expression, modern corporate office São Paulo"
        )


def build_prompt(title: str, excerpt: str = "", api_key: str = "") -> str:
    # Gera cena específica via LLM usando título + excerpt do artigo
    if api_key:
        visual_concept = generate_scene_for_title(title, excerpt, api_key)
        print(f"    → cena gerada: {visual_concept[:80]}...")
    else:
        # Fallback sem API: BATCH4_VISUALS → TOPIC_VISUALS → genérico
        if title in BATCH4_VISUALS:
            visual_concept = BATCH4_VISUALS[title]
        else:
            title_lower = title.lower()
            visual_concept = next(
                (v for k, v in TOPIC_VISUALS.items() if k in title_lower),
                "Brazilian finance professional at desk reviewing financial platform, engaged natural expression, colleagues in open office background"
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
    # GPT image models suportam size via parâmetro direto — força landscape 16:9
    if "gpt" in model.lower() or "openai" in model.lower():
        payload["size"] = "1792x1024"
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

        excerpt = row.get("excerpt", "") or row.get("meta_description", "") or ""
        prompt = build_prompt(title, excerpt=excerpt, api_key=api_key)
        print(f"  [{idx:02d}] ⏳ {title[:55]}...")
        t0 = time.time()

        img_bytes = call_image_api(prompt, api_key, args.model)

        if img_bytes:
            # Se a imagem for quadrada, corta para 16:9 mantendo pessoas bem enquadradas
            img = Image.open(io.BytesIO(img_bytes))
            w, h = img.size
            if w == h:
                target_h = int(w * 9 / 16)  # ex: 1024 → 576px de altura
                # Crop levemente acima do centro: preserva cabeças sem cortar base da composição
                # 1/4 do excedente fica no topo (menos headroom perdido), 3/4 na base
                excess = h - target_h
                top = excess // 4
                img = img.crop((0, top, w, top + target_h))
                img = img.resize((1280, 720), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                img_bytes = buf.getvalue()
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
