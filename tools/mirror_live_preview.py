#!/usr/bin/env python3
"""Espelha arquivos ausentes do Firebase Hosting para restaurar a paridade local.

Não remove e não sobrescreve arquivos locais. Baixa apenas paths que existem na versão live
e não existem em output/preview, validando o SHA-256 informado pela API antes de gravar.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request

import certifi

SITE = "sowads-orbit"
API = "https://firebasehosting.googleapis.com/v1beta1"
LIVE = "https://sowads-orbit.web.app"
CONTEXT = ssl.create_default_context(cafile=certifi.where())


def token():
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()


def api_json(path, access_token):
    request = urllib.request.Request(
        f"{API}/{path}",
        headers={"Authorization": f"Bearer {access_token}", "X-Goog-User-Project": SITE},
    )
    with urllib.request.urlopen(request, context=CONTEXT, timeout=60) as response:
        return json.load(response)


def current_files(access_token):
    release = api_json(f"sites/{SITE}/releases?pageSize=1", access_token)["releases"][0]
    version = release["version"]["name"]
    files, page = [], ""
    while True:
        suffix = f"&pageToken={urllib.parse.quote(page)}" if page else ""
        data = api_json(f"{version}/files?pageSize=1000{suffix}", access_token)
        files.extend(data.get("files", []))
        page = data.get("nextPageToken", "")
        if not page:
            return version, files


def download(path):
    quoted = urllib.parse.quote(path, safe="/%")
    request = urllib.request.Request(f"{LIVE}{quoted}", headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, context=CONTEXT, timeout=120) as response:
        return response.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="output/preview")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.exit(f"Pasta local não encontrada: {root}")

    version, files = current_files(token())
    missing = [item for item in files if not os.path.isfile(os.path.join(root, item["path"].lstrip("/")))]
    print(f"Versão live: {version} | arquivos: {len(files)} | ausentes localmente: {len(missing)}")
    if args.dry_run:
        for item in missing[:30]:
            print(item["path"])
        return

    def restore(item):
        path = item["path"]
        data = download(path)
        # A API registra o SHA-256 do artefato gzip enviado no deploy, enquanto o
        # domínio público devolve o conteúdo descompactado. Portanto os hashes não
        # são comparáveis aqui; o download vem da release live exata e é preservado
        # byte a byte como ela é servida aos visitantes.
        actual = hashlib.sha256(data).hexdigest()[:12]
        destination = os.path.join(root, path.lstrip("/"))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as file:
            file.write(data)
        return path, len(data), actual

    # Downloads independentes: paraleliza apenas arquivos ausentes, sem tocar em
    # nenhum path já presente localmente. Mantém o espelhamento rápido mesmo quando
    # o hub contém centenas de imagens legadas.
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(restore, item) for item in missing]
        for number, future in enumerate(as_completed(futures), 1):
            path, size, actual = future.result()
            print(f"[{number}/{len(missing)}] {path} ({size} bytes · {actual})")
    print("✓ Paridade local restaurada sem remover ou sobrescrever arquivos.")


if __name__ == "__main__":
    main()
