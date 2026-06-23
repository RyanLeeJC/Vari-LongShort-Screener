# Vari Long/Short Screener

GitHub Pages dashboard for Vari 4-bucket long/short selection — mirrors the backtest logic in `ck-cg-backtesting` (`backtest_4buckets.py`).

**Live site:** https://ryanleejc.github.io/Vari-LongShort-Screener/

## Features

- Toggle **B1–B4** buckets (volume/mcap/OI rank bands 1–50, 51–100, 101–150, 151–200)
- Toggle universe rank: **MCap**, **Volume**, **OI**
- **Top 10** and **Bottom 10** panels sorted by 24h chg% (descending)
- Copy button on each panel

## Local development

```bash
pip install -r requirements.txt
python scripts/build_screener_data.py

cd longshort-screener
npm install
npm run dev
```

## Deploy

Pushes to `main` trigger the GitHub Actions workflow (`.github/workflows/github-pages.yml`), which refreshes screener data and deploys the Vite build to GitHub Pages.

## Data

- Vari listings: `GET https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats`
- CoinGecko markets API for market cap and 24h % change
- Excludes BTC, ETH, and the vari-blacklist (27 tickers)
