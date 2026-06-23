#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

pip install -r requirements.txt
python scripts/build_screener_data.py

cd longshort-screener
npm ci
npm run build
