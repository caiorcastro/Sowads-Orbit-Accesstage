#!/usr/bin/env python3
"""
merge_retry.py — Mescla artigos de retry no CSV principal.

Uso:
  python3 tools/merge_retry.py \
    --main  output/articles/lote_veragi_batch1_artigos_1_a_10.csv \
    --retry output/articles/lote_veragi_retry_4_8_batch1_artigos_1_a_2.csv \
    --topics output/articles/lote_veragi_temas.csv

Identifica cada artigo do retry pelo post_title (exact match com o tópico no CSV de temas),
substitui a linha correspondente no main CSV e salva in-place.
"""
import csv, sys, argparse, os

def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def save_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--main",   required=True)
    parser.add_argument("--retry",  required=True)
    parser.add_argument("--topics", required=True)
    args = parser.parse_args()

    main_rows   = load_csv(args.main)
    retry_rows  = load_csv(args.retry)
    topic_rows  = load_csv(args.topics)

    fieldnames = list(main_rows[0].keys()) if main_rows else []

    # Build map: normalized_title → topic order index (0-based)
    topic_order = {row["topic_pt"].strip().lower(): i for i, row in enumerate(topic_rows)}

    # Build replacement map from retry CSV: topic_order_index → retry_row
    retry_map = {}
    for rrow in retry_rows:
        title = rrow.get("post_title", "").strip()
        # Find matching topic (prefix or exact)
        for topic, idx in topic_order.items():
            if title.lower().startswith(topic[:40].lower()) or topic.lower().startswith(title[:40].lower()):
                retry_map[idx] = rrow
                print(f"  Retry match: [{idx+1:02d}] '{title[:60]}'  score={rrow.get('qa_score','?')}")
                break
        else:
            print(f"  [WARN] Não encontrou tópico para: '{title[:60]}'", file=sys.stderr)

    if not retry_map:
        print("Nenhum artigo de retry mapeado. Abortando.", file=sys.stderr)
        sys.exit(1)

    # Replace in main_rows
    replaced = 0
    for main_idx, mrow in enumerate(main_rows):
        mtitle = mrow.get("post_title", "").strip()
        for topic, tidx in topic_order.items():
            if mtitle.lower().startswith(topic[:40].lower()) or topic.lower().startswith(mtitle[:40].lower()):
                if tidx in retry_map:
                    rrow = retry_map[tidx]
                    # Copy all fields from retry into main row
                    for k in fieldnames:
                        if k in rrow:
                            mrow[k] = rrow[k]
                    main_rows[main_idx] = mrow
                    replaced += 1
                    print(f"  Substituído [{tidx+1:02d}]: '{mtitle[:60]}'")
                break

    save_csv(args.main, main_rows, fieldnames)
    print(f"\n✅ {replaced} artigo(s) substituído(s) em {args.main}")

if __name__ == "__main__":
    main()
