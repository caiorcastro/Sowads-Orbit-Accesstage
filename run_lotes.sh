#!/bin/bash
# run_lotes.sh — Gera todos os lotes de artigos + copies sociais + events CSV
# Nunca publica automaticamente.

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$BASE_DIR/output/reports"
LOG="$LOG_DIR/run_pipeline.log"
mkdir -p "$LOG_DIR"

MODEL="google/gemini-2.5-flash"
FALLBACK_MODEL="google/gemini-2.5-flash-lite"
# Qualidade máxima (mais lento, custo alto):
#   MODEL="anthropic/claude-opus-4.7"
#   FALLBACK_MODEL="anthropic/claude-sonnet-4.6"

cd "$BASE_DIR"

# Carrega variáveis do .env
if [ -f "$BASE_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$BASE_DIR/.env"
  set +a
fi

echo "" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
echo "PIPELINE INICIADO: $(date '+%Y-%m-%d %H:%M:%S') | modelo: $MODEL" >> "$LOG"
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

# ── COPIES SOCIAIS + EVENTS CSV ──────────────────────────────────────────────
# Detecta o CSV do lote mais recente gerado acima e gera copies + events
echo "" >> "$LOG"
echo "▶ COPIES SOCIAIS + EVENTS — $(date '+%H:%M:%S')" >> "$LOG"

LATEST_CSV=$(ls -t "$BASE_DIR/output/articles/"*_batch*_artigos_*.csv 2>/dev/null | grep -v "\-backup\." | head -1)

if [ -n "$LATEST_CSV" ]; then
  echo "  CSV: $LATEST_CSV" >> "$LOG"
  python3 engine/social_agent.py --from_csv "$LATEST_CSV" 2>&1 | tee -a "$LOG"
  echo "✅ COPIES + EVENTS CONCLUÍDOS — $(date '+%H:%M:%S')" >> "$LOG"
else
  echo "⚠️  Nenhum CSV de batch encontrado para gerar events." >> "$LOG"
fi

echo "" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
echo "✅ PIPELINE COMPLETO — $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "Preview: python3 tools/preview_generator.py" >> "$LOG"
echo "Publicar: python3 engine/publisher.py --test_one" >> "$LOG"
echo "════════════════════════════════════════" >> "$LOG"
