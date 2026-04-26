#!/usr/bin/env python3
"""
monitor.py — Monitor de progresso do pipeline Orbit AI (paralelo)
Uso: python3 tools/monitor.py
     python3 tools/monitor.py --log output/reports/run_pipeline.log --total 10
"""
import os, re, sys, time, argparse
from datetime import datetime, timedelta
from collections import deque

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH  = os.path.join(_BASE_DIR, "output", "reports", "run_pipeline.log")
REFRESH   = 2

# ── Padrões de parse ─────────────────────────────────────────────────────────
RE_INICIO   = re.compile(r'PIPELINE INICIADO: (.+)')
RE_LOTE     = re.compile(r'▶ LOTE ([A-Z0-9_\-]+)', re.IGNORECASE)
RE_WORKERS  = re.compile(r'workers=(\d+)')
RE_TOTAL    = re.compile(r'Carregados (\d+) temas de')
RE_ARTIGO   = re.compile(r'^\[(\d+)/(\d+)\] ([^\[].{5,})')   # [01/10] Título sem prefixo extra
RE_BRIEFING = re.compile(r'briefing \(')                       # CTX com briefing
RE_HEAL     = re.compile(r'\[HEAL\] (tentativa|\d+x)')         # self-heal aplicado
RE_SCORE    = re.compile(r'\[(\d+)/\d+\] ✓ Score:(\d+)/100.* (\d+)s')   # concluído
RE_ERRO     = re.compile(r'\[(\d+)/\d+\] ✗ ERRO')
RE_BATCH    = re.compile(r'Batch \d+ salvo em (.+)')
RE_PUB      = re.compile(r'(▶ PUBLICANDO|PUBLICANDO RASCUNHOS)', re.IGNORECASE)
RE_DONE     = re.compile(r'(GERAÇÃO COMPLETA|PIPELINE COMPLETO|TODOS OS BATCHES COMPLETOS)', re.IGNORECASE)

# ── Cores ────────────────────────────────────────────────────────────────────
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
    return f"{'█' * fill}{'░' * (width - fill)} {done}/{total} ({pct*100:.0f}%)"

