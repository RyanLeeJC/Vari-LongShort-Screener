# Vari Long/Short Screener

Dashboard for Vari 4-bucket long/short selection — mirrors the backtest logic in `ck-cg-backtesting` (`backtest_4buckets.py`).

**Live site:** https://vari-longshort-screener.onrender.com *(set your Render URL after first deploy)*

## Features

- Toggle **B1–B4** buckets (volume/mcap/OI rank bands 1–50, 51–100, 101–150, 151–200)
- Toggle universe rank: **MCap**, **Volume**, **OI**
- **Top 10** and **Bottom 10** panels sorted by 24h chg%
- **Refresh Data** — fetches fresh Vari + CoinGecko data server-side
- Copy button on each panel

## Local development

```bash
pip install -r requirements.txt
python scripts/build_screener_data.py

cd longshort-screener
npm install
npm run dev
```

Run the full stack (static build + API) locally:

```bash
./scripts/render_build.sh
uvicorn server:app --reload --port 8000
```

Open http://localhost:8000

## Deploy (Render)

1. Connect this repo in [Render](https://render.com) → **New Web Service**.
2. Render reads `render.yaml` automatically, or set manually:
   - **Build command:** `./scripts/render_build.sh`
   - **Start command:** `uvicorn server:app --host 0.0.0.0 --port $PORT`
3. Add environment variable **`COINGECKO_API_KEY`** (recommended — reduces rate limits).
4. Deploy. Pushes to `main` trigger redeploys.

Optional: add a Render **Cron Job** to `POST https://<your-service>.onrender.com/api/refresh` every 15 minutes.

## Data

- Vari listings: `GET https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats`
- CoinGecko markets API for market cap and 24h % change
- Excludes BTC, ETH, and the vari-blacklist (27 tickers)
