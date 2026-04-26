#!/usr/bin/env python3
"""
monitor.py — Monitor de progresso do pipeline Orbit AI
Uso: python3 tools/monitor.py
     python3 tools/monitor.py --log output/reports/run_pipeline.log --total 10
"""
import os, re, sys, time, argparse
from datetime import datetime, timedelta
from collections import deque

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH  = os.path.join(_BASE_DIR, "output", "reports", "run_pipeline.log")

REFRESH = 2  # segundos entre atualizações

# Padrões de parse — genéricos, sem dependência de nome de lote
RE_GERANDO  = re.compile(r'\[(\d+)/(\d+)\] Gerando:(.+)')
RE_SCORE    = re.compile(r'-> .*(Score: (\d+)/100)')
RE_LOTE     = re.compile(r'▶ LOTE ([A-Z0-9_\-]+)', re.IGNORECASE)
RE_MEDIA    = re.compile(r'\[MEDIA\].*(\d+) grupos')
RE_BATCH    = re.compile(r'Batch \d+ salvo em (.+)')
RE_PUB      = re.compile(r'(▶ PUBLICANDO|PUBLICANDO RASCUNHOS)', re.IGNORECASE)
RE_DONE     = re.compile(r'(GERAÇÃO COMPLETA|PIPELINE COMPLETO|TODOS OS BATCHES COMPLETOS)', re.IGNORECASE)
RE_HEALING  = re.compile(r'\[HEAL\]')
RE_BRIEFING = re.compile(r'\[BRIEFING\]')
RE_IMG      = re.compile(r'\[IMG\] (Match encontrado|Sem imagem)')
RE_INICIO   = re.compile(r'PIPELINE INICIADO: (.+)')
RE_TOTAL    = re.compile(r'Carregados (\d+) temas de')

CLEAR  = "\033[2J\033[H"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def bar(done, total, width=36):
    pct  = done / total if total else 0
    fill = int(pct * width)
    b    = "█" * fill + "░" * (width - fill)
    return f"{b} {done}/{total} ({pct*100:.0f}%)"

