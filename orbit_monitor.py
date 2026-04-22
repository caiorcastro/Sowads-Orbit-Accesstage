#!/usr/bin/env python3
"""
orbit_monitor.py — Monitor de progresso do pipeline Orbit AI
Uso: python3 orbit_monitor.py
     python3 orbit_monitor.py --log relatorios/run_pipeline.log
"""
import os, re, sys, time, argparse
from datetime import datetime, timedelta
from collections import deque

LOG_PATH    = "relatorios/run_pipeline.log"
TOTAL_AUTO  = 20
TOTAL_TUR   = 20
TOTAL_ALL   = TOTAL_AUTO + TOTAL_TUR
REFRESH     = 2  # segundos entre atualizações

# Padrões de parse
RE_GERANDO  = re.compile(r'\[(\d+)/(\d+)\] Gerando:(.+)')
RE_SCORE    = re.compile(r'-> .*(Score: (\d+)/100)')
RE_LOTE     = re.compile(r'(▶ LOTE (AUTO|TURISMO)|LOTE AUTO|LOTE TURISMO)', re.IGNORECASE)
RE_MEDIA    = re.compile(r'\[MEDIA\].*(\d+) grupos')
RE_BATCH    = re.compile(r'Batch \d+ salvo em (.+)')
RE_PUB      = re.compile(r'(▶ PUBLICANDO|PUBLICANDO RASCUNHOS)', re.IGNORECASE)
RE_DONE     = re.compile(r'PIPELINE COMPLETO')
RE_HEALING  = re.compile(r'\[HEAL\]')
RE_BRIEFING = re.compile(r'\[BRIEFING\]')
RE_IMG      = re.compile(r'\[IMG\] (Match encontrado|Sem imagem)')
RE_INICIO   = re.compile(r'PIPELINE INICIADO: (.+)')

CLEAR  = "\033[2J\033[H"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def bar(done, total, width=30):
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
    parser.add_argument("--log", default=LOG_PATH)
    args = parser.parse_args()

    if not os.path.exists(args.log):
        print(f"Aguardando log em {args.log} ...")
        while not os.path.exists(args.log):
            time.sleep(1)

    state = {
        "fase":          "aguardando",
        "lote_atual":    "—",
        "art_atual":     "",
        "art_done":      0,
        "art_total":     TOTAL_ALL,
        "scores":        [],
        "heals":         0,
        "briefings":     0,
        "img_match":     0,
        "img_miss":      0,
        "batches_done":  [],
        "inicio":        None,
        "tempos":        deque(maxlen=10),   # últimos N tempos por artigo
        "ultimo_inicio": None,
        "pipeline_done": False,
    }

    pos = 0  # posição no log

    while True:
        with open(args.log, "r", encoding="utf-8", errors="replace") as f:
            f.seek(pos)
            novas = f.readlines()
            pos   = f.tell()

        agora = datetime.now()

        for linha in novas:
            l = linha.strip()

            m = RE_INICIO.search(l)
            if m and not state["inicio"]:
                state["inicio"] = agora

            if RE_LOTE.search(l):
                if "AUTO" in l.upper():
                    state["lote_atual"] = "AUTO 🚗"
                    state["fase"]       = "gerando"
                elif "TURISMO" in l.upper():
                    state["lote_atual"] = "TURISMO ✈️"
                    state["fase"]       = "gerando"

            if RE_PUB.search(l):
                state["fase"]       = "publicando"
                state["lote_atual"] = "WordPress 📤"

            m = RE_GERANDO.search(l)
            if m:
                n, total, tema = m.groups()
                state["art_atual"]   = tema.strip()[:55]
                state["ultimo_inicio"] = agora

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
                state["batches_done"].append(m.group(1).split("/")[-1])

            if RE_DONE.search(l):
                state["pipeline_done"] = True
                state["fase"]          = "concluído"

        # ── Calcula ETA ──────────────────────────────
        done       = state["art_done"]
        remaining  = state["art_total"] - done
        avg_tempo  = (sum(state["tempos"]) / len(state["tempos"])) if state["tempos"] else 0
        eta_s      = avg_tempo * remaining
        elapsed    = (agora - state["inicio"]).total_seconds() if state["inicio"] else 0

        scores = state["scores"]
        avg_score = sum(scores) / len(scores) if scores else 0
        score_color = GREEN if avg_score >= 85 else YELLOW if avg_score >= 75 else RED

        # ── Render ───────────────────────────────────
        sys.stdout.write(CLEAR)
        sys.stdout.write(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{RESET}\n")
        sys.stdout.write(f"{BOLD}{CYAN}║       ORBIT AI — MONITOR DE PIPELINE             ║{RESET}\n")
        sys.stdout.write(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{RESET}\n\n")

        sys.stdout.write(f"  {BOLD}Fase:{RESET}     {state['fase'].upper()}   |   Lote: {BOLD}{state['lote_atual']}{RESET}\n")
        sys.stdout.write(f"  {BOLD}Início:{RESET}   {state['inicio'].strftime('%H:%M:%S') if state['inicio'] else '—'}")
        sys.stdout.write(f"   |   Decorrido: {BOLD}{eta_str(elapsed)}{RESET}\n\n")

        sys.stdout.write(f"  {BOLD}Progresso geral{RESET}\n")
        sys.stdout.write(f"  {bar(done, state['art_total'])}\n\n")

        sys.stdout.write(f"  {BOLD}Artigo atual:{RESET} {DIM}{state['art_atual']}{RESET}\n")
        sys.stdout.write(f"  {BOLD}ETA:{RESET}          {YELLOW}{eta_str(eta_s)}{RESET}")
        if avg_tempo:
            sys.stdout.write(f"  {DIM}(~{avg_tempo:.0f}s/artigo){RESET}")
        sys.stdout.write("\n\n")

        sys.stdout.write(f"  ─────────────────────────────────────\n")
        sys.stdout.write(f"  {BOLD}Score médio QA:{RESET}  {score_color}{avg_score:.0f}/100{RESET}")
        sys.stdout.write(f"   ({len(scores)} artigos)\n")
        sys.stdout.write(f"  {BOLD}Self-healing:{RESET}    {state['heals']} correções\n")
        sys.stdout.write(f"  {BOLD}Briefings:{RESET}       {state['briefings']} injetados\n")
        sys.stdout.write(f"  {BOLD}Imagens:{RESET}         {GREEN}{state['img_match']} matched{RESET}")
        if state["img_miss"]:
            sys.stdout.write(f"  {YELLOW}{state['img_miss']} sem match{RESET}")
        sys.stdout.write("\n")

        if state["batches_done"]:
            sys.stdout.write(f"\n  {BOLD}CSVs gerados:{RESET}\n")
            for b in state["batches_done"]:
                sys.stdout.write(f"    ✅ {b}\n")

        if state["pipeline_done"]:
            sys.stdout.write(f"\n  {GREEN}{BOLD}🎉 PIPELINE COMPLETO! Todos os artigos publicados como rascunho.{RESET}\n")
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
