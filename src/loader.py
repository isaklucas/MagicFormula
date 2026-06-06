import pandas as pd
import re


def _parse_br_number(value):
    if pd.isna(value) or str(value).strip() == "":
        return float("nan")
    s = str(value).strip()
    # Remove thousand separator (dot) then replace decimal comma with dot
    s = re.sub(r"\.(?=\d{3})", "", s)
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


NUMERIC_COLS = [
    "PRECO", "DY", "P/L", "P/VP", "P/ATIVOS", "MARGEM BRUTA", "MARGEM EBIT",
    "MARG. LIQUIDA", "P/EBIT", "EV/EBIT", "DIVIDA LIQUIDA / EBIT",
    "DIV. LIQ. / PATRI.", "PSR", "P/CAP. GIRO", "P. AT CIR. LIQ.",
    "LIQ. CORRENTE", "ROE", "ROA", "ROIC", "PATRIMONIO / ATIVOS",
    "PASSIVOS / ATIVOS", "GIRO ATIVOS", "CAGR RECEITAS 5 ANOS",
    "CAGR LUCROS 5 ANOS", "LIQUIDEZ MEDIA DIARIA", "VPA", "LPA",
    "PEG Ratio", "VALOR DE MERCADO",
]


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]
    df["TICKER"] = df["TICKER"].str.strip()

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_parse_br_number)

    return df
