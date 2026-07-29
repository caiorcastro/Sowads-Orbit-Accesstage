# Deploy Safety — sowads-orbit é um HUB MULTI-CLIENTE

## Leia antes de qualquer deploy do Firebase

O site **sowads-orbit.web.app** NÃO é só o preview da Accesstage. É um **hub com vários clientes**, cada um numa subpasta:

```
sowads-orbit.web.app/
├── index.html            ← landing "Hub de Previews"
├── accesstage/           ← preview Accesstage (nosso)
├── omt/                  ← Oh My Travel
├── precolandia/          ← Preçolandia  (inclui subpastas aninhadas `r-205cd6b2bf/blog_lote2/` e `blog_lote3/`)
└── simuladinheiro/       ← SimulaDinheiro
```

O target `accesstage` no `firebase.json` tem `public: output/preview`. **`firebase deploy` substitui o site INTEIRO** pelo conteúdo de `output/preview`. Se `output/preview` local não contiver TODOS os clientes (e todas as subpastas aninhadas, como `precolandia/blog_lote2/`), o deploy **apaga** o que faltar.

## Incidente e recuperação (jul/2026)

Um deploy de `output/preview` incompleto derrubou conteúdo aninhado da Preçolandia. O espelhamento que reconstruiu o hub seguiu só os links do `index.html` de cada cliente e **não descobriu subpastas aninhadas** que não estavam linkadas no index. Resultado: 404 em conteúdo de outro cliente.

Em 29/07/2026, o `safe_deploy.py` bloqueou corretamente um novo deploy porque havia 746 paths live ausentes localmente. O procedimento `tools/mirror_live_preview.py` recompôs esses arquivos diretamente da release ativa, **sem apagar ou sobrescrever** arquivos locais; só depois a paridade permitiu o deploy do Lote 3 + Sowads Echo.

## Regras (invioláveis)

1. **NUNCA** rode `firebase deploy` direto. O hook `PreToolUse` bloqueia (tools/guard_firebase_deploy.py).
2. Deploy só via **`python3 tools/safe_deploy.py <target>`**, que compara o local com TODOS os arquivos que estão no ar (API de versões) e **recusa** se algum caminho live sumiria.
3. Sempre `--only hosting:<target>` — nunca deploy sem escopo, nunca `--only hosting` sem target.
4. Verificar pós-deploy pelo **conteúdo** (curl + grep de títulos), não só HTTP 200 — o CDN ignora query string, então `?cache-bust` não fura cache.
5. Se o `safe_deploy.py` indicar paths ausentes, **nunca** usar `--allow-removals` para contornar. Primeiro rodar `python3 tools/mirror_live_preview.py` para baixar somente os arquivos ausentes da release ativa, depois repetir o deploy seguro.

## Rollback de emergência (restaurar versão íntegra)

O Firebase guarda o histórico de versões. Para reverter o site a uma versão anterior íntegra:

```bash
TOKEN=$(gcloud auth print-access-token)
# 1) listar releases e achar a versão boa (fileCount esperado, data anterior ao estrago)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: sowads-orbit" \
  "https://firebasehosting.googleapis.com/v1beta1/sites/sowads-orbit/releases?pageSize=20"
# 2) (opcional) inspecionar arquivos de uma versão:
#   .../versions/<VERSION_ID>/files?pageSize=1000
# 3) rollback: cria release apontando p/ a versão íntegra
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "X-Goog-User-Project: sowads-orbit" \
  "https://firebasehosting.googleapis.com/v1beta1/sites/sowads-orbit/releases?versionName=sites/sowads-orbit/versions/<VERSION_ID>"
```

Precisa de `gcloud` autenticado (Application Default Credentials) + header `X-Goog-User-Project` (senão dá 403 de quota project).

## Como colocar um novo lote de um cliente sem quebrar os outros

1. Espelhar o site live INTEIRO (recursivo, incluindo subpastas aninhadas) para `output/preview/`, OU garantir que `output/preview/` já contém todos os clientes.
2. Trocar/atualizar apenas a subpasta do cliente alvo (ex.: `output/preview/accesstage/`).
3. `python3 tools/safe_deploy.py accesstage` — ele confirma paridade e só então deploya.
4. Verificar por conteúdo cada cliente.

### Recuperar paridade local sem perder arquivos

```bash
# Apenas diagnostica os arquivos live que faltam localmente
python3 tools/mirror_live_preview.py --dry-run

# Baixa somente os paths ausentes da release ativa; não remove nem sobrescreve
python3 tools/mirror_live_preview.py

# Só então o deploy seguro poderá seguir
python3 tools/safe_deploy.py accesstage
```
