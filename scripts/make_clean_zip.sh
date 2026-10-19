#!/usr/bin/env bash
# Create a clean zip of CorrosionGuard excluding heavy/generated content.
# Usage: ./scripts/make_clean_zip.sh [output.zip]   (default: corrosionguard.zip)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-corrosionguard.zip}"
rm -f "$OUT"
zip -r "$OUT" . \
  -x ".venv/*" \
  -x ".git/*" \
  -x "outputs/*" \
  -x "*__pycache__*" \
  -x "*.pyc" \
  -x ".pytest_cache/*" \
  -x ".DS_Store" \
  -x "node_modules/*"
echo "Wrote $OUT (excludes .venv, .git, outputs/, __pycache__, .pytest_cache, .DS_Store)"
