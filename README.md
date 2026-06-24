# Vari Long/Short Screener

Dashboard for Vari 4-bucket long/short selection — mirrors the backtest logic in `ck-cg-backtesting` (`backtest_4buckets.py`).

**Live site:** https://vari-longshort-screener.onrender.com *(set your Render URL after first deploy)*

## Features

- Toggle **B1–B4** buckets (FDV/volume/OI rank bands 1–50, 51–100, 101–150, 151–200)
- Toggle universe rank: **FDV**, **Volume**, **OI**
- **Top 10** and **Bottom 10** panels sorted by 24h chg%
- **Refresh Data** — fetches fresh Vari `supported_assets` server-side (~sub-second)
- Copy button on each panel

## Local development

Copy `env.example` → `.env` if you need `HTTPS_PROXY` locally (usually not required from home).

```bash
pip3 install -r requirements.txt
python3 scripts/build_screener_data.py

cd longshort-screener
npm install
npm run dev
```

Run the full stack (static build + API) locally — matches Render:

```bash
pip3 install -r requirements.txt
./scripts/render_build.sh
python3 -m uvicorn server:app --reload --port 8000
```

Open http://localhost:8000

## Deploy (Render)

Blueprint-managed **Python 3** service (runtime cannot be changed in the dashboard — create a new Docker service if you want `Dockerfile` instead).

1. Connect this repo in [Render](https://render.com) → **New Web Service** (or use existing Blueprint).
2. `render.yaml` sets **build:** `./scripts/render_build.sh` · **start:** `uvicorn server:app --host 0.0.0.0 --port $PORT`
3. In Render → **Environment**, add **`HTTPS_PROXY`** (secret) — **same URL as GridBot / HighOI**:
   - `HTTPS_PROXY=https://user:pass@host:port`
4. **Do not set `PYTHON_VERSION`** and do not add `.python-version` — use Render's default prebuilt Python for your service.
5. Deploy. Pushes to `main` trigger redeploys.

Optional Docker deploy: `Dockerfile` is in the repo; use **New Web Service → Docker** if native Python keeps failing.

Optional: add a Render **Cron Job** to `POST https://<your-service>.onrender.com/api/refresh` every 15 minutes.

## Data

- Vari `GET /api/metadata/supported_assets` (public; `curl_cffi` + Chrome impersonation) for FDV, 24h chg%, volume, and OI
- **`HTTPS_PROXY`** / **`HTTP_PROXY`** — same proxy env as GridBot / HighOI (`Varibot/env.example`)
- Excludes BTC, ETH, and the vari-blacklist (27 tickers)
