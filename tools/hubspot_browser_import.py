#!/usr/bin/env python3
"""Prepare and import Orbit articles as HubSpot blog drafts through Chrome.

The supported workflow uses HubSpot's native CSV blog importer instead of
calling private browser endpoints or replaying session cookies:

1. Convert an Orbit article CSV to HubSpot's documented import format.
2. Reject rows whose public URL already exists (idempotency guard).
3. Optionally open a persistent, visible Chrome profile and drive the importer.
4. Stop before the external mutation unless ``--commit-drafts`` is present.

The dedicated Chrome profile lives in ``.hubspot-browser-profile/`` and is
gitignored. On the first browser run, sign in interactively; later runs reuse
that HubSpot session.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_DIR = BASE_DIR / ".hubspot-browser-profile"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output" / "hubspot-import"
DEFAULT_PORTAL_ID = "457604"
DEFAULT_BLOG_BASE_URL = "https://blog.accesstage.com.br"
DEFAULT_BLOG_NAME = "Blog Accesstage"
DEFAULT_SOURCE_PLATFORM = "Outro"
DEFAULT_AUTHOR = "Nyara Arcieri"
DEFAULT_TAGS = "Soluções Financeiras,Blog"

HUBSPOT_HEADERS = (
    "URL",
    "Title",
    "SEO title",
    "Author",
    "Featured image",
    "Categories/Tags",
    "Meta description",
    "Publish date",
    "Post body",
)


@dataclass(frozen=True)
class Decision:
    row: int
    title: str
    url: str
    decision: str
    reason: str


class ImportPreparationError(ValueError):
    """Raised when the input cannot safely be converted."""


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def slugify_title(value: str) -> str:
    """Approximate HubSpot's Unicode-friendly title slug."""
    normalized = unicodedata.normalize("NFC", value).casefold().strip()
    chars = []
    for char in normalized:
        category = unicodedata.category(char)
        if char.isspace() or char in "_-":
            chars.append("-")
        elif category[0] in {"L", "N"}:
            chars.append(char)
    return re.sub(r"-+", "-", "".join(chars)).strip("-")


def hubspot_url(base_url: str, title: str) -> str:
    slug = slugify_title(title)
    if not slug:
        raise ImportPreparationError(f"Título sem slug utilizável: {title!r}")
    return f"{base_url.rstrip('/')}/{quote(slug, safe='-')}"


def format_publish_date(value: str, fallback: datetime | None = None) -> str:
    """HubSpot's CSV importer accepts only MM/DD/YYYY."""
    fallback = fallback or datetime.now()
    raw = (value or "").strip()
    if not raw:
        return fallback.strftime("%m/%d/%Y")
    candidates = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y")
    for pattern in candidates:
        try:
            return datetime.strptime(raw[:19], pattern).strftime("%m/%d/%Y")
        except ValueError:
            continue
    raise ImportPreparationError(f"Data inválida para o HubSpot: {value!r}")


