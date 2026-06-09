"""
Status Invest — busca avançada de ações (categoryType=1).

POST /category/advancedsearchresultpaginated
Retorna DataFrame com as mesmas colunas que loader.load_csv() produz,
permitindo substituição direta do CSV manual.
"""

import json
import os
import httpx
import pandas as pd

_URL = "https://statusinvest.com.br/category/advancedsearchresultpaginated"

_SI_COOKIE = os.getenv("SI_COOKIE", "")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "Referer": "https://statusinvest.com.br/acoes",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "priority": "u=1, i",
    **( {"Cookie": _SI_COOKIE} if _SI_COOKIE else {} ),
}

# Mapeamento: campo SI (JSON) → coluna CSV esperada pelo pipeline
_FIELD_MAP = {
    "ticker":                          "TICKER",
    "price":                           "PRECO",
    "dy":                              "DY",
    "p_l":                             "P/L",
    "p_vp":                            "P/VP",
    "p_ativo":                         "P/ATIVOS",
    "margembruta":                     "MARGEM BRUTA",
    "margemebit":                      "MARGEM EBIT",
    "margemliquida":                   "MARG. LIQUIDA",
    "p_ebit":                          "P/EBIT",
    "ev_ebit":                         "EV/EBIT",
    "dividaliquidaebit":               "DIVIDA LIQUIDA / EBIT",
    "dividaliquidapatrimonioliquido":  "DIV. LIQ. / PATRI.",
    "p_sr":                            "PSR",
    "p_capitalgiro":                   "P/CAP. GIRO",
    "p_ativocirculante":               "P. AT CIR. LIQ.",
    "liquidezcorrente":                "LIQ. CORRENTE",
    "roe":                             "ROE",
    "roa":                             "ROA",
    "roic":                            "ROIC",
    "pl_ativo":                        "PATRIMONIO / ATIVOS",
    "passivo_ativo":                   "PASSIVOS / ATIVOS",
    "giroativos":                      "GIRO ATIVOS",
    "receitas_cagr5":                  "CAGR RECEITAS 5 ANOS",
    "lucros_cagr5":                    "CAGR LUCROS 5 ANOS",
    "liquidezmediadiaria":             "LIQUIDEZ MEDIA DIARIA",
    "vpa":                             "VPA",
    "lpa":                             "LPA",
    "peg_ratio":                       "PEG Ratio",
    "valormercado":                    "VALOR DE MERCADO",
}

# Colunas numéricas esperadas (para garantir dtype float)
_NUMERIC_COLS = [
    "PRECO", "DY", "P/L", "P/VP", "P/ATIVOS", "MARGEM BRUTA", "MARGEM EBIT",
    "MARG. LIQUIDA", "P/EBIT", "EV/EBIT", "DIVIDA LIQUIDA / EBIT",
    "DIV. LIQ. / PATRI.", "PSR", "P/CAP. GIRO", "P. AT CIR. LIQ.",
    "LIQ. CORRENTE", "ROE", "ROA", "ROIC", "PATRIMONIO / ATIVOS",
    "PASSIVOS / ATIVOS", "GIRO ATIVOS", "CAGR RECEITAS 5 ANOS",
    "CAGR LUCROS 5 ANOS", "LIQUIDEZ MEDIA DIARIA", "VPA", "LPA",
    "PEG Ratio", "VALOR DE MERCADO",
]

_SEARCH_PAYLOAD = json.dumps({
    "Sector": "",
    "SubSector": "",
    "Segment": "",
    "my_range": "-20;100",
    "forecast": {
        "upsidedownside": {"Item1": None, "Item2": None},
        "estimatesnumber": {"Item1": None, "Item2": None},
        "revisedup": True,
        "reviseddown": True,
        "consensus": [],
    },
    "dy":                   {"Item1": None, "Item2": None},
    "p_l":                  {"Item1": None, "Item2": None},
    "peg_ratio":            {"Item1": None, "Item2": None},
    "p_vp":                 {"Item1": None, "Item2": None},
    "p_ativo":              {"Item1": None, "Item2": None},
    "margembruta":          {"Item1": None, "Item2": None},
    "giroativos":           {"Item1": None, "Item2": None},
    "receitas_cagr5":       {"Item1": None, "Item2": None},
    "lucros_cagr5":         {"Item1": None, "Item2": None},
    "liquidezmediadiaria":  {"Item1": None, "Item2": None},
    "vpa":                  {"Item1": None, "Item2": None},
    "lpa":                  {"Item1": None, "Item2": None},
    "valormercado":         {"Item1": None, "Item2": None},
}, separators=(",", ":"))


