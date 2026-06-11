"""
yfinance-based fetcher for B3 FIIs (Fundos de Investimento Imobiliário).
Mirrors yf_fetcher.py architecture.

Flow: FIIsListadosB3.csv → {CODE}11.SA yfinance → SI fallback (missing PVP/DY) → 7-day cache
"""

import json
import math
import time
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

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "output" / "fii_yf_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_TTL = 7 * 24 * 3600  # 7 days
FII_CSV = DATA_DIR / "FIIsListadosB3.csv"

_SI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


# ─── Cache helpers ────────────────────────────────────────────────────────────

def _load_cache(key: str) -> dict | None:
    p = CACHE_DIR / f"{key}.json"
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
        with open(CACHE_DIR / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False)
    except Exception:
        pass


# ─── CSV loader ───────────────────────────────────────────────────────────────

def _load_b3_meta() -> dict[str, dict]:
    """
    Load FIIsListadosB3.csv → {CODE: {nome, full_name}}.
    Columns: Razão Social;Fundo;Código  (semicolon-separated, latin-1)
    Rows have trailing ';' → use index_col=False + positional access.
    """
    for enc in ("latin-1", "cp1252", "utf-8"):
        try:
            df = pd.read_csv(
                FII_CSV, sep=";", encoding=enc, dtype=str,
                header=0, index_col=False, on_bad_lines="skip",
            )
            break
        except Exception:
            continue
    else:
        print("[fii_yf_fetcher] Erro ao ler FIIsListadosB3.csv")
        return {}

    # Positional: col0=Razão Social, col1=Fundo, col2=Código (trailing ; may add col3=empty)
    cols = df.columns.tolist()
    if len(cols) < 3:
        print(f"[fii_yf_fetcher] CSV com colunas inesperadas: {cols}")
        return {}

    # Use column positions instead of names (header may have encoding artifacts)
    df.columns = ["RAZAO_SOCIAL", "FUNDO", "CODIGO"] + [f"_x{i}" for i in range(len(cols) - 3)]

    meta: dict[str, dict] = {}
    for _, row in df.iterrows():
        code = str(row["CODIGO"]).strip().upper()
        if not code or code in ("NAN", "CÓDIGO", "CODIGO", ""):
            continue
        meta[code] = {
            "nome": str(row["FUNDO"]).strip(),
            "full_name": str(row["RAZAO_SOCIAL"]).strip(),
        }

    return meta


# ─── Numeric helpers ──────────────────────────────────────────────────────────

