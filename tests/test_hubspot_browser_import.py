from datetime import datetime

import pytest

import tools.hubspot_browser_import as hubspot_import
from tools.hubspot_browser_import import (
    ImportPreparationError,
    format_publish_date,
    hubspot_url,
    prepare_rows,
    slugify_title,
)


def valid_row(**overrides):
    row = {
        "post_title": "Tesouraria Online: visão D-1 ou tempo real?",
        "post_content": "<p>" + ("conteúdo " * 40) + "</p>",
        "post_status": "draft",
        "qa_score": "100",
        "meta_title": "Tesouraria Online | Accesstage",
        "meta_description": "Entenda a evolução da tesouraria corporativa.",
        "post_date": "2026-08-21 09:30:00",
        "img_blog": "https://example.com/image.jpg",
    }
    row.update(overrides)
    return row


def test_slug_preserves_unicode_like_current_hubspot_urls():
    assert slugify_title("Crédito & Gestão: Visão D-1") == "crédito-gestão-visão-d-1"


def test_hubspot_url_percent_encodes_unicode():
    assert hubspot_url("https://blog.accesstage.com.br/", "Crédito B2B") == (
        "https://blog.accesstage.com.br/cr%C3%A9dito-b2b"
    )


def test_publish_date_uses_required_hubspot_format():
    assert format_publish_date("2026-08-21 10:30:00") == "08/21/2026"
    assert format_publish_date("", datetime(2026, 1, 2)) == "01/02/2026"


def test_invalid_publish_date_fails_closed():
    with pytest.raises(ImportPreparationError):
        format_publish_date("21/08/2026")


def test_browser_mapping_covers_every_generated_hubspot_header():
    assert tuple(header for _, header in hubspot_import.CSV_COLUMN_MAPPING) == (
        hubspot_import.HUBSPOT_HEADERS
    )


def test_prepare_rows_maps_required_fields_without_network():
    prepared, decisions = prepare_rows(
        [valid_row()],
        base_url="https://blog.accesstage.com.br",
        author="Nyara Arcieri",
        tags="Soluções Financeiras,Blog",
        min_qa=80,
        check_public=False,
    )
    assert len(prepared) == 1
    assert decisions[0].decision == "include"
    assert prepared[0]["Author"] == "Nyara Arcieri"
    assert prepared[0]["Categories/Tags"] == "Soluções Financeiras,Blog"
    assert prepared[0]["Post body"].startswith("<p>")


def test_prepare_rows_blocks_low_qa_non_draft_and_duplicates():
    rows = [
        valid_row(qa_score="79"),
        valid_row(post_title="Outro", post_status="published"),
        valid_row(post_title="Duplicado"),
        valid_row(post_title="  duplicado  "),
    ]
    prepared, decisions = prepare_rows(
        rows,
        base_url="https://blog.accesstage.com.br",
        author="Nyara Arcieri",
        tags="Blog",
        min_qa=80,
        check_public=False,
    )
    assert len(prepared) == 1
    assert [item.decision for item in decisions] == ["skip", "skip", "include", "skip"]


def test_prepare_rows_blocks_an_existing_public_url(monkeypatch):
    monkeypatch.setattr(
        hubspot_import,
        "public_url_exists",
        lambda _url: (True, "HTTP 200 (existing URL)"),
    )
    prepared, decisions = prepare_rows(
        [valid_row()],
        base_url="https://blog.accesstage.com.br",
        author="Nyara Arcieri",
        tags="Blog",
        min_qa=80,
        check_public=True,
    )
    assert prepared == []
    assert decisions[0].decision == "skip"
    assert "já publicado" in decisions[0].reason