def eta_str(seconds):
    if seconds <= 0:
        return "—"
    return str(timedelta(seconds=int(seconds))).lstrip("0:").zfill(5)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log",   default=LOG_PATH, help="Caminho do log")
    parser.add_argument("--total", type=int, default=0, help="Total de artigos esperado (auto-detectado se 0)")
    args = parser.parse_args()

    if not os.path.exists(args.log):
        print(f"  Aguardando log em: {args.log}")
        print(f"  Inicie o pipeline em outro terminal e aguarde...")
        while not os.path.exists(args.log):
            time.sleep(1)

    state = {
        "fase":           "aguardando",
        "lote_atual":     "—",
        "art_atual":      "",
        "art_done":       0,
        "art_total":      args.total,   # 0 = auto-detectar pelo log
        "scores":         [],
        "heals":          0,
        "briefings":      0,
        "img_match":      0,
        "img_miss":       0,
        "batches_done":   [],
        "lotes_vistos":   [],
        "inicio":         None,
        "tempos":         deque(maxlen=10),
        "ultimo_inicio":  None,
        "pipeline_done":  False,
    }

    pos = 0

    while True:
        with open(args.log, "r", encoding="utf-8", errors="replace") as f:
            f.seek(pos)
            novas = f.readlines()
            pos   = f.tell()

        agora = datetime.now()

        for linha in novas:
            l = linha.strip()

            if RE_INICIO.search(l) and not state["inicio"]:
                state["inicio"] = agora
                state["fase"]   = "iniciando"

            # Auto-detecta total de artigos pelo log
            m = RE_TOTAL.search(l)
            if m and state["art_total"] == 0:
                state["art_total"] = int(m.group(1))

            # Detecta nome do lote genericamente
            m = RE_LOTE.search(l)
            if m:
                nome = m.group(1).capitalize()
                if nome not in state["lotes_vistos"]:
                    state["lotes_vistos"].append(nome)
                state["lote_atual"] = nome
                state["fase"]       = "gerando"

            if RE_PUB.search(l):
                state["fase"]       = "publicando"
                state["lote_atual"] = "WordPress 📤"

            m = RE_GERANDO.search(l)
            if m:
                n, total, tema = m.groups()
                state["art_atual"]    = tema.strip()[:60]
                state["ultimo_inicio"] = agora
                # Atualiza total se vier do log e não foi configurado
                if state["art_total"] == 0:
                    state["art_total"] = int(total)

            m = RE_SCORE.search(l)
            if m:
                score = int(m.group(2))
                state["scores"].append(score)
                state["art_done"] += 1
                if state["ultimo_inicio"]:
                    dt = (agora - state["ultimo_inicio"]).total_seconds()
                    state["tempos"].append(dt)
                    state["ultimo_inicio"] = None

            if RE_HEALING.search(l):
                state["heals"] += 1

            if RE_BRIEFING.search(l):
                state["briefings"] += 1

            m = RE_IMG.search(l)
            if m:
                if "Match" in m.group(1):
                    state["img_match"] += 1
                else:
                    state["img_miss"]  += 1

            m = RE_BATCH.search(l)
            if m:
                nome_csv = m.group(1).split("/")[-1]
                if nome_csv not in state["batches_done"]:
                    state["batches_done"].append(nome_csv)

            if RE_DONE.search(l):
                state["pipeline_done"] = True
                state["fase"]          = "concluído ✅"

        # ── Calcula métricas ────────────────────────────────────────
        done      = state["art_done"]
        total     = state["art_total"] if state["art_total"] > 0 else max(done, 1)
        remaining = max(total - done, 0)
        avg_tempo = (sum(state["tempos"]) / len(state["tempos"])) if state["tempos"] else 0
        eta_s     = avg_tempo * remaining
        elapsed   = (agora - state["inicio"]).total_seconds() if state["inicio"] else 0

        scores    = state["scores"]
        avg_score = sum(scores) / len(scores) if scores else 0
        min_score = min(scores) if scores else 0
        max_score = max(scores) if scores else 0
        score_color = GREEN if avg_score >= 85 else YELLOW if avg_score >= 75 else RED

        # ── Render ──────────────────────────────────────────────────
        sys.stdout.write(CLEAR)
        sys.stdout.write(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════════╗{RESET}\n")
        sys.stdout.write(f"{BOLD}{CYAN}║     ORBIT AI — MONITOR DE PIPELINE  (Accesstage)    ║{RESET}\n")
        sys.stdout.write(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════╝{RESET}\n\n")

        sys.stdout.write(f"  {BOLD}Fase:{RESET}      {state['fase'].upper()}\n")
        lotes_str = " → ".join(state["lotes_vistos"]) if state["lotes_vistos"] else "—"
        sys.stdout.write(f"  {BOLD}Lotes:{RESET}     {lotes_str}\n")
        sys.stdout.write(f"  {BOLD}Início:{RESET}    {state['inicio'].strftime('%H:%M:%S') if state['inicio'] else '—'}")
        sys.stdout.write(f"   |   Decorrido: {BOLD}{eta_str(elapsed)}{RESET}\n\n")

        sys.stdout.write(f"  {BOLD}Progresso geral{RESET}\n")
        sys.stdout.write(f"  {bar(done, total)}\n\n")

        # Tempo decorrido no artigo atual (mostra enquanto a API não responde)
        api_wait = ""
        if state["ultimo_inicio"]:
            t_atual = (agora - state["ultimo_inicio"]).total_seconds()
            api_wait = f"  {YELLOW}⏳ aguardando API há {t_atual:.0f}s{RESET}"

        sys.stdout.write(f"  {BOLD}Artigo atual:{RESET} {DIM}{state['art_atual']}{RESET}\n")
        sys.stdout.write(f"  {BOLD}ETA:{RESET}          {YELLOW}{eta_str(eta_s)}{RESET}")
        if avg_tempo:
            sys.stdout.write(f"   {DIM}(~{avg_tempo:.0f}s por artigo){RESET}")
        sys.stdout.write(f"{api_wait}\n\n")

        sys.stdout.write(f"  {'─' * 54}\n")
        sys.stdout.write(f"  {BOLD}Score QA médio:{RESET}  {score_color}{BOLD}{avg_score:.0f}/100{RESET}")
        if scores:
            sys.stdout.write(f"   {DIM}min {min_score} · max {max_score} · {len(scores)} artigos{RESET}")
        sys.stdout.write("\n")
        sys.stdout.write(f"  {BOLD}Self-healing:{RESET}    {state['heals']} correção(ões)\n")
        sys.stdout.write(f"  {BOLD}Briefings:{RESET}       {state['briefings']} injetados\n")
        imagens_str = f"{GREEN}{state['img_match']} matched{RESET}"
        if state["img_miss"]:
            imagens_str += f"   {YELLOW}{state['img_miss']} sem match{RESET}"
        sys.stdout.write(f"  {BOLD}Imagens:{RESET}         {imagens_str}\n")

        if state["batches_done"]:
            sys.stdout.write(f"\n  {BOLD}CSVs gerados:{RESET}\n")
            for b in state["batches_done"]:
                sys.stdout.write(f"    ✅ {b}\n")

        if state["pipeline_done"]:
            sys.stdout.write(f"\n  {GREEN}{BOLD}🎉 GERAÇÃO COMPLETA! Artigos salvos em output/articles/{RESET}\n")
            sys.stdout.write(f"  {DIM}Próximo passo: python3 engine/publisher.py --test_one{RESET}\n")
            sys.stdout.write(f"  {DIM}Pressione Ctrl+C para sair.{RESET}\n")
        else:
            sys.stdout.write(f"\n  {DIM}Atualiza a cada {REFRESH}s — Ctrl+C para sair{RESET}\n")

        sys.stdout.flush()
        time.sleep(REFRESH)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RESET}Monitor encerrado.")
