#!/usr/bin/env python3
"""Fetch Vari listings + CoinGecko enrichment and write screener.data.json."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT_PATH = ROOT / "longshort-screener" / "public" / "screener.data.json"
BLACKLIST_PATH = HERE / "vari_blacklist.json"
ID_MAP_PATH = HERE / "coingecko_id_map.json"

VARI_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
CG_PUBLIC_BASE = "https://api.coingecko.com/api/v3"
CG_PRO_BASE = "https://pro-api.coingecko.com/api/v3"
EXCLUDE = {"BTC", "ETH"}
UNIVERSE_TOP_N = 200

# Bulk top-by-mcap pagination (pro: 250/page; public: 100/page).
CG_BULK_MAX_PAGES = int(os.environ.get("CG_BULK_MAX_PAGES", "25"))
CG_ID_BATCH = int(os.environ.get("CG_ID_BATCH_SIZE", "100"))
CG_SLEEP_PUBLIC_S = 2.0
CG_SLEEP_PRO_S = float(os.environ.get("CG_MIN_SLEEP_S", "0.25"))


def cg_request_config() -> tuple[str, dict[str, str], str]:
    """Return (markets_url, headers, key_type) for CoinGecko."""
    api_key = os.environ.get("COINGECKO_API_KEY", "").strip()
    key_type = os.environ.get("COINGECKO_API_KEY_TYPE", "pro").strip().lower()
    base = os.environ.get("CG_API_BASE", "").strip().rstrip("/")

    if not api_key:
        public_base = base or CG_PUBLIC_BASE
        return f"{public_base}/coins/markets", {}, "none"

    if not base:
        base = CG_PRO_BASE if key_type == "pro" else CG_PUBLIC_BASE

    markets_url = f"{base}/coins/markets"
    use_pro = key_type == "pro" or "pro-api.coingecko.com" in base
    if use_pro:
        return markets_url, {"x-cg-pro-api-key": api_key}, "pro"
    return markets_url, {"x-cg-demo-api-key": api_key}, "demo"


def cg_per_page(key_type: str) -> int:
    return 250 if key_type in ("pro", "demo") else 100


def cg_sleep_s(key_type: str) -> float:
    return CG_SLEEP_PRO_S if key_type in ("pro", "demo") else CG_SLEEP_PUBLIC_S


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_vari_listings() -> list[dict[str, Any]]:
    resp = requests.get(VARI_URL, timeout=60)
    resp.raise_for_status()
    return resp.json().get("listings", [])


def _cg_get(
    cg_url: str,
    headers: dict[str, str],
    params: dict[str, Any],
    *,
    key_type: str,
) -> list[dict[str, Any]]:
    last_resp: requests.Response | None = None
    sleep_s = cg_sleep_s(key_type)
    for attempt in range(8):
        resp = requests.get(cg_url, params=params, headers=headers, timeout=60)
        last_resp = resp
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            try:
                wait_s = float(retry_after) if retry_after else 5 + attempt * 3
            except (TypeError, ValueError):
                wait_s = 5 + attempt * 3
            time.sleep(max(wait_s, sleep_s))
            continue
        resp.raise_for_status()
        return resp.json() or []
    if last_resp is not None:
        last_resp.raise_for_status()
    return []


def fetch_cg_markets_bulk() -> tuple[list[dict[str, Any]], str, int]:
    """Paginate top coins by market cap, then match Vari tickers locally."""
    coins: list[dict[str, Any]] = []
    cg_url, headers, key_type = cg_request_config()
    per_page = cg_per_page(key_type)
    sleep_s = cg_sleep_s(key_type)
    failed_batches = 0

    for page in range(1, CG_BULK_MAX_PAGES + 1):
        try:
            batch = _cg_get(
                cg_url,
                headers,
                {
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": per_page,
                    "page": page,
                    "price_change_percentage": "24h",
                },
                key_type=key_type,
            )
        except requests.HTTPError:
            failed_batches += 1
            break

        coins.extend(batch)
        if len(batch) < per_page:
            break
        if page < CG_BULK_MAX_PAGES:
            time.sleep(sleep_s)

    return coins, key_type, failed_batches


def fetch_cg_markets_by_ids(ids: list[str], *, key_type: str) -> tuple[list[dict[str, Any]], int]:
    """Fallback: fetch explicit CoinGecko ids for tickers missing from bulk."""
    if not ids:
        return [], 0

    coins: list[dict[str, Any]] = []
    cg_url, headers, _ = cg_request_config()
    per_page = min(cg_per_page(key_type), CG_ID_BATCH)
    sleep_s = cg_sleep_s(key_type)
    failed_batches = 0
    id_batches = [ids[i : i + per_page] for i in range(0, len(ids), per_page)]

    for i, batch in enumerate(id_batches):
        try:
            coins.extend(
                _cg_get(
                    cg_url,
                    headers,
                    {
                        "vs_currency": "usd",
                        "ids": ",".join(batch),
                        "order": "market_cap_desc",
                        "per_page": len(batch),
                        "page": 1,
                        "price_change_percentage": "24h",
                    },
                    key_type=key_type,
                )
            )
        except requests.HTTPError:
            failed_batches += 1
            print(f"CoinGecko fallback 400/HTTP ({key_type}), skipping batch")
        if i < len(id_batches) - 1:
            time.sleep(sleep_s)

    return coins, failed_batches


def merge_coins(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for group in groups:
        for coin in group:
            cid = (coin.get("id") or "").lower()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append(coin)
    return out


def build_symbol_index(coins: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for coin in coins:
        sym = (coin.get("symbol") or "").lower()
        if not sym:
            continue
        prev = index.get(sym)
        if prev is None or (coin.get("market_cap") or 0) > (prev.get("market_cap") or 0):
            index[sym] = coin
    return index


def build_id_index(coins: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {(coin.get("id") or "").lower(): coin for coin in coins if coin.get("id")}


def lookup_coin(
    ticker: str,
    id_map: dict[str, str],
    sym_index: dict[str, dict[str, Any]],
    id_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    cg_id = id_map.get(ticker)
    if cg_id:
        coin = id_index.get(cg_id.lower())
        if coin:
            return coin
    return sym_index.get(ticker.lower())


def chg24_pct(coin: dict[str, Any] | None) -> float | None:
    if not coin:
        return None
    val = coin.get("price_change_percentage_24h_in_currency")
    if val is None:
        val = coin.get("price_change_percentage_24h")
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def main() -> None:
    blacklist = set(load_json(BLACKLIST_PATH)["blacklist"]) | EXCLUDE
    id_map: dict[str, str] = load_json(ID_MAP_PATH)

    listings = fetch_vari_listings()

    coins_bulk, key_type, bulk_failed = fetch_cg_markets_bulk()
    sym_index = build_symbol_index(coins_bulk)
    id_index = build_id_index(coins_bulk)

    vari_tickers: list[str] = []
    for it in listings:
        ticker = str(it.get("ticker", "")).upper()
        if ticker and ticker not in blacklist:
            vari_tickers.append(ticker)

    fallback_ids: list[str] = []
    for ticker in vari_tickers:
        coin = lookup_coin(ticker, id_map, sym_index, id_index)
        if chg24_pct(coin) is None:
            cg_id = id_map.get(ticker)
            if cg_id:
                fallback_ids.append(cg_id.lower())

    coins_fallback, fallback_failed = fetch_cg_markets_by_ids(
        sorted(set(fallback_ids)),
        key_type=key_type,
    )
    for coin in coins_fallback:
        sym = (coin.get("symbol") or "").lower()
        cid = (coin.get("id") or "").lower()
        if sym:
            prev = sym_index.get(sym)
            if prev is None or (coin.get("market_cap") or 0) > (prev.get("market_cap") or 0):
                sym_index[sym] = coin
        if cid:
            id_index[cid] = coin

    coins = merge_coins(coins_bulk, coins_fallback)
    failed_batches = bulk_failed + fallback_failed

    with_chg = 0
    rows: list[dict[str, Any]] = []
    for it in listings:
        ticker = str(it.get("ticker", "")).upper()
        if not ticker or ticker in blacklist:
            continue

        oi = it.get("open_interest") or {}
        try:
            oi_long = float(oi.get("long_open_interest") or 0)
            oi_short = float(oi.get("short_open_interest") or 0)
            oi_total = oi_long + oi_short
        except (TypeError, ValueError):
            oi_total = None

        try:
            vol_24h = float(it.get("volume_24h") or 0)
        except (TypeError, ValueError):
            vol_24h = 0.0

        coin = lookup_coin(ticker, id_map, sym_index, id_index)
        mcap = coin.get("market_cap") if coin else None
        chg = chg24_pct(coin)
        if chg is not None:
            with_chg += 1

        rows.append(
            {
                "ticker": ticker,
                "market_cap": mcap,
                "vol_24h": vol_24h,
                "oi": oi_total,
                "chg24_pct": chg,
            }
        )

    now = datetime.now(ZoneInfo("Asia/Singapore"))
    payload = {
        "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S SGT"),
        "universe_top_n": UNIVERSE_TOP_N,
        "blacklist": sorted(blacklist),
        "meta": {
            "cg_key_type": key_type,
            "cg_fetch_mode": "bulk_then_fallback",
            "cg_api_base": os.environ.get("CG_API_BASE", CG_PRO_BASE if key_type == "pro" else CG_PUBLIC_BASE),
            "cg_coins_fetched": len(coins),
            "cg_bulk_coins": len(coins_bulk),
            "cg_fallback_ids": len(set(fallback_ids)),
            "cg_failed_batches": failed_batches,
            "listings_with_chg24": with_chg,
        },
        "listings": rows,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {OUT_PATH} ({len(rows)} listings, "
        f"{with_chg} with 24h chg, bulk={len(coins_bulk)} fallback_ids={len(set(fallback_ids))}, key={key_type})"
    )


if __name__ == "__main__":
    main()
