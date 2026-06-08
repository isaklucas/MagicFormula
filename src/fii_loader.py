"""
Carrega CSVs de FIIs e FIAgros exportados do StatusInvest.
Suporta data/fiis.csv + data/fiagros.csv (ou apenas um).
"""

import pandas as pd
from pathlib import Path


_COL_ALIASES: dict[str, list[str]] = {
    "TICKER":     ["TICKER", "Ticker", "ticker"],
    "PRECO":      ["PRECO", "Preço Atual", "PRECO_ATUAL", "Preço", "preco", "Cotação"],
    "PVP":        ["P/VP", "P_VP", "p/vp", "pvp", "P/Vp"],
    "DY":         ["DY", "Dividend Yield", "dy", "DY (12M)"],
    "DY_12M_MED": ["DY_12M_MEDIA", "DY 12M MEDIA", "Média 12M", "DY_12M_MED", "DY MEDIA (12M)"],
    "LIQUIDEZ":   ["LIQUIDEZ MEDIA DIARIA", "LIQUIDEZ_MEDIA_DIARIA",
                   "Liquidez Média Diária", "Liquidez Media Diaria", "Liquidez Diária"],
    "VPA":        ["VPA", "vpa", "V.P.A"],
    "SEGMENTO":   ["SEGMENTO", "Segmento", "SETOR", "Setor", "TIPO_FII", "Tipo"],
    "PATRIMONIO": ["PATRIMONIO LIQUIDO", "PATRIMÔNIO LÍQUIDO",
                   "Patrimônio Líquido", "PATRIMONIO_LIQUIDO", "Patrim. Líq."],
}


def _remap_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    for canonical, aliases in _COL_ALIASES.items():
        for alias in aliases:
            if alias in df.columns and alias != canonical:
                df.rename(columns={alias: canonical}, inplace=True)
                break
    return df


def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            continue
        if df[col].dtype == object:
            df[col] = (
                df[col].astype(str)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
                .str.replace("%", "", regex=False)
                .str.strip()
            )
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _load_one(path: str, tipo: str) -> pd.DataFrame:
    try:
        try:
            df = pd.read_csv(path, sep=";", decimal=",", encoding="utf-8-sig", thousands=".")
        except Exception:
            df = pd.read_csv(path, sep=",", decimal=".", encoding="utf-8-sig")

        df = _remap_columns(df)
        df["TIPO"] = tipo
        df["TICKER"] = df["TICKER"].astype(str).str.strip().str.upper()
        df = _to_numeric(df, ["PRECO", "PVP", "DY", "DY_12M_MED", "LIQUIDEZ", "VPA", "PATRIMONIO"])

        # Remove linhas sem ticker válido
        df = df[df["TICKER"].str.match(r"^[A-Z]{4}11$", na=False)].reset_index(drop=True)

        print(f"[fii_loader] {Path(path).name}: {len(df)} fundos ({tipo})")
        return df

    except FileNotFoundError:
        print(f"[fii_loader] Arquivo nao encontrado: {path}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[fii_loader] Erro ao carregar {path}: {e}")
        return pd.DataFrame()


def load_fiis_fiagros(fiis_path: str, fiagros_path: str) -> pd.DataFrame:
    """
    Carrega e unifica CSVs de FIIs e FIAgros.
    Pelo menos um arquivo deve existir.
    """
    frames = []

    if Path(fiis_path).exists():
        frames.append(_load_one(fiis_path, "FII"))
    else:
        print(f"[fii_loader] {fiis_path} nao encontrado — pulando FIIs")

    if Path(fiagros_path).exists():
        frames.append(_load_one(fiagros_path, "FIAgro"))
    else:
        print(f"[fii_loader] {fiagros_path} nao encontrado — pulando FIAgros")

    if not frames:
        raise FileNotFoundError(
            "Nenhum CSV encontrado.\n"
            "Exporte data/fiis.csv (StatusInvest > Fundos Imobiliários > Busca Avançada)\n"
            "e/ou data/fiagros.csv (StatusInvest > Fundos Agro > Busca Avançada)."
        )

    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    print(f"[fii_loader] Total carregado: {len(df)} fundos")
    return df
