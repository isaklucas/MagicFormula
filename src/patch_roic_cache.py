"""
Patches ROIC in today's sp500 cache using balance_sheet Invested Capital.
Runs in parallel — much faster than a full re-fetch.
"""

import json
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import yfinance as yf

warnings.filterwarnings("ignore")

CACHE_FILE = Path("output/sp500_cache") / f"{date.today()}.json"
WORKERS = 20


def fetch_roic(record: dict) -> dict:
    ticker = record["TICKER"]
    try:
        t = yf.Ticker(ticker)
        fin = t.financials
        bs = t.balance_sheet

        ebit_row = fin.loc["EBIT"].dropna() if "EBIT" in fin.index else None
        ic_row = bs.loc["Invested Capital"].dropna() if "Invested Capital" in bs.index else None

        ebit = float(ebit_row.iloc[0]) if ebit_row is not None and len(ebit_row) > 0 else None
        ic = float(ic_row.iloc[0]) if ic_row is not None and len(ic_row) > 0 else None

        if ebit and ic and ic > 0:
            roic = round(ebit * 0.75 / ic * 100, 2)
        else:
            roic = None

        return {"TICKER": ticker, "ROIC": roic}
    except Exception:
        return {"TICKER": ticker, "ROIC": None}


def main():
    if not CACHE_FILE.exists():
        print(f"Cache not found: {CACHE_FILE}")
        return

    with open(CACHE_FILE, encoding="utf-8") as f:
        records = json.load(f)

    print(f"Patching ROIC for {len(records)} tickers with {WORKERS} workers...")

    roic_map = {}
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_roic, r): r["TICKER"] for r in records}
        for fut in as_completed(futures):
            result = fut.result()
            roic_map[result["TICKER"]] = result["ROIC"]
            done += 1
            if done % 50 == 0:
                valid = sum(1 for v in roic_map.values() if v is not None)
                print(f"  {done}/{len(records)} — ROIC válido: {valid}")

    for rec in records:
        rec["ROIC"] = roic_map.get(rec["TICKER"], rec["ROIC"])

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)

    valid = sum(1 for r in records if r.get("ROIC") is not None)
    print(f"Done. {valid}/{len(records)} tickers now have ROIC.")
    print(f"Cache updated: {CACHE_FILE}")


if __name__ == "__main__":
    main()
