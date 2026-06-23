# Vari 24h change % — `supported_assets` endpoint

How the longshort bot (`longshortoivol` / `Varibot`) gets **24h chg%** for ranking. This is a **single Vari bulk call**, not CoinGecko.

---

## Endpoint

| | |
|---|---|
| **Method / path** | `GET /api/metadata/supported_assets` |
| **Base URL** | `VARI_BASE_URL` in `Varibot/.env` (default `https://omni.variational.io`) |
| **Auth** | Omni session cookie / `VR_TOKEN` (same as other authenticated Vari API calls) |
| **Client** | `VariEndpoints.get_supported_assets()` → `Varibot/variationalbot/vari/endpoints.py` |

Full URL example:

```text
https://omni.variational.io/api/metadata/supported_assets
```

---

## Response shape

- Top-level **dict** keyed by underlying ticker (e.g. `BTC`, `ETH`, `SOL`).
- Each value is a **list** of one or more instrument rows (crypto perps use `instrument_type: perpetual_future`).
- Relevant row fields (probed 2026-06-04):

| Field | Type | Notes |
|-------|------|--------|
| `price_change_percentage_24h` | float | **24h % change** — percent, not decimal (e.g. `-1.79` = −1.79%) |
| `price` / `index_price` | float | Mark / index |
| `volume_24h` | float | 24h volume (USD) |
| `coingecko_id` | string | For optional CoinGecko enrichment (7d %, missing market cap) |
| `funding_rate` | float | Raw funding rate (UI ann. % = `funding_rate × 100`) |
| `open_interest` | object | `long_open_interest` + `short_open_interest` (one-sided; pool OI × 2) |

**Not on this endpoint:** `price_change_7d_pct` / 7d % — use CoinGecko `coingecko_id` if needed.

Fixture reference (on `longshortoivol`): `Varibot/tests/fixtures/supported_assets_fields.json`.

---

## How the bot reads it

`Varibot/longshort_feed.py` → `parse_supported_assets_crypto_rows()`:

```python
chg24 = _parse_float_field(row, "price_change_percentage_24h", "price_change_24h_pct")
```

Snapshot field written: `price_change_24h_pct`.

`strategy/longshort.py` ranks long/short candidates on this field within volume buckets.

---

## Timing (live probe, 2026-06-23)

Universe: ~420 crypto perps after blacklist scrub, category `all`, Pro CoinGecko key present (CG only used for market cap backfill, **not** 24h %).

| Step | ~Duration |
|------|-----------|
| `GET /api/metadata/supported_assets` (includes 24h % for all tickers) | **0.2 s** |
| Full `build_longshort_listing_snapshot` (Vari + optional CG market cap) | **~4 s** |
| CoinGecko `enrich_market_cap` only | **~4–6 s** |

24h chg% itself is effectively free inside the Vari bulk fetch — no per-ticker CoinGecko calls.

---

## Contrast with this screener (today)

`scripts/build_screener_data.py` on this branch currently:

1. Fetches listings from **`GET …/metadata/stats`** (public client API).
2. Enriches **24h %** via **CoinGecko** `/api/v3/coins/markets` (`price_change_percentage=24h`).

That CG path is slower (~seconds per batch, rate limits) and duplicates data Vari already exposes on `supported_assets`.

**Possible screener improvement:** switch 24h chg% (and volume/OI/funding if needed) to `GET /api/metadata/supported_assets` when auth is available; keep CoinGecko only for fields Vari does not provide (e.g. 7d %, or market cap when missing).

---

## Quick probe (Varibot)

```bash
cd Varibot
python3 -c "
from dotenv import load_dotenv; load_dotenv('.env')
from variationalbot.config import load_config
from variationalbot.vari import VariAuth, VariClient, VariEndpoints
cfg = load_config()
ep = VariEndpoints(VariClient(base_url=cfg.base_url, auth=VariAuth(wallet_address=cfg.wallet_address, vr_token=cfg.vr_token)))
bulk = ep.get_supported_assets()
row = bulk['BTC'][0]
print('price_change_percentage_24h:', row.get('price_change_percentage_24h'))
"
```

Maintainer key dump: `scripts/probe_supported_assets.py` (on `longshortoivol`).
