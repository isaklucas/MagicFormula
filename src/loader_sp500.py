"""
Carrega dados do S&P 500 via yfinance com cache diário.
"""

import json
import logging
import time
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

CACHE_DIR = Path("output/sp500_cache")
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def _get_sp500_tickers() -> list:
    try:
        tables = pd.read_html(SP500_URL)
        tickers = tables[0]["Symbol"].tolist()
        return [t.replace(".", "-") for t in tickers]
    except Exception as e:
        print(f"[loader_sp500] Erro ao buscar lista S&P 500: {e}")
        return []


def _cagr(series: list) -> float | None:
    """CAGR de uma série ordenada do mais antigo ao mais recente."""
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
        fin = t.financials  # colunas = datas (mais recente primeiro)

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
        total_assets = info.get("totalAssets")
        current_liab = info.get("currentLiabilities") or info.get("totalCurrentLiabilities")
        cash = info.get("cash") or info.get("totalCash") or 0
        total_debt = info.get("totalDebt") or 0
        mkt_cap = info.get("marketCap")
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        avg_vol = info.get("averageVolume") or info.get("averageDailyVolume10Day") or 0
        roe = info.get("returnOnEquity")
        sector = info.get("sector", "")

        if not ebit or not revenue:
            return None

        invested_capital = (total_assets or 0) - (current_liab or 0) - cash
        roic = round(ebit * 0.75 / invested_capital * 100, 2) if invested_capital > 0 else None
        ev_ebit = None
        ev = info.get("enterpriseValue")
        if ev and ebit and ebit != 0:
            ev_ebit = round(ev / ebit, 2)

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


def load_sp500(force_refresh: bool = False) -> list[dict]:
    """
    Carrega dados do S&P 500. Usa cache diário se disponível.
    Retorna lista de dicts com campos normalizados (mesmo schema do pipeline BR).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{date.today()}.json"

    if not force_refresh and cache_file.exists():
        print(f"[loader_sp500] Cache hit: {cache_file}")
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    tickers = _get_sp500_tickers()
    if not tickers:
        raise RuntimeError("Não foi possível obter lista do S&P 500")

    print(f"[loader_sp500] Buscando {len(tickers)} tickers via yfinance (pode demorar 10-15 min)...")
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

    print(f"[loader_sp500] Concluído: {len(results)} tickers com dados completos, {failed} falhas")

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    print(f"[loader_sp500] Cache salvo: {cache_file}")

    return results
