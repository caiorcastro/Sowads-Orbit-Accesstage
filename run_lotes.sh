#!/bin/bash
# run_lotes.sh — Gera todos os lotes de artigos (nunca publica automaticamente)

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$BASE_DIR/output/reports"
LOG="$LOG_DIR/run_pipeline.log"
mkdir -p "$LOG_DIR"

MODEL="deepseek/deepseek-v4-pro"

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

# ── Adicione um bloco por lote seguindo o padrão abaixo ──────────────────────
# Exemplo: lote fintech
# echo "" >> "$LOG"
# echo "▶ LOTE FINTECH — $(date '+%H:%M:%S')" >> "$LOG"
# python3 engine/content_engine.py \
#   --model "$MODEL" \
#   --wp_url "$WP_URL" --wp_user "$WP_USER" --wp_pass "$WP_PASS" \
#   --csv_input "output/articles/lote_fintech_temas.csv" \
#   2>&1 | tee -a "$LOG"
# if [ ${PIPESTATUS[0]} -ne 0 ]; then echo "ERRO no lote fintech." >> "$LOG"; exit 1; fi
# echo "✅ LOTE FINTECH CONCLUÍDO — $(date '+%H:%M:%S')" >> "$LOG"
# ─────────────────────────────────────────────────────────────────────────────

echo "" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
echo "✅ GERAÇÃO COMPLETA — $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "Para publicar: python3 engine/publisher.py --test_one" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
