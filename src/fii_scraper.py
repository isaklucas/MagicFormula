"""
Busca lista de tickers FII do Funds Explorer (HTML parsing).
P/VP, preço, dividendos e idade vêm do yfinance via fii_enricher.py.
"""

import httpx
import re
import pandas as pd
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

_FE_FUNDS_URL   = "https://www.fundsexplorer.com.br/funds"
_FE_FIAGRO_URL  = "https://www.fundsexplorer.com.br/fiagros"


def _parse_tickerboxes(html: str, tipo: str) -> pd.DataFrame:
    """
    Extrai tickers e segmentos dos elementos tickerBox do Funds Explorer.
    Cada box tem: tipo/segmento, ticker, nome, e 2 valores numéricos (DY, Patrimônio).
    """
    soup = BeautifulSoup(html, "html.parser")
    boxes = soup.find_all("div", attrs={"data-element": "content-list-ticker"})

    rows = []
    for box in boxes:
        ticker_el = box.find(attrs={"data-element": "ticker-box-title"})
        type_el   = box.find(class_="tickerBox__type")
        name_el   = box.find(class_="tickerBox__desc")

        if not ticker_el:
            continue

        ticker = ticker_el.get_text(strip=True).upper()
        if not re.match(r"^[A-Z]{4}11$", ticker):
            continue

        segmento = type_el.get_text(strip=True) if type_el else ""
        nome     = name_el.get_text(strip=True) if name_el else ""

        rows.append({"TICKER": ticker, "SEGMENTO": segmento, "NOME": nome, "TIPO": tipo})

    return pd.DataFrame(rows)


def _fetch_page(url: str) -> str:
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=20) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def fetch_fiis() -> pd.DataFrame:
    """Lista de FIIs do Funds Explorer."""
    print("[fii_scraper] Funds Explorer /funds...")
    try:
        html = _fetch_page(_FE_FUNDS_URL)
        df = _parse_tickerboxes(html, "FII")
        print(f"[fii_scraper] FIIs encontrados: {len(df)}")
        return df
    except Exception as e:
        print(f"[fii_scraper] FE /funds erro: {e}")
        return pd.DataFrame()


def fetch_fiagros() -> pd.DataFrame:
    """Lista de FIAgros do Funds Explorer."""
    print("[fii_scraper] Funds Explorer /fiagros...")
    try:
        html = _fetch_page(_FE_FIAGRO_URL)
        df = _parse_tickerboxes(html, "FIAgro")
        if df.empty:
            # Fallback: extrai todos XXXX11 do HTML que não aparecem na lista FII
            tickers = list(dict.fromkeys(re.findall(r'\b([A-Z]{4}11)\b', html)))
            print(f"[fii_scraper] FIAgros (fallback regex): {len(tickers)} tickers")
            return pd.DataFrame([{"TICKER": t, "SEGMENTO": "Agro", "NOME": "", "TIPO": "FIAgro"} for t in tickers])
        print(f"[fii_scraper] FIAgros encontrados: {len(df)}")
        return df
    except Exception as e:
        print(f"[fii_scraper] FE /fiagros erro: {e}")
        return pd.DataFrame()


def fetch_all() -> pd.DataFrame:
    """
    Retorna DataFrame com colunas: TICKER, SEGMENTO, NOME, TIPO.
    Dados numéricos (P/VP, preço, DY) são enriquecidos pelo fii_enricher.py via yfinance.
    """
    frames = []

    df_fii = fetch_fiis()
    if not df_fii.empty:
        frames.append(df_fii)

    df_fiagro = fetch_fiagros()
    if not df_fiagro.empty:
        frames.append(df_fiagro)

    if not frames:
        raise RuntimeError(
            "Funds Explorer inacessível.\n"
            "Exporte data/fiis.csv e data/fiagros.csv manualmente do StatusInvest."
        )

    df = pd.concat(frames, ignore_index=True)
    # Deduplica (FIAgros podem aparecer também como FII no /funds)
    df = df.drop_duplicates(subset=["TICKER"], keep="first").reset_index(drop=True)
    print(f"[fii_scraper] Total: {len(df)} fundos únicos")
    return df
