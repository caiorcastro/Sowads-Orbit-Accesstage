#!/bin/bash
# run_lotes.sh — Pipeline completo: auto + turismo + publicação como rascunho

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$BASE_DIR/relatorios"
LOG="$LOG_DIR/run_pipeline.log"
mkdir -p "$LOG_DIR"

WP_URL="https://sowads.com.br"
WP_USER="caio"
WP_PASS="Ltx%Z7@*sh%MbXo2waNJZEwB"
MODEL="google/gemini-2.5-flash"

cd "$BASE_DIR"

echo "" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
echo "PIPELINE INICIADO: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"

# ── LOTE AUTO ───────────────────────────────
echo "" >> "$LOG"
echo "▶ LOTE AUTO — $(date '+%H:%M:%S')" >> "$LOG"
echo "────────────────────────────────────────" >> "$LOG"

python3 orbit_content_engine.py \
  --model "$MODEL" \
  --wp_url "$WP_URL" \
  --wp_user "$WP_USER" \
  --wp_pass "$WP_PASS" \
  --csv_input "output_csv_batches_v2/lote_auto_temas.csv" \
  2>&1 | tee -a "$LOG"

if [ ${PIPESTATUS[0]} -ne 0 ]; then
  echo "ERRO no lote auto. Abortando." >> "$LOG"
  exit 1
fi

echo "" >> "$LOG"
echo "✅ LOTE AUTO CONCLUÍDO — $(date '+%H:%M:%S')" >> "$LOG"

# ── LOTE TURISMO ─────────────────────────────
echo "" >> "$LOG"
echo "▶ LOTE TURISMO — $(date '+%H:%M:%S')" >> "$LOG"
echo "────────────────────────────────────────" >> "$LOG"

python3 orbit_content_engine.py \
  --model "$MODEL" \
  --csv_input "output_csv_batches_v2/lote_turismo_temas.csv" \
  2>&1 | tee -a "$LOG"

if [ ${PIPESTATUS[0]} -ne 0 ]; then
  echo "ERRO no lote turismo. Abortando." >> "$LOG"
  exit 1
fi

echo "" >> "$LOG"
echo "✅ LOTE TURISMO CONCLUÍDO — $(date '+%H:%M:%S')" >> "$LOG"

echo "" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
echo "✅ GERAÇÃO COMPLETA — $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "Para publicar: python3 orbit_publisher.py --test_one (valide 1 artigo antes)" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
