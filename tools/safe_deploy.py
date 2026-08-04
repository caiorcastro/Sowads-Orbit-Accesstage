#!/usr/bin/env python3
"""
safe_deploy.py — Deploy SEGURO do hub sowads-orbit, com checagem de paridade.

O site é um HUB multi-cliente e `firebase deploy` substitui o site inteiro.
Este script compara a pasta local com TODOS os arquivos que estão no ar (via API de
versões do Firebase) e RECUSA o deploy se algum caminho live sumiria do local
(ou seja, se subir apagaria outro cliente). Só então chama o firebase deploy.

Uso:
  python3 tools/safe_deploy.py accesstage           # confere e deploya output/preview
  python3 tools/safe_deploy.py hub
  python3 tools/safe_deploy.py accesstage --allow-removals   # força (use com MUITO cuidado)
  python3 tools/safe_deploy.py hub --account caiorcastro@gmail.com   # conta específica

Requer: gcloud autenticado. Se a conta ativa do gcloud não for a dona do projeto
(ou o token dela tiver expirado), o script procura sozinho uma conta credenciada
que funcione — dá para fixar com --account ou com a env SOWADS_GCLOUD_ACCOUNT.
"""
import os, sys, subprocess
from collections import Counter

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = "sowads-orbit"
TARGET_PUBLIC = {"accesstage": "output/preview", "hub": "output/sowads-hosting"}
# Cada target publica num SITE diferente do mesmo projeto (ver .firebaserc).
# A checagem de paridade tem de olhar o site certo, senão compara com o site errado.
TARGET_SITE = {"accesstage": "sowads-orbit", "hub": "sowads"}
# Contas que costumam ter acesso ao projeto, tentadas em ordem se a ativa falhar.
FALLBACK_ACCOUNTS = ["caiorcastro@gmail.com", "orbit-ai@sowads.com"]

def _try_token(account=""):
    cmd = ["gcloud", "auth", "print-access-token"] + (["--account", account] if account else [])
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
    except subprocess.CalledProcessError:
        return ""

def token(account=""):
    """Access token do gcloud, com fallback entre contas credenciadas."""
    if account:
        tok = _try_token(account)
        if not tok:
            print(f"ABORTADO: conta {account} não tem token válido. Rode: gcloud auth login {account}")
            sys.exit(1)
        return tok, account

    tok = _try_token()
    if tok:
        return tok, "(conta ativa)"

    print("Conta ativa do gcloud sem token válido — procurando outra conta credenciada…")
    for acct in FALLBACK_ACCOUNTS:
        tok = _try_token(acct)
        if tok:
            print(f"Usando conta: {acct}")
            return tok, acct

    print("ABORTADO: nenhuma conta gcloud com token válido. Rode: gcloud auth login")
    sys.exit(1)

def api(path, tok):
    # requests traz o bundle do certifi — o Python do macOS costuma vir sem CA raiz.
    r = requests.get(
        f"https://firebasehosting.googleapis.com/v1beta1/{path}",
        headers={"Authorization": f"Bearer {tok}", "X-Goog-User-Project": PROJECT},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def live_paths(tok, site):
    rel = api(f"sites/{site}/releases?pageSize=1", tok).get("releases", [])
    if not rel:
        return set()
    ver = rel[0]["version"]["name"]
    files, pagetok = [], ""
    while True:
        q = f"{ver}/files?pageSize=1000" + (f"&pageToken={pagetok}" if pagetok else "")
        d = api(q, tok)
        files += [f["path"] for f in d.get("files", [])]
        pagetok = d.get("nextPageToken")
        if not pagetok:
            break
    return set(files)

def local_paths(public):
    root = os.path.join(BASE, public)
    out = set()
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn == ".DS_Store":
                continue
            rel = "/" + os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
            out.add(rel)
    return out, root

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TARGET_PUBLIC:
        print("uso: safe_deploy.py <accesstage|hub> [--allow-removals]")
        sys.exit(2)
    target = sys.argv[1]
    allow = "--allow-removals" in sys.argv
    public = TARGET_PUBLIC[target]

    account = os.environ.get("SOWADS_GCLOUD_ACCOUNT", "")
    if "--account" in sys.argv:
        i = sys.argv.index("--account")
        if i + 1 >= len(sys.argv):
            print("uso: --account <email>")
            sys.exit(2)
        account = sys.argv[i + 1]

    site = TARGET_SITE[target]
    tok, used_account = token(account)
    live = live_paths(tok, site)
    local, root = local_paths(public)
    if not os.path.isdir(root):
        print(f"ABORTADO: pasta local não existe: {public}")
        sys.exit(1)

    # /__/ é namespace reservada do Firebase Hosting (init.js/init.json do SDK):
    # é servida automaticamente e nunca vem da pasta local, então não conta como remoção.
    removed = sorted(p for p in live if p not in local and not p.startswith("/__/"))
    print(f"Target: {target}  | site: {site}  | public: {public}  | gcloud: {used_account}")
    print(f"Live: {len(live)} arquivos  | Local: {len(local)} arquivos", flush=True)

    if removed:
        c = Counter(("/" + p.split("/")[1]) if p.count("/") >= 2 else "/(raiz)" for p in removed)
        print(f"\n⛔ {len(removed)} caminhos que estão NO AR sumiriam (ausentes no local):")
        for k, v in c.most_common():
            print(f"   {k}/… : {v} arquivos")
        for p in removed[:8]:
            print("     ex:", p)
        if not allow:
            print("\nABORTADO. Deployar agora apagaria os caminhos acima (provável outro cliente).")
            print("Espelhe o site live completo para o local primeiro, ou use --allow-removals se for intencional.")
            sys.exit(1)
        print("\n⚠️  --allow-removals ativo: prosseguindo mesmo com remoções.")
    else:
        print("✅ Paridade OK — o local contém tudo que está no ar. Nada de outro cliente será apagado.")

    print("Deployando…", flush=True)
    cmd = ["firebase", "deploy", "--only", f"hosting:{target}", "--project", PROJECT]
    if account:
        cmd += ["--account", account]
    subprocess.check_call(cmd, cwd=BASE)

if __name__ == "__main__":
    main()