def public_url_exists(url: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Return whether a URL already resolves to public content."""
    response = requests.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={"User-Agent": "Sowads-Orbit-HubSpot-Preflight/1.0"},
    )
    if response.status_code == 404:
        return False, "HTTP 404"
    if response.status_code == 200:
        return True, f"HTTP 200 ({response.url})"
    raise ImportPreparationError(
        f"Não foi possível confirmar {url}: HTTP {response.status_code}"
    )


def read_orbit_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        required = {"post_title", "post_content", "meta_description"}
        missing = sorted(required - headers)
        if missing:
            raise ImportPreparationError(
                f"CSV sem colunas obrigatórias do Orbit: {', '.join(missing)}"
            )
        return [dict(row) for row in reader]


def prepare_rows(
    rows: Iterable[dict[str, str]],
    *,
    base_url: str,
    author: str,
    tags: str,
    min_qa: int,
    check_public: bool,
) -> tuple[list[dict[str, str]], list[Decision]]:
    prepared: list[dict[str, str]] = []
    decisions: list[Decision] = []
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()

    for index, row in enumerate(rows, start=1):
        title = (row.get("post_title") or "").strip()
        content = (row.get("post_content") or "").strip()
        status = (row.get("post_status") or "draft").strip().casefold()
        url = hubspot_url(base_url, title) if title else ""

        def skip(reason: str) -> None:
            decisions.append(Decision(index, title, url, "skip", reason))

        if not title or len(content) < 200:
            skip("título ausente ou conteúdo menor que 200 caracteres")
            continue
        if "ERRO" in content:
            skip("conteúdo marcado com ERRO")
            continue
        if status not in {"draft", "rascunho"}:
            skip(f"status local não é draft: {status}")
            continue
        try:
            qa_score = int(float((row.get("qa_score") or "0").strip()))
        except ValueError:
            qa_score = 0
        if qa_score < min_qa:
            skip(f"QA {qa_score} abaixo do mínimo {min_qa}")
            continue

        normalized = normalize_title(title)
        if normalized in seen_titles or url in seen_urls:
            skip("duplicado dentro do próprio CSV")
            continue
        seen_titles.add(normalized)
        seen_urls.add(url)

        if check_public:
            exists, evidence = public_url_exists(url)
            if exists:
                skip(f"já publicado: {evidence}")
                continue

        prepared.append(
            {
                "URL": url,
                "Title": title,
                "SEO title": (row.get("meta_title") or title).strip(),
                "Author": author,
                "Featured image": (row.get("img_blog") or "").strip(),
                "Categories/Tags": tags,
                "Meta description": (row.get("meta_description") or "").strip(),
                "Publish date": format_publish_date(row.get("post_date") or ""),
                "Post body": content,
            }
        )
        decisions.append(Decision(index, title, url, "include", "apto para import"))

    return prepared, decisions


def write_import_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=HUBSPOT_HEADERS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def write_audit(path: Path, source: Path, decisions: list[Decision]) -> None:
    payload = {
        "source": str(source.resolve()),
        "generated_at": datetime.now().astimezone().isoformat(),
        "included": sum(item.decision == "include" for item in decisions),
        "skipped": sum(item.decision == "skip" for item in decisions),
        "decisions": [asdict(item) for item in decisions],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def first_visible(page, candidates):
    for locator in candidates:
        try:
            locator.wait_for(state="visible", timeout=4_000)
            return locator
        except Exception:
            continue
    return None


def verify_imported_drafts(page, rows: list[dict[str, str]], portal_id: str) -> list[dict]:
    """Reconcile imported titles against HubSpot's blog manager."""
    page.goto(f"https://app.hubspot.com/blog/{portal_id}/manage/posts/all-drafts")
    page.wait_for_load_state("domcontentloaded")
    results = []
    page.get_by_text(re.compile("Todos os rascunhos|All drafts", re.I)).first.wait_for(
        state="visible", timeout=30_000
    )

    for row in rows:
        title = row["Title"]
        post_row = page.get_by_role("row").filter(has_text=title).first
        try:
            post_row.wait_for(state="visible", timeout=30_000)
            found = True
            is_draft = bool(re.search(r"Rascunho|Draft", post_row.inner_text(), re.I))
        except Exception:
            found = False
            is_draft = False
        results.append(
            {
                "title": title,
                "found": found,
                "draft": is_draft,
                "error": "" if is_draft else "título/status draft não confirmado",
            }
        )

    return results


CSV_COLUMN_MAPPING = (
    (r"^URL\s*\*", "URL"),
    (r"^Título\s*\*|^Title\s*\*", "Title"),
    (r"^Título de SEO\s*\*|^SEO title\s*\*", "SEO title"),
    (r"^Autor\s*\*|^Author\s*\*", "Author"),
    (r"^Imagem em destaque|^Featured image", "Featured image"),
    (r"^Categorias/Tags|^Categories/Tags", "Categories/Tags"),
    (r"^Metadescrição\s*\*|^Meta description\s*\*", "Meta description"),
    (r"^Data de publicação\s*\*|^Publish date\s*\*", "Publish date"),
    (r"^Corpo do post\s*\*|^Post body\s*\*", "Post body"),
)


def select_dropdown_option(page, button, option_name: str) -> None:
    button.click()
    option = page.get_by_role("option", name=option_name, exact=True).first
    option.wait_for(state="visible", timeout=30_000)
    option.click()


def map_csv_columns(page) -> None:
    """Map the documented English CSV headers in HubSpot's localized UI."""
    for property_pattern, csv_header in CSV_COLUMN_MAPPING:
        property_label = page.get_by_text(
            re.compile(property_pattern, re.I), exact=True
        ).first
        row = page.get_by_role("row").filter(has=property_label).first
        select = row.get_by_role(
            "button", name=re.compile("Selecione uma coluna|Select a column", re.I)
        ).first
        select.wait_for(state="visible", timeout=30_000)
        select_dropdown_option(page, select, csv_header)


def run_browser_import(
    import_csv: Path,
    *,
    portal_id: str,
    blog_name: str,
    source_platform: str,
    profile_dir: Path,
    commit_drafts: bool,
) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportPreparationError(
            "Playwright não está instalado. Execute: pip install playwright"
        ) from exc

    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chrome",
            headless=False,
            slow_mo=120,
            viewport={"width": 1440, "height": 960},
        )
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(f"https://app.hubspot.com/blog/{portal_id}/manage")
            page.wait_for_load_state("domcontentloaded")

            if "/login" in page.url:
                print("\nFaça login no Chrome aberto pelo script.")
                input("Quando o portal HubSpot estiver aberto, pressione ENTER aqui... ")
                page.goto(f"https://app.hubspot.com/blog/{portal_id}/manage")

            page.get_by_text(re.compile("Accesstage", re.I)).first.wait_for(
                state="visible", timeout=30_000
            )

            import_blog = first_visible(
                page,
                [
                    page.get_by_text(re.compile("Importar blog|Import blog", re.I)),
                    page.get_by_role("button", name=re.compile("Importar blog|Import blog", re.I)),
                    page.get_by_role("link", name=re.compile("Importar blog|Import blog", re.I)),
                ],
            )
            if import_blog is None:
                raise ImportPreparationError(
                    "Opção 'Importar blog' não encontrada; confira a permissão de Importação"
                )
            import_blog.click()

            start = first_visible(
                page,
                [
                    page.get_by_role("button", name=re.compile("Importar novo blog|Import new blog", re.I)),
                    page.get_by_role("button", name=re.compile("Iniciar nova importa|Start new import", re.I)),
                ],
            )
            if start is not None:
                start.click()

            csv_option = first_visible(
                page,
                [
                    page.get_by_role(
                        "radio",
                        name=re.compile(
                            "Carregamento de arquivo CSV|Upload de arquivo CSV|CSV file upload",
                            re.I,
                        ),
                    ),
                    page.get_by_text(
                        re.compile(
                            "Carregamento de arquivo CSV|Upload de arquivo CSV|CSV file upload",
                            re.I,
                        )
                    ),
                ],
            )
            if csv_option is None:
                raise ImportPreparationError("Opção de upload CSV não encontrada")
            try:
                csv_option.check()
            except Exception:
                csv_option.click()

            next_control = first_visible(
                page,
                [
                    page.get_by_role("link", name=re.compile("^Próximo$|^Next$", re.I)),
                    page.get_by_role("button", name=re.compile("^Próximo$|^Next$", re.I)),
                ],
            )
            if next_control is None:
                raise ImportPreparationError("Controle Próximo não encontrado")
            next_control.click()

            platform_button = page.get_by_role(
                "button",
                name=re.compile("Qual plataforma de blog|current blog platform", re.I),
            )
            platform_button.wait_for(state="visible", timeout=30_000)
            select_dropdown_option(page, platform_button, source_platform)

            blog_button = page.get_by_role(
                "button", name=re.compile("Blog da HubSpot|HubSpot blog", re.I)
            )
            select_dropdown_option(page, blog_button, blog_name)

            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(str(import_csv.resolve()))

            copy_posts = first_visible(
                page,
                [
                    page.get_by_role(
                        "button",
                        name=re.compile(
                            "Copiar posts (?:de|do) blog|Copy blog posts", re.I
                        ),
                    ),
                    page.get_by_role("button", name=re.compile("Próximo|Next", re.I)),
                ],
            )
            if copy_posts is None:
                raise ImportPreparationError("Botão para processar o CSV não encontrado")
            copy_posts.click()

            page.get_by_text(
                re.compile("Mapear as coluna|Map columns", re.I)
            ).first.wait_for(state="visible", timeout=60_000)
            map_csv_columns(page)
            page.get_by_role(
                "button", name=re.compile("^Próximo$|^Next$", re.I)
            ).click()

            select_all = page.get_by_role(
                "button", name=re.compile("Selecione todos os|Select all", re.I)
            ).first
            select_all.wait_for(state="visible", timeout=60_000)
            select_all.click()

            if not commit_drafts:
                print(
                    "CSV carregado, mapeado e revisado. Encerrando antes do clique "
                    "Importar; use --commit-drafts para criar os rascunhos."
                )
                return

            confirmation = input(
                "Digite IMPORTAR DRAFTS para autorizar o clique final no HubSpot: "
            )
            if confirmation != "IMPORTAR DRAFTS":
                print("Importação cancelada antes da mutação.")
                return

            import_button = first_visible(
                page,
                [page.get_by_role("button", name=re.compile("^Importar$|^Import$", re.I))],
            )
            if import_button is None:
                raise ImportPreparationError("Botão Importar não encontrado na revisão")
            import_button.click()

            import_dialog = page.get_by_role("dialog").last
            drafts = import_dialog.get_by_role(
                "radio", name=re.compile("Rascunhos|Drafts", re.I)
            )
            drafts.wait_for(state="visible", timeout=30_000)
            drafts.check()

            override = import_dialog.get_by_role(
                "checkbox", name=re.compile("Substitua|sobrescrever|override", re.I)
            )
            if override.count() and override.first.is_checked():
                override.first.uncheck()

            save = import_dialog.get_by_role(
                "button", name=re.compile("^Salvar$|^Save$", re.I)
            )
            save.click()
            page.wait_for_url(re.compile(r"/content-import/dashboard"), timeout=60_000)
            page.get_by_text(
                re.compile("Importação concluída|Import completed", re.I)
            ).wait_for(
                state="visible", timeout=180_000
            )
            with import_csv.open(newline="", encoding="utf-8-sig") as handle:
                imported_rows = list(csv.DictReader(handle))
            verification = verify_imported_drafts(
                page, rows=imported_rows, portal_id=portal_id
            )
            verification_path = import_csv.with_suffix(".verification.json")
            verification_path.write_text(
                json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            confirmed = sum(item["draft"] for item in verification)
            print(
                f"Importação concluída; {confirmed}/{len(verification)} drafts "
                f"confirmados. Relatório: {verification_path}"
            )
        finally:
            trace_path = DEFAULT_OUTPUT_DIR / "hubspot-browser-trace.zip"
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            context.tracing.stop(path=str(trace_path))
            context.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orbit CSV -> importador oficial de drafts do HubSpot via Chrome"
    )
    parser.add_argument("--csv", required=True, type=Path, help="CSV de artigos do Orbit")
    parser.add_argument("--portal-id", default=DEFAULT_PORTAL_ID)
    parser.add_argument("--blog-base-url", default=DEFAULT_BLOG_BASE_URL)
    parser.add_argument("--blog-name", default=DEFAULT_BLOG_NAME)
    parser.add_argument("--source-platform", default=DEFAULT_SOURCE_PLATFORM)
    parser.add_argument("--author", default=DEFAULT_AUTHOR)
    parser.add_argument("--tags", default=DEFAULT_TAGS)
    parser.add_argument("--min-qa", type=int, default=80)
    parser.add_argument("--output", type=Path, help="CSV HubSpot de saída")
    parser.add_argument("--skip-public-check", action="store_true")
    parser.add_argument("--browser", action="store_true", help="Abrir Chrome e enviar o CSV")
    parser.add_argument(
        "--commit-drafts",
        action="store_true",
        help="Permitir confirmação final no HubSpot; ainda exige frase no terminal",
    )
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source = args.csv.expanduser().resolve()
    if not source.exists():
        print(f"ERRO: CSV não encontrado: {source}", file=sys.stderr)
        return 2

    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", source.stem)
    output = args.output or DEFAULT_OUTPUT_DIR / f"{stem}_hubspot_import.csv"
    output = output.expanduser().resolve()
    audit = output.with_suffix(".audit.json")

    try:
        source_rows = read_orbit_rows(source)
        prepared, decisions = prepare_rows(
            source_rows,
            base_url=args.blog_base_url,
            author=args.author,
            tags=args.tags,
            min_qa=args.min_qa,
            check_public=not args.skip_public_check,
        )
        write_import_csv(output, prepared)
        write_audit(audit, source, decisions)
    except (ImportPreparationError, requests.RequestException) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    skipped = len(decisions) - len(prepared)
    print(f"Fonte       : {source}")
    print(f"Aptos       : {len(prepared)}")
    print(f"Bloqueados  : {skipped}")
    print(f"CSV HubSpot : {output}")
    print(f"Auditoria   : {audit}")

    if not prepared:
        print("Nada será enviado: todas as linhas foram bloqueadas pelo preflight.")
        return 0

    if args.browser:
        try:
            run_browser_import(
                output,
                portal_id=args.portal_id,
                blog_name=args.blog_name,
                source_platform=args.source_platform,
                profile_dir=args.profile_dir.expanduser().resolve(),
                commit_drafts=args.commit_drafts,
            )
        except ImportPreparationError as exc:
            print(f"ERRO DE BROWSER: {exc}", file=sys.stderr)
            return 3
    else:
        print("Prepare-only: use --browser para abrir o importador oficial do HubSpot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
