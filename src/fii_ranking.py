"""
Filtra e rankeia FIIs/FIAgros por DY Limpo 12M.
TOP 20 FIIs + TOP 10 FIAgros = 30 candidatos totais.
"""

import pandas as pd

_MIN_LIQUIDEZ_FII = 1_000_000  # R$ 1M liquidez diária mínima (FIIs)
_MIN_AGE_DAYS     = 365
_TOP_N_FII        = 20
_TOP_N_FIAGRO     = 10


def apply_basic_filters(df: pd.DataFrame, min_liquidez: float = _MIN_LIQUIDEZ_FII) -> pd.DataFrame:
    """
    Filtra:
    - P/VP < 0.90
    - Liquidez diária mínima (se coluna disponível)
    """
    if "PVP" not in df.columns:
        raise ValueError(
            "Coluna P/VP nao encontrada. Verifique o CSV exportado do StatusInvest."
        )

    total = len(df)

    # P/VP < 0.90
    df = df[df["PVP"].notna() & (df["PVP"] < 0.90)].copy()
    print(f"[fii_ranking] P/VP < 0.90:       {total} → {len(df)}")

    # Liquidez mínima
    if "LIQUIDEZ" in df.columns:
        before = len(df)
        mask = df["LIQUIDEZ"].isna() | (df["LIQUIDEZ"] >= min_liquidez)
        df = df[mask].copy()
        print(f"[fii_ranking] Liquidez >= R${min_liquidez:,.0f}: {before} → {len(df)}")

    return df.reset_index(drop=True)


def apply_age_filter(records: list[dict], enriched: dict[str, dict]) -> list[dict]:
    """Remove fundos com < 1 ano de histórico de preços."""
    before = len(records)
    result = []
    for r in records:
        ticker = r["TICKER"]
        age = enriched.get(ticker, {}).get("idade_dias", -1)
        if age >= _MIN_AGE_DAYS:
            result.append(r)
        else:
            label = f"{age}d" if age > 0 else "sem historico"
            print(f"[fii_ranking] {ticker} removido: {label} < 1 ano")
    print(f"[fii_ranking] Filtro de idade:       {before} → {len(result)}")
    return result


def rank_by_dy_limpo(records: list[dict], top_n: int = _TOP_N_FII) -> list[dict]:
    """
    Ordena por dy_limpo_12m descrescente.
    Descarta fundos com dados DY insuficientes.
    Retorna TOP N com campo 'posicao' (1-based).
    """
    valid   = [r for r in records if r.get("dy_info", {}).get("valido")]
    invalid = [r for r in records if not r.get("dy_info", {}).get("valido")]

    if invalid:
        print(f"[fii_ranking] {len(invalid)} fundos descartados (DY insuficiente):")
        for r in invalid:
            motivo = r.get("dy_info", {}).get("motivo_invalido", "?")
            print(f"  {r['TICKER']}: {motivo}")

    valid.sort(key=lambda r: r["dy_info"]["dy_limpo_12m"], reverse=True)
    top = valid[:top_n]

    for i, r in enumerate(top):
        r["posicao"] = i + 1

    print(f"[fii_ranking] TOP {top_n} selecionados de {len(valid)} validos")
    return top
