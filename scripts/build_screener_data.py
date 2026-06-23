#!/usr/bin/env python3
"""Fetch Vari supported_assets (FDV, 24h chg%, volume, OI) and write screener.data.json."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from curl_cffi.requests import Session

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT_PATH = ROOT / "longshort-screener" / "public" / "screener.data.json"
BLACKLIST_PATH = HERE / "vari_blacklist.json"

VARI_BASE_URL = os.getenv("VARI_BASE_URL", "https://omni.variational.io").rstrip("/")
EXCLUDE = {"BTC", "ETH"}
UNIVERSE_TOP_N = 200


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _http_proxies() -> dict[str, str] | None:
    proxy = (os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or "").strip()
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def _parse_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def fetch_supported_assets() -> dict[str, list[dict[str, Any]]]:
    session = Session(impersonate="chrome124")
    url = f"{VARI_BASE_URL}/api/metadata/supported_assets"
    resp = session.get(
        url,
        headers={
            "accept": "*/*",
            "origin": VARI_BASE_URL,
            "referer": f"{VARI_BASE_URL}/perpetual/BTC",
        },
        proxies=_http_proxies(),
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise TypeError("supported_assets response must be a dict")
    return data


def pick_crypto_perp_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if row.get("instrument_type") == "perpetual_future":
            return row
    return rows[0] if rows else None


def parse_asset_row(row: dict[str, Any]) -> dict[str, Any]:
    oi = row.get("open_interest") or {}
    oi_long = _parse_float(oi.get("long_open_interest")) or 0.0
    oi_short = _parse_float(oi.get("short_open_interest")) or 0.0

    return {
        "fdv": _parse_float(row.get("fdv")),
        "vol_24h": _parse_float(row.get("volume_24h")) or 0.0,
        "oi": oi_long + oi_short,
        "chg24_pct": _parse_float(
            row.get("price_change_percentage_24h") or row.get("price_change_24h_pct")
        ),
    }


def main() -> None:
    blacklist = set(load_json(BLACKLIST_PATH)["blacklist"]) | EXCLUDE
    bulk = fetch_supported_assets()

    rows: list[dict[str, Any]] = []
    with_chg = 0
    with_fdv = 0
    for ticker, asset_rows in bulk.items():
        sym = str(ticker).upper()
        if not sym or sym in blacklist:
            continue
        row = pick_crypto_perp_row(asset_rows if isinstance(asset_rows, list) else [])
        if not row:
            continue
        parsed = parse_asset_row(row)
        if parsed["chg24_pct"] is not None:
            with_chg += 1
        if parsed["fdv"] is not None:
            with_fdv += 1
        rows.append({"ticker": sym, **parsed})

    now = datetime.now(ZoneInfo("Asia/Singapore"))
    payload = {
        "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S SGT"),
        "universe_top_n": UNIVERSE_TOP_N,
        "blacklist": sorted(blacklist),
        "meta": {
            "data_source": "vari_supported_assets",
            "vari_base_url": VARI_BASE_URL,
            "listings_with_chg24": with_chg,
            "listings_with_fdv": with_fdv,
        },
        "listings": rows,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(rows)} listings, {with_chg} with 24h chg, {with_fdv} with FDV)")


if __name__ == "__main__":
    main()