def _f(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _pct(val) -> float | None:
    v = _f(val)
    return None if v is None else v * 100


def _has_sufficient_data(data: dict | None) -> bool:
    if not data:
        return False
    price = _f(data.get("PRECO"))
    pvp = _f(data.get("PVP"))
    dy = _f(data.get("DY"))
    return price is not None and price > 0 and (pvp is not None or dy is not None)


# ─── yfinance per-ticker ──────────────────────────────────────────────────────

def _fetch_yfinance_fii(ticker: str) -> dict | None:
    """
    Fetch FII metrics from yfinance. ticker = 'KNRI11' (no .SA suffix).
    Retries 4x on rate limit with exponential backoff (30/60/120/240s).
    Returns None if price unavailable or retries exhausted.
    """
    ticker_sa = f"{ticker}.SA"

    for attempt in range(4):
        time.sleep(2.0)
        try:
            t = yf.Ticker(ticker_sa)
            info = t.info or {}

            price = _f(
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )
            if price is None:
                return None

            avg_vol = _f(info.get("averageVolume") or info.get("averageDailyVolume10Day")) or 0.0
            liquidez = (avg_vol * price) if avg_vol > 0 else None
            patrimonio = _f(info.get("totalAssets")) or _f(info.get("marketCap"))

            categoria = (info.get("category") or info.get("fundFamily") or "").strip() or None

            # yfinance returns dividendYield already in % for BR FIIs (e.g. 8.63, not 0.0863)
            dy_raw = _f(info.get("dividendYield"))
            # trailingAnnualDividendYield is often 0 for FIIs; fall back to dividendYield
            dy_trail = _f(info.get("trailingAnnualDividendYield")) or dy_raw

            return {
                "TICKER": ticker,
                "PRECO": price,
                "DY": dy_raw,
                "DY_12M_MED": dy_trail,
                "PVP": _f(info.get("priceToBook")),
                "VPA": _f(info.get("bookValue")),
                "LIQUIDEZ": liquidez,
                "PATRIMONIO": patrimonio,
                "SEGMENTO": categoria,
                "_source": "yfinance",
            }

        except Exception as e:
            msg = str(e)
            if "404" in msg or "Not Found" in msg or "Quote not found" in msg:
                return None  # ticker não existe no yfinance — sem retry
            if "Too Many Requests" in msg or "Rate limited" in msg or "429" in msg:
                wait = 30 * (2 ** attempt)
                print(f"[fii_yf_fetcher] {ticker}: rate limit, aguardando {wait}s (tentativa {attempt + 1}/4)...")
                time.sleep(wait)
                continue
            return None

    print(f"[fii_yf_fetcher] {ticker}: rate limit persistente após 4 tentativas")
    return None


# ─── Status Invest fallback ───────────────────────────────────────────────────

_SI_FII_LABEL_MAP = {
    "P/VP": "PVP",
    "DY": "DY",
    "VPA": "VPA",
    "LIQUIDEZ": "LIQUIDEZ",
    "PATRIMÔNIO": "PATRIMONIO",
    "PATRIMONIO": "PATRIMONIO",
    "SEGMENTO": "SEGMENTO",
    "SETOR": "SEGMENTO",
}


def _parse_br_float(text: str) -> float | None:
    try:
        t = (
            text.strip()
            .replace("%", "").replace("R$", "").replace("x", "").replace("X", "")
            .replace("M", "").replace("B", "").strip()
        )
        if not t or t in ("-", "—", "N/A", ""):
            return None
        return float(t.replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _scrape_si_fii_metrics(ticker: str) -> dict:
    """Scrape FII indicator values from Status Invest individual FII page."""
    url = f"https://statusinvest.com.br/fundos-imobiliarios/{ticker.lower()}"
    try:
        with httpx.Client(headers=_SI_HEADERS, follow_redirects=True, timeout=15) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return {}
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return {}

    metrics: dict = {}

    # Primary: h3.title elements (SI uses title attr = metric name)
    for h3 in soup.find_all("h3", class_="title"):
        title_text = (h3.get("title") or h3.get_text(strip=True)).upper().strip()
        for si_label, col in _SI_FII_LABEL_MAP.items():
            if si_label.upper() in title_text and col not in metrics:
                container = h3.parent
                for _ in range(5):
                    if container is None:
                        break
                    strong = container.find("strong", class_=lambda c: c and "value" in c)
                    if strong:
                        raw = strong.get_text(strip=True)
                        if col == "SEGMENTO":
                            metrics[col] = raw
                        else:
                            val = _parse_br_float(raw)
                            if val is not None:
                                metrics[col] = val
                        break
                    container = container.parent
                break

    # Fallback: text search in .info divs
    for si_label, col in _SI_FII_LABEL_MAP.items():
        if col in metrics:
            continue
        for div in soup.find_all("div", class_=lambda c: c and "info" in c.split()):
            if si_label.upper() in div.get_text(separator=" ").upper():
                strong = div.find("strong")
                if strong:
                    raw = strong.get_text(strip=True)
                    if col == "SEGMENTO":
                        metrics[col] = raw
                    else:
                        val = _parse_br_float(raw)
                        if val is not None:
                            metrics[col] = val
                break

    return metrics


def _si_fallback_fii(ticker: str, data: dict) -> dict:
    """Enrich FII data from SI page when yfinance left PVP or DY as None."""
    needs = data.get("PVP") is None or data.get("DY") is None
    if not needs:
        return data

    si = _scrape_si_fii_metrics(ticker)
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


# ─── Main entry point ─────────────────────────────────────────────────────────

_REQUIRED_COLS = ["TICKER", "TIPO", "NOME", "SEGMENTO", "PRECO", "PVP", "DY", "DY_12M_MED", "VPA", "LIQUIDEZ", "PATRIMONIO"]


def fetch_all_fiis(force: bool = False) -> pd.DataFrame:
    """
    Load all FIIs from FIIsListadosB3.csv, fetch metrics via yfinance (+SI fallback),
    cache 7 days per ticker. Returns DataFrame with columns compatible with fii_main.py.

    P/VP fallback chain: yfinance → Fundamentus batch → Status Invest per ticker.
    Output columns: TICKER, TIPO, NOME, SEGMENTO, PRECO, PVP, DY, DY_12M_MED, VPA, LIQUIDEZ, PATRIMONIO
    """
    b3_meta = _load_b3_meta()
    if not b3_meta:
        raise RuntimeError("FIIsListadosB3.csv não encontrado ou vazio")

    codes = sorted(b3_meta.keys())
    print(f"[fii_yf_fetcher] {len(codes)} FIIs no CSV B3")

    # Preload Fundamentus batch (uses monthly cache — fast, no HTTP unless stale)
    fund_lookup: dict[str, dict] = {}
    try:
        import io as _io
        from contextlib import redirect_stdout as _redir
        from fii_si_scraper import fetch_all_si as _fetch_fund
        with _redir(_io.StringIO()):
            _df_fund = _fetch_fund()
        if not _df_fund.empty and "TICKER" in _df_fund.columns:
            for _, row in _df_fund.iterrows():
                t = str(row.get("TICKER", "")).strip().upper()
                if t:
                    fund_lookup[t] = row.to_dict()
            print(f"[fii_yf_fetcher] Fundamentus preloaded: {len(fund_lookup)} FIIs")
    except Exception as _e:
        print(f"[fii_yf_fetcher] Fundamentus preload falhou: {_e}")

    stats = {"cache": 0, "yfinance": 0, "fundamentus_pvp": 0, "si_fallback": 0, "sem_dados": 0}
    records: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ) as prog:
        task = prog.add_task("FII yfinance fetch...", total=len(codes))

        for code in codes:
            ticker = f"{code}11"
            meta = b3_meta[code]

            _from_cache = False
            data = None
            if not force:
                cached = _load_cache(ticker)
                if cached is not None:
                    data = cached
                    _from_cache = True
                    stats["cache"] += 1

            if data is None:
                data = _fetch_yfinance_fii(ticker)
                if data is None:
                    data = {"TICKER": ticker, "_source": "failed"}
                else:
                    stats["yfinance"] += 1

            # Patch PVP from Fundamentus if missing (works for both fresh and cached)
            if _f(data.get("PVP")) is None and ticker in fund_lookup:
                fund = fund_lookup[ticker]
                pvp = _f(fund.get("PVP"))
                if pvp is not None:
                    data = data.copy()
                    data["PVP"] = pvp
                    for col in ("DY", "DY_12M_MED", "VPA", "LIQUIDEZ", "PATRIMONIO"):
                        if _f(data.get(col)) is None:
                            v = _f(fund.get(col))
                            if v is not None:
                                data[col] = v
                    if data.get("SEGMENTO") in (None, "—", ""):
                        seg = fund.get("SEGMENTO")
                        if seg:
                            data["SEGMENTO"] = seg
                    src = data.get("_source", "unknown")
                    data["_source"] = f"{src}+Fundamentus"
                    stats["fundamentus_pvp"] += 1
                    _save_cache(ticker, data)

            # SI per-ticker fallback if PVP still missing
            if _f(data.get("PVP")) is None:
                enriched = _si_fallback_fii(ticker, data)
                if _f(enriched.get("PVP")) is not None:
                    data = enriched
                    stats["si_fallback"] += 1
                    _save_cache(ticker, data)
                elif not _has_sufficient_data(data):
                    stats["sem_dados"] += 1

            # Merge CSV metadata (don't overwrite yfinance/SI values)
            data.setdefault("TICKER", ticker)
            data.setdefault("NOME", meta["nome"])
            data.setdefault("TIPO", "FII")
            data.setdefault("SEGMENTO", "—")
            if not data.get("SEGMENTO"):
                data["SEGMENTO"] = "—"

            if not _from_cache:
                _save_cache(ticker, data)

            records.append(data)
            prog.advance(task)

    print(
        f"[fii_yf_fetcher] cache={stats['cache']} yfinance={stats['yfinance']} "
        f"fundamentus_pvp={stats['fundamentus_pvp']} si_fallback={stats['si_fallback']} "
        f"sem_dados={stats['sem_dados']}"
    )

    df = pd.DataFrame(records)

    for col in _REQUIRED_COLS:
        if col not in df.columns:
            df[col] = None

    # Drop rows with no usable price
    df = df[df["PRECO"].notna() & (df["PRECO"].apply(lambda v: _f(v) is not None and _f(v) > 0))].copy()
    df = df.reset_index(drop=True)

    print(f"[fii_yf_fetcher] {len(df)} FIIs com preço disponível")
    return df[_REQUIRED_COLS]
