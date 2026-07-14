"""
Carrega dados do S&P 600 Small Cap via yfinance com cache diário.
Mesmo schema do pipeline US (loader_sp500.py) — universo diferente.
"""

import io
import json
import logging
import time
import urllib.request
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

CACHE_DIR = Path("output/smallcap_cache")
SP600_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def _get_sp600_tickers() -> list:
    try:
        req = urllib.request.Request(SP600_URL, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8")
        tables = pd.read_html(io.StringIO(html))
        df = tables[0]
        symbol_col = next((c for c in df.columns if "Symbol" in str(c) or "Ticker" in str(c)), df.columns[0])
        tickers = df[symbol_col].tolist()
        return [str(t).replace(".", "-") for t in tickers]
    except Exception as e:
        print(f"[loader_smallcap] Erro ao buscar lista S&P 600: {e}")
        return []


def _cagr(series: list) -> float | None:
    clean = [v for v in series if v and v == v and v != 0]
    if len(clean) < 2:
        return None
    start, end = clean[0], clean[-1]
    if start <= 0 or end <= 0:
        return None
    n = len(clean) - 1
    return round(((end / start) ** (1 / n) - 1) * 100, 2)


def _fetch_ticker(ticker: str) -> dict | None:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        fin = t.financials

        def _row(label):
            try:
                row = fin.loc[label]
                return row.dropna().tolist()
            except Exception:
                return []

        ebit_series = _row("EBIT")
        rev_series = _row("Total Revenue")
        ni_series = _row("Net Income")

        ebit = ebit_series[0] if ebit_series else None
        revenue = rev_series[0] if rev_series else None
        total_debt = info.get("totalDebt") or 0
        cash = info.get("totalCash") or 0
        mkt_cap = info.get("marketCap")
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        avg_vol = info.get("averageVolume") or info.get("averageDailyVolume10Day") or 0
        roe = info.get("returnOnEquity")
        sector = info.get("sector", "")

        if not ebit or not revenue:
            return None

        # Capital investido = patrimonio liquido + divida liquida. A linha "Invested
        # Capital" do yfinance usa divida BRUTA e ignora o caixa, o que infla o capital
        # de empresas cheias de caixa e corta o ROIC pela metade. Greenblatt exclui caixa
        # em excesso. So usa a linha crua se faltar o PL.
        equity = None
        invested_capital = None
        try:
            bs = t.balance_sheet
            for label in ("Stockholders Equity", "Total Equity Gross Minority Interest"):
                if label in bs.index:
                    eq_row = bs.loc[label].dropna()
                    if len(eq_row) > 0:
                        equity = float(eq_row.iloc[0])
                        break
            if equity is not None:
                invested_capital = equity + (total_debt - cash)
            elif "Invested Capital" in bs.index:
                ic_row = bs.loc["Invested Capital"].dropna()
                invested_capital = float(ic_row.iloc[0]) if len(ic_row) > 0 else None
        except Exception:
            invested_capital = None

        # PL negativo: empresa tecnicamente insolvente, fora da Magic Formula.
        if equity is not None and equity <= 0:
            return None

        roic = round(ebit * 0.75 / invested_capital * 100, 2) if invested_capital and invested_capital > 0 else None
        ev = info.get("enterpriseValue")
        ev_ebit = round(ev / ebit, 2) if ev and ebit and ebit != 0 else None
        margem_ebit = round(ebit / revenue * 100, 2) if revenue else None
        div_ebit = round((total_debt - cash) / ebit, 2) if ebit else None
        cagr_rev = _cagr(list(reversed(rev_series[:5])))
        cagr_ni = _cagr(list(reversed(ni_series[:5])))
        liq_diaria = round(avg_vol * price, 2) if avg_vol and price else None

        return {
            "TICKER": ticker,
            "EV/EBIT": ev_ebit,
            "ROIC": roic,
            "MARGEM EBIT": margem_ebit,
            "ROE": round(roe * 100, 2) if roe else None,
            "DIVIDA LIQUIDA / EBIT": div_ebit,
            "CAGR RECEITAS 5 ANOS": cagr_rev,
            "CAGR LUCROS 5 ANOS": cagr_ni,
            "LIQUIDEZ MEDIA DIARIA": liq_diaria,
            "VALOR DE MERCADO": mkt_cap,
            "PRECO": price,
            "setor": sector,
            "moeda": "USD",
        }
    except Exception:
        return None


def load_smallcap(force_refresh: bool = False) -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{date.today()}.json"

    if not force_refresh and cache_file.exists():
        print(f"[loader_smallcap] Cache hit: {cache_file}")
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    tickers = _get_sp600_tickers()
    if not tickers:
        raise RuntimeError("Não foi possível obter lista do S&P 600")

    print(f"[loader_smallcap] Buscando {len(tickers)} tickers S&P 600 via yfinance...")
    results = []
    failed = 0
    for i, ticker in enumerate(tickers, 1):
        rec = _fetch_ticker(ticker)
        if rec:
            results.append(rec)
        else:
            failed += 1
        if i % 50 == 0:
            pct = i / len(tickers) * 100
            print(f"  {i}/{len(tickers)} ({pct:.0f}%) — OK: {len(results)} | Falhas: {failed}")
            time.sleep(0.5)

    print(f"[loader_smallcap] Concluído: {len(results)} tickers com dados, {failed} falhas")

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    print(f"[loader_smallcap] Cache salvo: {cache_file}")

    return results
