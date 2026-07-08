#!/usr/bin/env python3
"""
guard_firebase_deploy.py — Hook PreToolUse que BLOQUEIA `firebase deploy` direto.

Motivo: sowads-orbit.web.app é um HUB MULTI-CLIENTE (accesstage, omt, precolandia,
simuladinheiro). Um `firebase deploy` substitui o site INTEIRO; se a pasta local não
tiver todos os clientes, apaga os outros. Já aconteceu (precolandia/blog_lote2, jul/2026).

Deploys devem passar por tools/safe_deploy.py, que confere paridade com o site live antes.
Escape consciente: incluir o texto SAFE_DEPLOY_OK no comando.

Só bloqueia quando `firebase deploy` aparece como COMANDO de verdade (início de um segmento
do shell), NÃO quando é só substring (ex.: dentro de uma mensagem de commit ou de um echo).
"""
import sys, json, re

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

cmd = ((data.get("tool_input") or {}).get("command")) or ""

if "SAFE_DEPLOY_OK" in cmd:
    sys.exit(0)

# quebra o comando em segmentos nos separadores do shell
segments = re.split(r"(?:\n|;|&&|\|\||\||&|\(|\)|`|\$\()", cmd)

def is_real_deploy(seg: str) -> bool:
    s = seg.strip()
    # remove wrappers comuns no início (nohup, sudo, env VAR=x, time)
    s = re.sub(r"^(?:nohup\s+|sudo\s+|time\s+|env\s+\w+=\S+\s+)+", "", s)
    # bloqueia SÓ o deploy LIVE (substitui o site inteiro). Preview channel
    # (hosting:channel:deploy) é SEGURO — URL isolada, não toca no live — e fica LIBERADO.
    return bool(re.match(r"firebase\s+deploy\b", s))

if any(is_real_deploy(seg) for seg in segments):
    reason = (
        "BLOQUEADO pelo guardrail de deploy. O site sowads-orbit é um HUB multi-cliente "
        "(accesstage, omt, precolandia, simuladinheiro) e `firebase deploy` substitui o site "
        "INTEIRO — se a pasta local não contiver todos os clientes, apaga os outros "
        "(já derrubou precolandia/blog_lote2). NÃO rode firebase deploy direto. "
        "Use: python3 tools/safe_deploy.py <target> (confere paridade com o live antes de subir). "
        "Se for realmente intencional e você já verificou, inclua SAFE_DEPLOY_OK no comando."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)

sys.exit(0)
