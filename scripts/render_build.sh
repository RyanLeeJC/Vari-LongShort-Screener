#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -n "${HTTPS_PROXY:-}${HTTP_PROXY:-}" ]]; then
  echo "HTTPS_PROXY/HTTP_PROXY configured (Vari Cloudflare tunnel)"
else
  echo "WARNING: HTTPS_PROXY not set — Cloudflare may block Render (403). Use same proxy as GridBot / HighOI."
fi

pip install -r requirements.txt
python scripts/build_screener_data.py

cd longshort-screener
npm ci
npm run build
