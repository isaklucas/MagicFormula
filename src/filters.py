import pandas as pd

FINANCIAL_PREFIXES = {
    "BBAS", "BBDC", "ITUB", "SANB", "BRSR", "BPAC", "BMGB", "BRBI",
    "ABCB", "PINE", "CSAN", "SULA", "PSSA", "IRBR", "BBSE", "CXSE",
    "WIZS", "EGIE", "TASA",
}


def _is_financial(ticker: str) -> bool:
    return ticker[:4].upper() in FINANCIAL_PREFIXES


def _suffix_priority(ticker: str) -> int:
    """Menor numero = maior prioridade para representar a empresa."""
    t = ticker.upper()
    if t.endswith("11"):
        return 0   # Units (BPAC11, SANH11) — melhor liquidez e governanca
    if t.endswith("4"):
        return 1   # PN — prioridade em dividendos
    if t.endswith("3"):
        return 2   # ON — acao ordinaria padrao
    return 3       # outros sufixos (5, 6, 7, 8...)


def _company_base(ticker: str) -> str:
    """Extrai base da empresa (4 chars) ignorando o sufixo numerico."""
    t = ticker.upper().strip()
    # Remove sufixo numerico (1-2 digitos no final)
    i = len(t) - 1
    while i >= 0 and t[i].isdigit():
        i -= 1
    return t[: i + 1]


def deduplicate_by_company(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove tickers duplicados da mesma empresa.
    Prioridade: 11 (Units) > 4 (PN) > 3 (ON) > outros.
    Em caso de empate de sufixo, prefere maior DY.
    """
    df = df.copy()
    df["_base"] = df["TICKER"].apply(_company_base)
    df["_prio"] = df["TICKER"].apply(_suffix_priority)

    dy_col = "DY" if "DY" in df.columns else None
    sort_cols = ["_base", "_prio"]
    sort_asc = [True, True]
    if dy_col:
        df[dy_col] = pd.to_numeric(df[dy_col], errors="coerce").fillna(0)
        sort_cols.append(dy_col)
        sort_asc.append(False)  # maior DY = melhor em empate

    df_sorted = df.sort_values(sort_cols, ascending=sort_asc)
    df_dedup = df_sorted.drop_duplicates(subset="_base", keep="first")

    removidos = len(df) - len(df_dedup)
    if removidos > 0:
        print(f"[filtros] {removidos} tickers duplicados removidos (mesmo empresa, sufixo inferior)")

    return df_dedup.drop(columns=["_base", "_prio"]).reset_index(drop=True)


def apply_sector_limit(records: list[dict], setor_map: dict[str, str], max_per_sector: int = 3) -> list[dict]:
    """
    Remove excesso de empresas do mesmo setor.
    Preserva as de melhor posicao MF (menor mf_score = melhor).
    records ja devem estar ordenados por mf_score asc.
    setor_map: {ticker: setor}
    """
    sector_count: dict[str, int] = {}
    kept = []
    removed = []

    for r in records:
        ticker = r["TICKER"]
        setor = setor_map.get(ticker, "Desconhecido")
        r["setor"] = setor
        count = sector_count.get(setor, 0)
        if setor == "Desconhecido" or count < max_per_sector:
            sector_count[setor] = count + 1
            kept.append(r)
        else:
            removed.append(ticker)

    if removed:
        print(f"[filtros] Removidos por limite de setor (max {max_per_sector}): {removed}")
    print(f"[filtros] {len(kept)} empresas apos limite de setor")
    return kept


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    total = len(df)
    mask = pd.Series([True] * total, index=df.index)

    # Remove financeiros (Magic Formula nao se aplica)
    mask &= ~df["TICKER"].apply(_is_financial)

    # Liquidez minima 500k/dia
    mask &= df["LIQUIDEZ MEDIA DIARIA"].fillna(0) >= 500_000

    # EV/EBIT positivo (negativo = prejuizo ou divida > ativos)
    mask &= df["EV/EBIT"].fillna(0) > 0

    # ROIC positivo — FIIs reais nao tem ROIC, sao eliminados aqui naturalmente
    mask &= df["ROIC"].fillna(0) > 0

    # Divida/EBIT controlada
    mask &= df["DIVIDA LIQUIDA / EBIT"].fillna(99) < 5

    result = df[mask].copy()
    print(f"[filtros] {total} -> {len(result)} empresas apos filtros basicos")

    # Deduplica: uma acao por empresa, melhor sufixo
    result = deduplicate_by_company(result)
    print(f"[filtros] {len(result)} empresas unicas apos deduplicacao")

    return result
