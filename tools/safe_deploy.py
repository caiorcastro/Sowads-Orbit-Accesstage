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

Requer: gcloud autenticado (Application Default Credentials).
"""
import os, sys, json, subprocess, urllib.request
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "sowads-orbit"
TARGET_PUBLIC = {"accesstage": "output/preview", "hub": "output/sowads-hosting"}

def token():
    return subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()

def api(path, tok):
    req = urllib.request.Request(
        f"https://firebasehosting.googleapis.com/v1beta1/{path}",
        headers={"Authorization": f"Bearer {tok}", "X-Goog-User-Project": SITE},
    )
    return json.load(urllib.request.urlopen(req, timeout=30))

def live_paths(tok):
    rel = api(f"sites/{SITE}/releases?pageSize=1", tok).get("releases", [])
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

    tok = token()
    live = live_paths(tok)
    local, root = local_paths(public)
    if not os.path.isdir(root):
        print(f"ABORTADO: pasta local não existe: {public}")
        sys.exit(1)

    removed = sorted(p for p in live if p not in local)
    print(f"Target: {target}  | public: {public}")
    print(f"Live: {len(live)} arquivos  | Local: {len(local)} arquivos")

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

    print("Deployando…")
    subprocess.check_call(
        ["firebase", "deploy", "--only", f"hosting:{target}", "--project", SITE],
        cwd=BASE,
    )

if __name__ == "__main__":
    main()
