"""
yfinance-based fetcher for B3 stocks.
Replaces si_fetcher.py as primary data source.

Flow: xlsx tickers → expand suffixes → yfinance → SI fallback (missing EV/EBIT/ROIC) → 30-day cache
"""

import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "output" / "mf_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_TTL = 30 * 24 * 3600  # 30 days
SUFFIXES = ["3", "4", "11", "5", "6"]
TAX_RATE = 0.34  # Brazil corporate tax

_SI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

_NUMERIC_COLS = [
    "PRECO", "DY", "P/L", "P/VP", "P/ATIVOS", "MARGEM BRUTA", "MARGEM EBIT",
    "MARG. LIQUIDA", "P/EBIT", "EV/EBIT", "DIVIDA LIQUIDA / EBIT",
    "DIV. LIQ. / PATRI.", "PSR", "P/CAP. GIRO", "P. AT CIR. LIQ.",
    "LIQ. CORRENTE", "ROE", "ROA", "ROIC", "PATRIMONIO / ATIVOS",
    "PASSIVOS / ATIVOS", "GIRO ATIVOS", "CAGR RECEITAS 5 ANOS",
    "CAGR LUCROS 5 ANOS", "LIQUIDEZ MEDIA DIARIA", "VPA", "LPA",
    "PEG Ratio", "VALOR DE MERCADO",
]


# ─── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key_to_path(key: str) -> Path:
    safe = key.replace("/", "_").replace(".", "_").replace(" ", "_")
    return CACHE_DIR / f"{safe}.json"


def _load_cache(key: str) -> dict | None:
    p = _cache_key_to_path(key)
    if not p.exists():
        return None
    if (time.time() - p.stat().st_mtime) > CACHE_TTL:
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(key: str, data: dict) -> None:
    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    clean = {k: _clean(v) for k, v in data.items()}
    try:
        with open(_cache_key_to_path(key), "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False)
    except Exception:
        pass


# ─── xlsx loader ──────────────────────────────────────────────────────────────

def load_b3_tickers() -> pd.DataFrame:
    """
    Load B3 companies from EmpresasB3Porsetor.xlsx.
    The file has a split header (rows 1-2) and data from row 3 onward.
    SETOR is only filled on first row of each sector group (forward-filled here).
    """
    path = DATA_DIR / "EmpresasB3Porsetor.xlsx"
    raw = pd.read_excel(path, engine="openpyxl", header=None)

    # Columns: 0=empty, 1=SETOR, 2=SUBSETOR, 3=SEGMENTO, 4=EMISSOR, 5=CÓDIGO, 6=SEG_NEG
    raw.columns = ["_idx", "SETOR", "SUBSETOR", "SEGMENTO", "EMISSOR", "CÓDIGO", "SEG_NEG"]

    # Data rows start at index 3 (rows 0-2 are headers/empty)
    df = raw.iloc[3:].copy().reset_index(drop=True)
    df = df.drop(columns=["_idx", "SEG_NEG"])

    # Forward-fill SETOR (only populated on first row of each sector group)
    df["SETOR"] = df["SETOR"].ffill()

    df["CÓDIGO"] = df["CÓDIGO"].astype(str).str.strip().str.upper()
    # Keep only valid B3 base codes (3-5 uppercase letters)
    df = df[df["CÓDIGO"].str.match(r"^[A-Z]{3,5}$")].copy()
    df = df.drop_duplicates(subset="CÓDIGO").reset_index(drop=True)

    return df


# ─── Universe expansion ───────────────────────────────────────────────────────

def expand_tickers(base_codes: list[str]) -> dict[str, list[str]]:
    """
    Discover which ticker class variants (3/4/11/5/6) exist for each base code.
    Returns {base_code: [valid_tickers_without_SA]}.
    Result cached 30 days.
    """
    cached = _load_cache("_universe")
    if cached is not None:
        total = sum(len(v) for v in cached.values())
        print(f"[yf_fetcher] Universe cache hit: {total} tickers de {len(cached)} empresas")
        return cached

    print(f"[yf_fetcher] Descobrindo tickers: {len(base_codes)} empresas × {len(SUFFIXES)} sufixos...")
    all_sa = [f"{base}{suf}.SA" for base in base_codes for suf in SUFFIXES]
    print(f"[yf_fetcher] Download batch de {len(all_sa)} candidatos via yf.download...")

    valid_sa: set[str] = set()

    try:
        data = yf.download(
            tickers=all_sa,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="ticker",
        )
        if not data.empty and isinstance(data.columns, pd.MultiIndex):
            top_level = data.columns.get_level_values(0).unique()
            for ticker_sa in all_sa:
                if ticker_sa in top_level:
                    try:
                        close = data[ticker_sa]["Close"].dropna()
                        if len(close) > 0:
                            valid_sa.add(ticker_sa)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[yf_fetcher] yf.download erro: {e}")

    if not valid_sa:
        print("[yf_fetcher] Fallback: validação individual (pode demorar ~5 min)...")
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn()) as prog:
            task = prog.add_task("Validando...", total=len(all_sa))
            for ticker_sa in all_sa:
                try:
                    p = yf.Ticker(ticker_sa).fast_info.last_price
                    if p and float(p) > 0:
                        valid_sa.add(ticker_sa)
                    time.sleep(0.04)
                except Exception:
                    pass
                prog.advance(task)

    universe: dict[str, list[str]] = {}
    for base in base_codes:
        valid = [f"{base}{suf}" for suf in SUFFIXES if f"{base}{suf}.SA" in valid_sa]
        if valid:
            universe[base] = valid

    total = sum(len(v) for v in universe.values())
    print(f"[yf_fetcher] {total} tickers válidos de {len(universe)} empresas")
    _save_cache("_universe", universe)
    return universe


