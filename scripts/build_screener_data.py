#!/usr/bin/env python3
"""Fetch Vari listings + CoinGecko enrichment and write screener.data.json."""

from __future__ import annotations

import json
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
CG_URL = "https://api.coingecko.com/api/v3/coins/markets"
EXCLUDE = {"BTC", "ETH"}
UNIVERSE_TOP_N = 200
CG_BATCH = 50
CG_SLEEP_S = 2.1


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_vari_listings() -> list[dict[str, Any]]:
    resp = requests.get(VARI_URL, timeout=60)
    resp.raise_for_status()
    return resp.json().get("listings", [])


def fetch_cg_markets(*, symbols: list[str], ids: list[str]) -> list[dict[str, Any]]:
    coins: list[dict[str, Any]] = []
    headers: dict[str, str] = {}
    api_key = __import__("os").environ.get("COINGECKO_API_KEY", "").strip()
    if api_key:
        headers["x-cg-pro-api-key"] = api_key

    def _get(params: dict[str, Any]) -> list[dict[str, Any]]:
        for attempt in range(6):
            resp = requests.get(CG_URL, params=params, headers=headers, timeout=60)
            if resp.status_code == 429:
                time.sleep(5 + attempt * 2)
                continue
            resp.raise_for_status()
            return resp.json() or []
        resp.raise_for_status()
        return []

    sym_batches = [symbols[i : i + CG_BATCH] for i in range(0, len(symbols), CG_BATCH)]
    id_batches = [ids[i : i + 100] for i in range(0, len(ids), 100)]

    for i, batch in enumerate(sym_batches):
        coins.extend(
            _get(
                {
                    "vs_currency": "usd",
                    "symbols": ",".join(batch),
                    "include_tokens": "top",
                    "order": "market_cap_desc",
                    "per_page": 100,
                    "page": 1,
                    "price_change_percentage": "24h",
                }
            )
        )
        if i < len(sym_batches) - 1:
            time.sleep(CG_SLEEP_S)

    for i, batch in enumerate(id_batches):
        coins.extend(
            _get(
                {
                    "vs_currency": "usd",
                    "ids": ",".join(batch),
                    "order": "market_cap_desc",
                    "per_page": 100,
                    "page": 1,
                    "price_change_percentage": "24h",
                }
            )
        )
        if i < len(id_batches) - 1:
            time.sleep(CG_SLEEP_S)

    return coins


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
    symbols: list[str] = []
    ids: list[str] = []
    for it in listings:
        ticker = str(it.get("ticker", "")).upper()
        if not ticker or ticker in blacklist:
            continue
        cg_id = id_map.get(ticker)
        if cg_id:
            ids.append(cg_id.lower())
        else:
            symbols.append(ticker.lower())

    coins = fetch_cg_markets(symbols=sorted(set(symbols)), ids=sorted(set(ids)))
    sym_index = build_symbol_index(coins)
    id_index = build_id_index(coins)

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
        "listings": rows,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(rows)} listings)")


if __name__ == "__main__":
    main()
