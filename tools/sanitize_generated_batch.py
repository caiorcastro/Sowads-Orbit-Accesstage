#!/usr/bin/env python3
"""Aplica o compliance Accesstage a CSVs já gerados e recalcula o QA."""

import argparse
import csv
import glob
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from engine.content_engine import (
    clamp_meta_text,
    remove_unsupported_claims,
    sanitize_accesstage_compliance,
)
from engine.qa_validator import OrbitValidator


def sanitize_file(path, in_place=False):
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    validator = OrbitValidator()
    changed = 0
    blocked = 0
    scores = []

    for row in rows:
        original = row.get("post_content", "")
        content = sanitize_accesstage_compliance(original)
        content = remove_unsupported_claims(content)
        row["post_content"] = content
        row["meta_title"] = clamp_meta_text(row.get("meta_title", ""), 60)
        row["meta_description"] = clamp_meta_text(
            row.get("meta_description", ""), 155
        )

        score, _issues = validator.grade_article_raw(content)
        row["qa_score"] = str(score)
        scores.append(score)
        if score < 80:
            row["post_status"] = "error"
            blocked += 1
        if content != original:
            changed += 1

    target = source if in_place else source.with_name(source.stem + "_sanitized.csv")
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    average = sum(scores) / len(scores) if scores else 0
    return target, len(rows), changed, blocked, average


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="CSV ou glob de CSVs gerados")
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()

    matches = []
    for pattern in args.paths:
        matches.extend(glob.glob(pattern))
    matches = sorted(set(matches))
    if not matches:
        raise SystemExit("Nenhum CSV encontrado.")

    total_rows = total_changed = total_blocked = 0
    weighted_score = 0.0
    for path in matches:
        target, count, changed, blocked, average = sanitize_file(path, args.in_place)
        total_rows += count
        total_changed += changed
        total_blocked += blocked
        weighted_score += average * count
        print(
            f"{target}: {count} linhas, {changed} ajustadas, "
            f"{blocked} bloqueadas, QA médio {average:.1f}/100"
        )

    overall = weighted_score / total_rows if total_rows else 0
    print(
        f"TOTAL: {total_rows} linhas, {total_changed} ajustadas, "
        f"{total_blocked} bloqueadas, QA médio {overall:.1f}/100"
    )


if __name__ == "__main__":
    main()
