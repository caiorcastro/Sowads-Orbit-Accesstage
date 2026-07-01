#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
monitor_lote.py — Painel CLI colorido de progresso de geração de artigos.
Lê o log do content_engine e mostra barra de progresso, ETA e custo, atualizando sozinho.

Uso:
  python3 tools/monitor_lote.py                         # log/total padrão (lote2), refresh 20s
  python3 tools/monitor_lote.py --log output/reports/gen_lote2.log --total 28 --interval 20
  python3 tools/monitor_lote.py --once                  # 1 render (sem loop)
"""
import os, re, sys, time, argparse, glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── cores ANSI ────────────────────────────────────────────────────────────────
class C:
    R="\033[0m"; B="\033[1m"; DIM="\033[2m"
    CY="\033[96m"; GR="\033[92m"; YE="\033[93m"; RE="\033[91m"; MA="\033[95m"; BL="\033[94m"; GY="\033[90m"
    BGGR="\033[42m"; BGGY="\033[100m"

DONE_RE  = re.compile(r"\[(\d+)/(\d+)\]\s+✓\s+Score:(\d+)/100\s+\|\s+(\d+)s\s+\|\s+U\$([\d.]+)")
START_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(?!✓)(.+)$")
BATCH_RE = re.compile(r"BATCH\s+(\d+)/(\d+)")
FAIL_RE  = re.compile(r"\[(\d+)/(\d+)\].*(FALHA|ERRO|falhou|reprovado)", re.I)

def parse(log_path, total_hint):
    done={}; started={}; total=total_hint; batch=(0,0); failed=set()
    if not os.path.exists(log_path):
        return dict(done={}, started={}, total=total, batch=batch, failed=failed)
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m=DONE_RE.search(line)
            if m:
                idx=int(m.group(1)); total=int(m.group(2))
                done[idx]=dict(score=int(m.group(3)), secs=int(m.group(4)), cost=float(m.group(5)))
                continue
            m=START_RE.match(line.strip())
            if m:
                idx=int(m.group(1)); total=int(m.group(2)); started[idx]=m.group(3).strip()[:52]
            m=BATCH_RE.search(line)
            if m: batch=(int(m.group(1)), int(m.group(2)))
            m=FAIL_RE.search(line)
            if m: failed.add(int(m.group(1)))
    return dict(done=done, started=started, total=total, batch=batch, failed=failed)

def bar(frac, width=42):
    fill=int(round(frac*width))
    col = C.GR if frac>=1 else (C.CY if frac>=0.5 else C.YE)
    return col + "█"*fill + C.GY + "░"*(width-fill) + C.R

def human(sec):
    sec=int(max(0,sec)); m,s=divmod(sec,60); h,m=divmod(m,60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"

def render(log_path, total_hint, workers, t0, running):
    d=parse(log_path, total_hint)
    done=d["done"]; started=d["started"]; total=d["total"] or total_hint or 1
    nd=len(done); frac=nd/total if total else 0
    times=[v["secs"] for v in done.values()]
    avg=sum(times)/len(times) if times else 0
    cost=sum(v["cost"] for v in done.values())
    remaining=total-nd
    eta = remaining*avg/max(1,workers) if avg else 0
    inflight=sorted(set(started)-set(done))
    elapsed=time.time()-t0
    W="\033[2J\033[H"  # clear + home
    out=[W]
    p=out.append
    p(f"{C.MA}{C.B}╔══════════════════════════════════════════════════════════════╗{C.R}")
    p(f"{C.MA}{C.B}║{C.R}  {C.B}SOWADS ORBIT · ACCESSTAGE — Geração Lote 2 (opus 4.7){C.R}        {C.MA}{C.B}║{C.R}")
    p(f"{C.MA}{C.B}╠══════════════════════════════════════════════════════════════╣{C.R}")
    status = f"{C.GR}● RODANDO{C.R}" if running else (f"{C.GR}✓ CONCLUÍDO{C.R}" if nd>=total else f"{C.RE}■ PARADO{C.R}")
    b = d["batch"]
    p(f"{C.MA}{C.B}║{C.R}  Status: {status}   Batch: {C.CY}{b[0]}/{b[1] or '?'}{C.R}   Workers: {C.CY}{workers}{C.R}          {C.MA}{C.B}║{C.R}")
    p(f"{C.MA}{C.B}║{C.R}                                                              {C.MA}{C.B}║{C.R}")
    p(f"  {bar(frac)}  {C.B}{nd}/{total}{C.R} {C.DIM}({frac*100:4.0f}%){C.R}")
    p("")
    p(f"  {C.GY}Concluídos {C.R}{C.GR}{C.B}{nd}{C.R}   {C.GY}Em andamento {C.R}{C.YE}{C.B}{len(inflight)}{C.R}   {C.GY}Restantes {C.R}{C.B}{remaining}{C.R}   {C.GY}Falhas {C.R}{C.RE}{len(d['failed'])}{C.R}")
    p(f"  {C.GY}Tempo médio/artigo {C.R}{C.CY}{avg:4.0f}s{C.R}   {C.GY}Decorrido {C.R}{C.CY}{human(elapsed)}{C.R}   {C.GY}ETA {C.R}{C.YE}{C.B}~{human(eta)}{C.R}")
    p(f"  {C.GY}Custo acumulado {C.R}{C.GR}{C.B}US$ {cost:5.2f}{C.R}   {C.GY}Projeção {total} arts {C.R}{C.GR}US$ {(cost/nd*total) if nd else 0:5.2f}{C.R}")
    p("")
    if inflight:
        p(f"  {C.YE}▶ Gerando agora:{C.R}")
        for idx in inflight[:workers+1]:
            p(f"    {C.YE}◔{C.R} [{idx:02d}] {C.DIM}{started.get(idx,'')}{C.R}")
    recent=sorted(done.items())[-4:]
    if recent:
        p(f"  {C.GR}✓ Últimos prontos:{C.R}")
        for idx,v in recent:
            sc = C.GR if v['score']>=90 else (C.YE if v['score']>=80 else C.RE)
            p(f"    {C.GR}●{C.R} [{idx:02d}] {sc}{v['score']:>3}/100{C.R} {C.DIM}· {v['secs']}s · US${v['cost']:.2f}{C.R}")
    p("")
    p(f"  {C.DIM}log: {os.path.relpath(log_path, BASE)}   ·   atualiza a cada {C.R}{C.CY}{{INT}}s{C.R}{C.DIM}   ·   Ctrl+C p/ sair{C.R}")
    return "\n".join(out), (nd>=total)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--log", default=os.path.join(BASE,"output/reports/gen_lote2.log"))
    ap.add_argument("--total", type=int, default=28)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--interval", type=int, default=20)
    ap.add_argument("--once", action="store_true")
    a=ap.parse_args()
    t0=time.time()
    # tenta ancorar t0 no mtime de criação do log, se existir
    if os.path.exists(a.log):
        t0=os.path.getmtime(a.log)
    try:
        while True:
            running = bool(os.popen("pgrep -f content_engine.py").read().strip())
            txt, finished = render(a.log, a.total, a.workers, t0, running)
            sys.stdout.write(txt.replace("{INT}", str(a.interval))); sys.stdout.write("\n"); sys.stdout.flush()
            if a.once: break
            if finished and not running:
                sys.stdout.write(f"\n  {C.GR}{C.B}✓ Geração finalizada.{C.R}\n"); break
            time.sleep(a.interval)
    except KeyboardInterrupt:
        sys.stdout.write("\n  (monitor encerrado)\n")

if __name__=="__main__":
    main()
