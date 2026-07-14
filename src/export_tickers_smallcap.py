"""
Exporta lista filtrada de tickers do S&P 600 Small Cap para JSON.
Exclui Financials e Real Estate (Magic Formula standard).
"""

import io
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

SP600_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

EXCLUDED_GICS = {"Financials", "Real Estate"}

OUT_PATH = Path("output/universe_tickers_smallcap.json")
SECTORS_PATH = Path("output/universe_sectors_smallcap.json")


def get_sp600_tickers_filtered() -> tuple[list[str], dict[str, str]]:
    """Retorna (tickers, mapa ticker->setor GICS). O setor sai da mesma tabela, de graça."""
    req = urllib.request.Request(SP600_URL, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8")

    tables = pd.read_html(io.StringIO(html))
    df = tables[0]

    sector_col = next((c for c in df.columns if "Sector" in str(c)), None)
    symbol_col = next((c for c in df.columns if "Symbol" in str(c) or "Ticker" in str(c)), df.columns[0])

    tickers = []
    setores: dict[str, str] = {}
    for _, row in df.iterrows():
        symbol = str(row[symbol_col]).replace(".", "-")
        sector = str(row[sector_col]) if sector_col else ""
        if sector not in EXCLUDED_GICS:
            tickers.append(symbol)
            setores[symbol] = sector or "Desconhecido"

    return tickers, setores


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("[export_tickers_smallcap] Buscando lista S&P 600 Small Cap...")
    tickers, setores = get_sp600_tickers_filtered()
    print(f"[export_tickers_smallcap] {len(tickers)} tickers após excluir {EXCLUDED_GICS}")

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(tickers, f)

    with open(SECTORS_PATH, "w", encoding="utf-8") as f:
        json.dump(setores, f, ensure_ascii=False, indent=2)

    print(f"[export_tickers_smallcap] Salvo: {OUT_PATH}")
    print(f"[export_tickers_smallcap] Setores salvos: {SECTORS_PATH}")