def eta_str(seconds):
    if seconds <= 0:
        return "—"
    return str(timedelta(seconds=int(seconds))).lstrip("0:").zfill(5)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log",   default=LOG_PATH)
    parser.add_argument("--total", type=int, default=0)
    args = parser.parse_args()

    if not os.path.exists(args.log):
        print(f"  Aguardando log em: {args.log}")
        print(f"  Inicie o pipeline em outro terminal e aguarde...")
        while not os.path.exists(args.log):
            time.sleep(1)

    state = {
        "fase":          "aguardando",
        "lotes_vistos":  [],
        "workers":       1,
        "art_total":     args.total,
        "art_done":      0,
        "art_erros":     0,
        "in_flight":     {},           # idx → tema (artigos na API agora)
        "api_tempos":    deque(maxlen=20),
        "scores":        [],
        "heals":         0,
        "briefings":     0,
        "batches_done":  [],
        "inicio":        None,
        "pipeline_done": False,
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

            m = RE_WORKERS.search(l)
            if m:
                state["workers"] = int(m.group(1))

            m = RE_TOTAL.search(l)
            if m and state["art_total"] == 0:
                state["art_total"] = int(m.group(1))

            m = RE_LOTE.search(l)
            if m:
                nome = m.group(1).capitalize()
                if nome not in state["lotes_vistos"]:
                    state["lotes_vistos"].append(nome)
                state["fase"] = "gerando"

            if RE_PUB.search(l):
                state["fase"] = "publicando"

            # Artigo inicia: [01/10] Título (linha sem outro prefixo entre colchetes)
            m = RE_ARTIGO.search(l)
            if m:
                idx, total, tema = m.group(1), m.group(2), m.group(3).strip()[:55]
                state["in_flight"][idx] = tema
                if state["art_total"] == 0:
                    state["art_total"] = int(total)

            if RE_BRIEFING.search(l):
                state["briefings"] += 1

            if RE_HEAL.search(l):
                state["heals"] += 1

            # Artigo concluído: [01/10] ✓ Score:100/100 | ... | 87s
            m = RE_SCORE.search(l)
            if m:
                idx, score, secs = m.group(1), int(m.group(2)), int(m.group(3))
                state["scores"].append(score)
                state["art_done"] += 1
                state["api_tempos"].append(secs)
                state["in_flight"].pop(idx, None)

            m = RE_ERRO.search(l)
            if m:
                state["in_flight"].pop(m.group(1), None)
                state["art_erros"] += 1
                state["art_done"]  += 1

            m = RE_BATCH.search(l)
            if m:
                nome_csv = m.group(1).split("/")[-1]
                if nome_csv not in state["batches_done"]:
                    state["batches_done"].append(nome_csv)

            if RE_DONE.search(l):
                state["pipeline_done"] = True
                state["fase"]          = "concluído ✅"

        # ── Métricas ─────────────────────────────────────────────────────────
        done      = state["art_done"]
        total     = state["art_total"] if state["art_total"] > 0 else max(done, 1)
        in_flight = len(state["in_flight"])
        remaining = max(total - done - in_flight, 0)
        workers   = max(state["workers"], 1)
        avg_tempo = sum(state["api_tempos"]) / len(state["api_tempos"]) if state["api_tempos"] else 0
        eta_s     = (remaining / workers) * avg_tempo if avg_tempo else 0
        elapsed   = (agora - state["inicio"]).total_seconds() if state["inicio"] else 0

        scores      = state["scores"]
        avg_score   = sum(scores) / len(scores) if scores else 0
        min_score   = min(scores) if scores else 0
        max_score   = max(scores) if scores else 0
        score_color = GREEN if avg_score >= 85 else YELLOW if avg_score >= 75 else RED

        # ── Render ───────────────────────────────────────────────────────────
        sys.stdout.write(CLEAR)
        sys.stdout.write(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════════╗{RESET}\n")
        sys.stdout.write(f"{BOLD}{CYAN}║     ORBIT AI — MONITOR DE PIPELINE  (Accesstage)    ║{RESET}\n")
        sys.stdout.write(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════╝{RESET}\n\n")

        lotes_str = " → ".join(state["lotes_vistos"]) or "—"
        sys.stdout.write(f"  {BOLD}Fase:{RESET}    {state['fase'].upper()}   |   Lote: {lotes_str}   |   Workers: {workers}\n")
        sys.stdout.write(f"  {BOLD}Início:{RESET}  {state['inicio'].strftime('%H:%M:%S') if state['inicio'] else '—'}")
        sys.stdout.write(f"   |   Decorrido: {BOLD}{eta_str(elapsed)}{RESET}\n\n")

        sys.stdout.write(f"  {BOLD}Progresso  {done}/{total} concluídos  +{in_flight} na API agora{RESET}\n")
        sys.stdout.write(f"  {bar(done, total)}\n\n")

        if state["in_flight"]:
            sys.stdout.write(f"  {BOLD}Na API agora:{RESET}\n")
            for idx, tema in sorted(state["in_flight"].items()):
                sys.stdout.write(f"    {YELLOW}⏳ [{idx}] {tema}{RESET}\n")
            sys.stdout.write("\n")

        sys.stdout.write(f"  {BOLD}ETA:{RESET}     {YELLOW}{eta_str(eta_s)}{RESET}")
        if avg_tempo:
            sys.stdout.write(f"   {DIM}(~{avg_tempo:.0f}s/artigo · ~{avg_tempo/workers:.0f}s/rodada com {workers} workers){RESET}")
        sys.stdout.write("\n\n")

        sys.stdout.write(f"  {'─'*54}\n")
        sys.stdout.write(f"  {BOLD}Score QA:{RESET}     {score_color}{BOLD}{avg_score:.0f}/100{RESET}")
        if scores:
            sys.stdout.write(f"   {DIM}min {min_score} · max {max_score} · {len(scores)} prontos{RESET}")
        sys.stdout.write("\n")
        sys.stdout.write(f"  {BOLD}Self-healing:{RESET} {state['heals']} correção(ões)\n")
        sys.stdout.write(f"  {BOLD}Briefings:{RESET}    {state['briefings']} injetados\n")
        if state["art_erros"]:
            sys.stdout.write(f"  {BOLD}Erros:{RESET}        {RED}{state['art_erros']}{RESET}\n")

        if state["batches_done"]:
            sys.stdout.write(f"\n  {BOLD}CSV gerado:{RESET}\n")
            for b in state["batches_done"]:
                sys.stdout.write(f"    ✅ {b}\n")

        if state["pipeline_done"]:
            sys.stdout.write(f"\n  {GREEN}{BOLD}🎉 GERAÇÃO COMPLETA! Artigos em output/articles/{RESET}\n")
            sys.stdout.write(f"  {DIM}Próximo: python3 engine/publisher.py --test_one{RESET}\n")
            sys.stdout.write(f"  {DIM}Ctrl+C para sair.{RESET}\n")
        else:
            sys.stdout.write(f"\n  {DIM}Atualiza a cada {REFRESH}s — Ctrl+C para sair{RESET}\n")

        sys.stdout.flush()
        time.sleep(REFRESH)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RESET}Monitor encerrado.")