# ─── Metric helpers ────────────────────────────────────────────────────────────

def _f(val) -> float | None:
    """Cast to float, return None for missing/NaN/inf."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _pct(val) -> float | None:
    """Convert 0-1 ratio to percentage. None if missing."""
    v = _f(val)
    return None if v is None else v * 100


def _get_ebit(t: yf.Ticker) -> float | None:
    try:
        fin = t.financials
        if fin is None or fin.empty:
            return None
        for label in ("EBIT", "Operating Income", "Total Operating Income", "Operating Income Or Loss"):
            if label in fin.index:
                v = _f(fin.loc[label].iloc[0])
                if v is not None and v != 0:
                    return v
    except Exception:
        pass
    return None


def _get_balance(t: yf.Ticker) -> tuple[float, float, float]:
    """Returns (total_debt, cash, equity). 0.0 if unavailable."""
    debt, cash, equity = 0.0, 0.0, 0.0
    try:
        bal = t.balance_sheet
        if bal is None or bal.empty:
            return debt, cash, equity
        for label in ("Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"):
            if label in bal.index:
                v = _f(bal.loc[label].iloc[0])
                if v is not None:
                    debt = v
                    break
        for label in ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"):
            if label in bal.index:
                v = _f(bal.loc[label].iloc[0])
                if v is not None:
                    cash = v
                    break
        for label in ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"):
            if label in bal.index:
                v = _f(bal.loc[label].iloc[0])
                if v is not None:
                    equity = v
                    break
    except Exception:
        pass
    return debt, cash, equity


# ─── yfinance per-ticker fetcher ───────────────────────────────────────────────

def fetch_yfinance(ticker: str) -> dict | None:
    """
    Fetch all Magic Formula metrics for a single ticker (no .SA suffix).
    Retries up to 4x on rate limit (30/60/120/240s backoff).
    Returns None if price unavailable or all retries exhausted.
    """
    ticker_sa = f"{ticker}.SA"

    for attempt in range(4):
        time.sleep(2.0)  # base rate-limit guard between every call
        try:
            t = yf.Ticker(ticker_sa)
            info = t.info or {}

            price = _f(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
            if price is None:
                return None

            market_cap = _f(info.get("marketCap"))
            ev = _f(info.get("enterpriseValue"))

            ebit = _get_ebit(t)
            debt, cash, equity = _get_balance(t)
            net_debt = debt - cash
            invested_capital = equity + net_debt

            ev_ebit = (ev / ebit) if (ev is not None and ebit and ebit > 0) else None
            roic = ((ebit * (1 - TAX_RATE) / invested_capital) * 100) if (ebit and invested_capital > 0) else None
            div_liq_ebit = (net_debt / ebit) if (ebit and ebit != 0) else None
            p_ebit = (market_cap / ebit) if (market_cap is not None and ebit and ebit > 0) else None

            avg_vol = _f(info.get("averageVolume") or info.get("averageDailyVolume10Day")) or 0.0
            liquidez = (avg_vol * price) if avg_vol > 0 else None

            ebit_margin = None
            if ebit:
                rev = _f(info.get("totalRevenue"))
                if rev and rev > 0:
                    ebit_margin = (ebit / rev) * 100

            shares = _f(info.get("sharesOutstanding")) or 0.0
            vpa = (equity / shares) if (shares > 0 and equity) else None

            return {
                "TICKER": ticker,
                "PRECO": price,
                "DY": _pct(info.get("dividendYield")),
                "P/L": _f(info.get("trailingPE") or info.get("forwardPE")),
                "P/VP": _f(info.get("priceToBook")),
                "P/ATIVOS": None,
                "MARGEM BRUTA": _pct(info.get("grossMargins")),
                "MARGEM EBIT": ebit_margin,
                "MARG. LIQUIDA": _pct(info.get("profitMargins")),
                "P/EBIT": p_ebit,
                "EV/EBIT": ev_ebit,
                "DIVIDA LIQUIDA / EBIT": div_liq_ebit,
                "DIV. LIQ. / PATRI.": None,
                "PSR": _f(info.get("priceToSalesTrailing12Months")),
                "P/CAP. GIRO": None,
                "P. AT CIR. LIQ.": None,
                "LIQ. CORRENTE": _f(info.get("currentRatio")),
                "ROE": _pct(info.get("returnOnEquity")),
                "ROA": _pct(info.get("returnOnAssets")),
                "ROIC": roic,
                "PATRIMONIO / ATIVOS": None,
                "PASSIVOS / ATIVOS": None,
                "GIRO ATIVOS": None,
                "CAGR RECEITAS 5 ANOS": None,
                "CAGR LUCROS 5 ANOS": None,
                "LIQUIDEZ MEDIA DIARIA": liquidez,
                "VPA": vpa,
                "LPA": _f(info.get("trailingEps")),
                "PEG Ratio": _f(info.get("pegRatio")),
                "VALOR DE MERCADO": market_cap,
                "_source": "yfinance",
            }

        except Exception as e:
            msg = str(e)
            if "Too Many Requests" in msg or "Rate limited" in msg or "429" in msg:
                wait = 30 * (2 ** attempt)  # 30s, 60s, 120s, 240s
                print(f"[yf_fetcher] {ticker}: rate limit, aguardando {wait}s (tentativa {attempt + 1}/4)...")
                time.sleep(wait)
                continue
            print(f"[yf_fetcher] {ticker}: erro: {e}")
            return None

    print(f"[yf_fetcher] {ticker}: rate limit persistente após 4 tentativas")
    return None


# ─── Status Invest fallback ────────────────────────────────────────────────────

def _parse_br_float(text: str) -> float | None:
    try:
        t = text.strip().replace("%", "").replace("R$", "").replace("x", "").replace("X", "").strip()
        if not t or t in ("-", "—", "N/A", ""):
            return None
        return float(t.replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


_SI_LABEL_MAP = {
    "EV/EBIT": "EV/EBIT",
    "ROIC": "ROIC",
    "P/EBIT": "P/EBIT",
    "P/L": "P/L",
    "P/VP": "P/VP",
    "ROE": "ROE",
    "ROA": "ROA",
    "DY": "DY",
    "DIV. LÍQUIDA / EBIT": "DIVIDA LIQUIDA / EBIT",
    "DÍVIDA LÍQUIDA / EBIT": "DIVIDA LIQUIDA / EBIT",
    "DIV. LIQ. / EBIT": "DIVIDA LIQUIDA / EBIT",
    "LIQ. MÉD. DIÁRIA": "LIQUIDEZ MEDIA DIARIA",
    "LIQUIDEZ MÉD. DIÁRIA": "LIQUIDEZ MEDIA DIARIA",
}


def _scrape_si_metrics(ticker: str) -> dict[str, float]:
    """Scrape indicator values from Status Invest individual ticker page."""
    url = f"https://statusinvest.com.br/acoes/{ticker.lower()}"
    try:
        with httpx.Client(headers=_SI_HEADERS, follow_redirects=True, timeout=15) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return {}
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return {}

    metrics: dict[str, float] = {}

    # Strategy: find h3.title elements (SI uses title attr = metric name)
    for h3 in soup.find_all("h3", class_="title"):
        title_text = (h3.get("title") or h3.get_text(strip=True)).upper().strip()
        for si_label, col in _SI_LABEL_MAP.items():
            if si_label.upper() in title_text and col not in metrics:
                # Search for strong.value in the parent container
                container = h3.parent
                for _ in range(5):
                    if container is None:
                        break
                    strong = container.find("strong", class_=lambda c: c and "value" in c)
                    if strong:
                        val = _parse_br_float(strong.get_text(strip=True))
                        if val is not None:
                            metrics[col] = val
                        break
                    container = container.parent
                break

    # Fallback: text search in .info divs
    if "EV/EBIT" not in metrics or "ROIC" not in metrics:
        for div in soup.find_all("div", class_=lambda c: c and "info" in c.split()):
            div_text = div.get_text(separator=" ").upper()
            for si_label, col in _SI_LABEL_MAP.items():
                if col not in metrics and si_label.upper() in div_text:
                    strong = div.find("strong")
                    if strong:
                        val = _parse_br_float(strong.get_text(strip=True))
                        if val is not None:
                            metrics[col] = val

    return metrics


def _si_fallback(ticker: str, data: dict) -> dict:
    """
    Enrich data with metrics from SI individual page when yfinance left them None.
    Only calls SI if EV/EBIT or ROIC is missing.
    """
    needs = data.get("EV/EBIT") is None or data.get("ROIC") is None
    if not needs:
        return data

    si = _scrape_si_metrics(ticker)
    if not si:
        return data

    result = data.copy()
    changed = False
    for col, val in si.items():
        if result.get(col) is None and val is not None:
            result[col] = val
            changed = True

    if changed:
        result["_source"] = "yfinance+SI"

    time.sleep(0.8)
    return result


# ─── Per-ticker fetch with cache + fallback ────────────────────────────────────

def _fetch_and_cache(ticker: str) -> tuple[str, dict | None, str]:
    """Fetch yfinance (com retry interno) → SI fallback → save cache."""
    data = fetch_yfinance(ticker)
    if data is None:
        return ticker, None, "failed"

    data = _si_fallback(ticker, data)
    _save_cache(ticker, data)

    src = data.get("_source", "yfinance")
    status = "si_fallback" if "SI" in src else "yfinance"
    return ticker, data, status


# ─── Main entry point ──────────────────────────────────────────────────────────

def fetch_all_stocks() -> pd.DataFrame:
    """
    Load all B3 stocks from xlsx, fetch metrics via yfinance (+ SI fallback),
    cache 30 days, return DataFrame compatible with the MF pipeline.
    """
    # 1. Load xlsx
    b3_df = load_b3_tickers()
    base_codes = b3_df["CÓDIGO"].tolist()
    setor_map: dict[str, str] = {}
    if "SETOR" in b3_df.columns:
        setor_map = dict(zip(b3_df["CÓDIGO"], b3_df["SETOR"].fillna("Desconhecido")))
    print(f"[yf_fetcher] {len(base_codes)} empresas no xlsx")

    # 2. Expand to full tickers
    universe = expand_tickers(base_codes)
    all_tickers = [t for tickers in universe.values() for t in tickers]
    print(f"[yf_fetcher] {len(all_tickers)} tickers para processar")

    # 3. Fetch metrics
    rows: list[dict] = []
    stats = {"cache": 0, "yfinance": 0, "si_fallback": 0, "failed": 0}
    to_fetch: list[str] = []

    # Pre-collect cache hits (avoids thread overhead for already-cached tickers)
    for ticker in all_tickers:
        cached = _load_cache(ticker)
        if cached is not None:
            rows.append(cached)
            stats["cache"] += 1
        else:
            to_fetch.append(ticker)

    if stats["cache"]:
        print(f"[yf_fetcher] Cache hits: {stats['cache']} / {len(all_tickers)}")

    if to_fetch:
        print(f"[yf_fetcher] Buscando {len(to_fetch)} tickers (sequencial, 2s/ticker)...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("yfinance...", total=len(to_fetch))
            with ThreadPoolExecutor(max_workers=1) as executor:
                futures = {executor.submit(_fetch_and_cache, t): t for t in to_fetch}
                for future in as_completed(futures):
                    ticker, data, status = future.result()
                    if data is not None:
                        rows.append(data)
                        stats[status] += 1
                    else:
                        stats["failed"] += 1
                    progress.advance(task)

    print(
        f"[yf_fetcher] Cache: {stats['cache']} | yfinance: {stats['yfinance']} | "
        f"SI fallback: {stats['si_fallback']} | Falhas: {stats['failed']}"
    )

    if not rows:
        raise RuntimeError("Nenhum dado coletado. Verifique a conexão.")

    # 4. Build DataFrame
    df = pd.DataFrame(rows)
    df["TICKER"] = df["TICKER"].astype(str).str.strip().str.upper()

    # 5. Add setor from xlsx
    if setor_map:
        def _get_setor(ticker: str) -> str:
            base = ticker.rstrip("0123456789")
            return setor_map.get(base, "Desconhecido")
        df["SETOR"] = df["TICKER"].apply(_get_setor)

    # 6. Enforce numeric dtypes
    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.drop(columns=["_source"], errors="ignore")
    df = df.drop_duplicates(subset=["TICKER"], keep="first").reset_index(drop=True)

    ev_ok = df["EV/EBIT"].notna().sum()
    roic_ok = df["ROIC"].notna().sum()
    print(f"[yf_fetcher] {len(df)} ações | EV/EBIT: {ev_ok} | ROIC: {roic_ok}")
    return df


if __name__ == "__main__":
    df = fetch_all_stocks()
    cols = ["TICKER", "PRECO", "EV/EBIT", "ROIC", "LIQUIDEZ MEDIA DIARIA", "VALOR DE MERCADO"]
    print(df[cols].dropna(subset=["EV/EBIT", "ROIC"]).head(30).to_string())
