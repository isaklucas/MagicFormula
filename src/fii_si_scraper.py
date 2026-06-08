"""
Fundamentus — scraper de FIIs e FIAgros com cache mensal JSON.
Cache em data/fii_cache/YYYY_MM.json e YYYY_MM_fiagro.json.

Colunas retornadas: TICKER, TIPO, NOME, SEGMENTO, PRECO, PVP, DY,
                    DY_12M_MED, VPA, LIQUIDEZ, PATRIMONIO
"""

import json
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import date

ROOT      = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "fii_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_FII_URL    = "https://www.fundamentus.com.br/fii_resultado.php"
_FIAGRO_URL = "https://www.fundamentus.com.br/fiagro_resultado.php"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def _parse_br_number(s: str) -> float | None:
    """Converte '1.234,56' ou '12,34%' para float."""
    if not s or s.strip() in ("-", ""):
        return None
    try:
        cleaned = (
            str(s)
            .replace(".", "")
            .replace(",", ".")
            .replace("%", "")
            .strip()
        )
        v = float(cleaned)
        return v if v != 0.0 else None
    except (ValueError, TypeError):
        return None


def _scrape_url(url: str, tipo: str) -> pd.DataFrame:
    """Scrapa tabela tabelaResultado de qualquer página Fundamentus."""
    label = tipo
    print(f"[fii_si_scraper] Fundamentus {label}...", end=" ", flush=True)
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=30) as c:
        r = c.get(url)
        r.raise_for_status()

    soup = BeautifulSoup(r.content, "html.parser", from_encoding="utf-8")
    tbl  = soup.find("table", id="tabelaResultado")
    if tbl is None:
        raise RuntimeError(f"Tabela 'tabelaResultado' não encontrada em {url}")

    all_rows = tbl.find_all("tr")
    print(f"{len(all_rows) - 1} fundos")

    rows = []
    for tr in all_rows[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 6:
            continue

        # colunas: Papel, Segmento, Cotação, FFO Yield, Dividend Yield, P/VP,
        #          Valor de Mercado, Liquidez, ...
        ticker = cells[0].strip().upper()
        if not (len(ticker) >= 5 and ticker.endswith("11") and ticker[:4].isalpha()):
            continue

        preco   = _parse_br_number(cells[2])
        dy      = _parse_br_number(cells[4])   # Dividend Yield %
        pvp     = _parse_br_number(cells[5])
        patrim  = _parse_br_number(cells[6]) if len(cells) > 6 else None
        liq     = _parse_br_number(cells[7]) if len(cells) > 7 else None

        vpa = None
        if preco and pvp and pvp > 0:
            vpa = round(preco / pvp, 4)

        rows.append({
            "TICKER":     ticker,
            "TIPO":       tipo,
            "NOME":       ticker,
            "SEGMENTO":   cells[1].strip() if len(cells) > 1 else "",
            "PRECO":      preco,
            "PVP":        pvp,
            "DY":         dy,
            "DY_12M_MED": dy,
            "VPA":        vpa,
            "LIQUIDEZ":   liq,
            "PATRIMONIO": patrim,
        })

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["TICKER"], keep="first").reset_index(drop=True)
    return df


def _load_or_scrape(cache_key: str, scrape_fn, label: str, force: bool) -> pd.DataFrame:
    """Cache mensal: retorna do JSON se existir, senão scrapa e salva."""
    cache_path = CACHE_DIR / f"{cache_key}.json"

    if not force and cache_path.exists():
        print(f"[fii_si_scraper] Cache {cache_key} → {cache_path.name}")
        with open(cache_path, encoding="utf-8") as f:
            cached = json.load(f)
        df = pd.DataFrame(cached["rows"])
        print(f"[fii_si_scraper] {len(df)} {label} carregados do cache")
        return df

    df = scrape_fn()
    if df.empty:
        raise RuntimeError(f"Fundamentus retornou 0 {label}")

    print(f"[fii_si_scraper] Total {label}: {len(df)} únicos")

    today = date.today()
    cache_data = {
        "data":  str(today),
        "mes":   cache_key,
        "total": len(df),
        "fonte": "Fundamentus",
        "rows":  df.to_dict("records"),
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[fii_si_scraper] Cache salvo: {cache_path}")
    return df


def fetch_all_si(force: bool = False) -> pd.DataFrame:
    """Retorna DataFrame com todos FIIs do Fundamentus. Cache mensal."""
    today     = date.today()
    cache_key = f"{today.year}_{today.month:02d}"
    return _load_or_scrape(cache_key, lambda: _scrape_url(_FII_URL, "FII"), "FIIs", force)


def fetch_all_fiagro(force: bool = False) -> pd.DataFrame:
    """Retorna DataFrame com todos FIAgros do Fundamentus. Cache mensal."""
    today     = date.today()
    cache_key = f"{today.year}_{today.month:02d}_fiagro"
    return _load_or_scrape(cache_key, lambda: _scrape_url(_FIAGRO_URL, "FIAgro"), "FIAgros", force)
