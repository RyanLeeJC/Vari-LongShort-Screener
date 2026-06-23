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
CG_ID_BATCH = 50
CG_SLEEP_S = 2.1


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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_vari_listings() -> list[dict[str, Any]]:
    resp = requests.get(VARI_URL, timeout=60)
    resp.raise_for_status()
    return resp.json().get("listings", [])


def fetch_cg_markets(*, ids: list[str]) -> tuple[list[dict[str, Any]], str, int]:
    coins: list[dict[str, Any]] = []
    cg_url, headers, key_type = cg_request_config()
    failed_batches = 0

    def _get(params: dict[str, Any]) -> list[dict[str, Any]]:
        nonlocal failed_batches
        last_resp: requests.Response | None = None
        for attempt in range(8):
            resp = requests.get(cg_url, params=params, headers=headers, timeout=60)
            last_resp = resp
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait_s = float(retry_after) if retry_after else 5 + attempt * 3
                except (TypeError, ValueError):
                    wait_s = 5 + attempt * 3
                time.sleep(max(wait_s, CG_SLEEP_S))
                continue
            if resp.status_code == 400:
                failed_batches += 1
                print(f"CoinGecko 400 ({key_type}), skipping batch: {params.get('ids')}")
                return []
            resp.raise_for_status()
            return resp.json() or []
        if last_resp is not None:
            last_resp.raise_for_status()
        return []

    id_batches = [ids[i : i + CG_ID_BATCH] for i in range(0, len(ids), CG_ID_BATCH)]

    for i, batch in enumerate(id_batches):
        coins.extend(
            _get(
                {
                    "vs_currency": "usd",
                    "ids": ",".join(batch),
                    "order": "market_cap_desc",
                    "per_page": CG_ID_BATCH,
                    "page": 1,
                    "price_change_percentage": "24h",
                }
            )
        )
        if i < len(id_batches) - 1:
            time.sleep(CG_SLEEP_S)

    return coins, key_type, failed_batches


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
    ids: list[str] = []
    for it in listings:
        ticker = str(it.get("ticker", "")).upper()
        if not ticker or ticker in blacklist:
            continue
        cg_id = id_map.get(ticker)
        if cg_id:
            ids.append(cg_id.lower())

    coins, key_type, failed_batches = fetch_cg_markets(ids=sorted(set(ids)))
    sym_index = build_symbol_index(coins)
    id_index = build_id_index(coins)

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

        cg_id = id_map.get(ticker)
        coin = id_index.get(cg_id.lower()) if cg_id else sym_index.get(ticker.lower())
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
            "cg_api_base": os.environ.get("CG_API_BASE", CG_PRO_BASE if key_type == "pro" else CG_PUBLIC_BASE),
            "cg_coins_fetched": len(coins),
            "cg_failed_batches": failed_batches,
            "listings_with_chg24": with_chg,
        },
        "listings": rows,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {OUT_PATH} ({len(rows)} listings, "
        f"{with_chg} with 24h chg, {len(coins)} CG coins, key={key_type})"
    )


if __name__ == "__main__":
    main()