def _fetch_page(client: httpx.Client, page: int, take: int) -> dict:
    # SI usa GET com query params; page é 0-indexed; CategoryType com C maiúsculo
    params = {
        "search": _SEARCH_PAYLOAD,
        "orderColumn": "",
        "isAsc": "",
        "page": str(page),
        "take": str(take),
        "CategoryType": "1",
    }
    r = client.get(_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _map_item(item: dict, key_lower_map: dict[str, str]) -> dict:
    """Mapeia um item do response SI para as colunas do pipeline."""
    row = {}
    for si_key_lower, csv_col in key_lower_map.items():
        # Tenta chave lowercase; SI às vezes retorna camelCase
        val = item.get(si_key_lower)
        if val is None:
            # Tenta variação com primeiro char maiúsculo
            val = item.get(si_key_lower[0].upper() + si_key_lower[1:])
        if val is None:
            val = float("nan")
        row[csv_col] = val
    return row


def fetch_all_stocks(take: int = 600) -> pd.DataFrame:
    """
    Busca todas as ações do Status Invest via busca avançada.
    Retorna DataFrame com as mesmas colunas que load_csv() produz.
    """
    rows = []

    with httpx.Client(headers=_HEADERS, follow_redirects=True) as client:
        # Página 0 para descobrir total (SI é 0-indexed)
        resp = _fetch_page(client, page=0, take=take)

        items = resp.get("list") or resp.get("data") or []
        if not items:
            raise RuntimeError(f"Status Invest retornou lista vazia. Response keys: {list(resp.keys())}")

        first_keys = {k.lower(): k for k in items[0].keys()}
        print(f"[si_fetcher] Campos recebidos ({len(first_keys)}): {sorted(first_keys)[:10]}...")

        key_lower_map: dict[str, str] = {}
        for si_key_lower, csv_col in _FIELD_MAP.items():
            if si_key_lower in first_keys:
                key_lower_map[si_key_lower] = csv_col
            else:
                matches = [k for k in first_keys if si_key_lower in k or k in si_key_lower]
                if matches:
                    key_lower_map[matches[0]] = csv_col
                else:
                    print(f"[si_fetcher] AVISO: campo '{si_key_lower}' → '{csv_col}' não encontrado no response")

        total_results = resp.get("totalResults", len(items))
        total_pages = max(1, -(-total_results // take))  # ceiling division
        cookie_status = "com cookie" if _SI_COOKIE else "sem cookie (universo limitado)"
        print(f"[si_fetcher] {total_results} ações | {total_pages} página(s) | {cookie_status}")

        for item in items:
            item_lower = {k.lower(): v for k, v in item.items()}
            rows.append(_map_item(item_lower, key_lower_map))

        # Páginas 1..N-1 (0-indexed)
        for page in range(1, total_pages):
            resp_n = _fetch_page(client, page=page, take=take)
            for item in (resp_n.get("list") or resp_n.get("data") or []):
                item_lower = {k.lower(): v for k, v in item.items()}
                rows.append(_map_item(item_lower, key_lower_map))
            print(f"[si_fetcher] Página {page + 1}/{total_pages} carregada")

    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError("Status Invest retornou 0 ações.")

    # Garante TICKER limpo
    df["TICKER"] = df["TICKER"].astype(str).str.strip().str.upper()

    # Converte colunas numéricas (SI já retorna float, mas garante o tipo)
    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.drop_duplicates(subset=["TICKER"], keep="first").reset_index(drop=True)
    print(f"[si_fetcher] {len(df)} ações únicas carregadas")
    return df
