#!/bin/bash
# run_lotes.sh — Gera todos os lotes de artigos (nunca publica automaticamente)

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$BASE_DIR/output/reports"
LOG="$LOG_DIR/run_pipeline.log"
mkdir -p "$LOG_DIR"

MODEL="google/gemini-2.5-flash"
FALLBACK_MODEL="google/gemini-2.5-flash-lite"
# Para qualidade máxima (mais lento): MODEL="deepseek/deepseek-v4-pro"

cd "$BASE_DIR"

# Carrega variáveis do .env
if [ -f "$BASE_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$BASE_DIR/.env"
  set +a
fi

WP_URL="${WORDPRESS_URL}"
WP_USER="${WORDPRESS_USER}"
WP_PASS="${WORDPRESS_PASSWORD}"

echo "" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
echo "PIPELINE INICIADO: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"

# ── LOTE VERAGI (10 temas — Plataforma Veragi, Crédito, Integrações, Cash Pooling) ──
echo "" >> "$LOG"
echo "▶ LOTE VERAGI — $(date '+%H:%M:%S')" >> "$LOG"
python3 engine/content_engine.py \
  --model "$MODEL" \
  --fallback_model "$FALLBACK_MODEL" \
  --csv_input "output/articles/lote_veragi_temas.csv" \
  2>&1 | tee -a "$LOG"
if [ ${PIPESTATUS[0]} -ne 0 ]; then echo "ERRO no lote Veragi." >> "$LOG"; exit 1; fi
echo "✅ LOTE VERAGI CONCLUÍDO — $(date '+%H:%M:%S')" >> "$LOG"
# ─────────────────────────────────────────────────────────────────────────────
# Para adicionar novo lote: copie o bloco acima e ajuste o nome e o csv_input
# ─────────────────────────────────────────────────────────────────────────────

echo "" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
echo "✅ GERAÇÃO COMPLETA — $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "Para publicar: python3 engine/publisher.py --test_one" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
