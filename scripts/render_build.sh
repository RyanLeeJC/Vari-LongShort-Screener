#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -n "${HTTPS_PROXY:-}${HTTP_PROXY:-}${ALL_PROXY:-}" ]]; then
  echo "Proxy configured for Vari supported_assets fetch"
else
  echo "WARNING: no HTTPS_PROXY set — Cloudflare may block Render build (403)"
fi

pip install -r requirements.txt
python scripts/build_screener_data.py

cd longshort-screener
npm ci
npm run build
