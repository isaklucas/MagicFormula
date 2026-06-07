"""
Exporta lista filtrada de tickers do S&P 500 para JSON.
Exclui Financials e Real Estate (Magic Formula standard).
Usa tabela da Wikipedia para obter setor sem chamadas yfinance.
"""

import io
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

EXCLUDED_GICS = {"Financials", "Real Estate"}

OUT_PATH = Path("output/universe_tickers_us.json")


def get_sp500_tickers_filtered() -> list[str]:
    req = urllib.request.Request(SP500_URL, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8")

    tables = pd.read_html(io.StringIO(html))
    df = tables[0]

    # Wikipedia columns: Symbol, Security, GICS Sector, GICS Sub-Industry, ...
    sector_col = next((c for c in df.columns if "Sector" in str(c)), None)
    symbol_col = next((c for c in df.columns if "Symbol" in str(c)), "Symbol")

    tickers = []
    for _, row in df.iterrows():
        symbol = str(row[symbol_col]).replace(".", "-")
        sector = str(row[sector_col]) if sector_col else ""
        if sector not in EXCLUDED_GICS:
            tickers.append(symbol)

    return tickers


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print(f"[export_tickers_us] Buscando lista S&P 500...")
    tickers = get_sp500_tickers_filtered()
    print(f"[export_tickers_us] {len(tickers)} tickers após excluir {EXCLUDED_GICS}")

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(tickers, f)

    print(f"[export_tickers_us] Salvo: {OUT_PATH}")
