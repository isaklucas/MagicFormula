import pandas as pd

# Guarda de outlier: numeros bons demais quase sempre sao EBIT contaminado por ganho
# nao-operacional (ex.: AMER3 pos-RJ, com o perdao de divida embutido no EBIT de 2024).
MIN_EV_EBIT = 1.0
MAX_ROIC = 100.0

# Bancos e seguradoras: a Magic Formula (EV/EBIT, ROIC) não se aplica ao balanço deles.
# CSAN (Cosan), EGIE (Engie) e TASA (Taurus) já estiveram aqui por engano — são
# holding/energia/indústria, não financeiras, e vinham sendo excluídas sem motivo.
FINANCIAL_PREFIXES = {
    "BBAS", "BBDC", "ITUB", "SANB", "BRSR", "BPAC", "BMGB", "BRBI",
    "ABCB", "PINE", "SULA", "PSSA", "IRBR", "BBSE", "CXSE", "WIZS",
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
    i = len(t) - 1
    while i >= 0 and t[i].isdigit():
        i -= 1
    return t[: i + 1]


def _safe_float(val, default: float = 0.0) -> float:
    try:
        f = float(val)
        return f if f == f else default
    except (TypeError, ValueError):
        return default


def deduplicate_by_company(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Remove tickers duplicados da mesma empresa.
    Prioridade: 11 (Units) > 4 (PN) > 3 (ON) > outros.
    Em caso de empate de sufixo, prefere maior DY.
    Retorna (df_dedupicado, lista_removidos).
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
        sort_asc.append(False)

    df_sorted = df.sort_values(sort_cols, ascending=sort_asc)
    df_dedup = df_sorted.drop_duplicates(subset="_base", keep="first")

    tickers_kept = set(df_dedup["TICKER"])
    removidos = [
        {
            "ticker": row["TICKER"],
            "etapa": "Deduplicação",
            "motivo": "Sufixo inferior (mesma empresa tem ticket melhor)",
        }
        for _, row in df.iterrows()
        if row["TICKER"] not in tickers_kept
    ]

    if removidos:
        print(f"[filtros] {len(removidos)} tickers duplicados removidos (mesmo empresa, sufixo inferior)")

    return df_dedup.drop(columns=["_base", "_prio"]).reset_index(drop=True), removidos


def apply_sector_limit(
    records: list[dict],
    setor_map: dict[str, str],
    max_per_sector: int = 5,
    desired_n: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Remove excesso de empresas do mesmo setor, com reposição do pool.
    Itera pelo ranking completo até ter desired_n candidatos (ou esgotar o pool).
    records devem estar ordenados por mf_score asc (melhor = menor score).
    Retorna (kept, removidos).
    """
    sector_count: dict[str, int] = {}
    kept = []
    removidos: list[dict] = []

    for r in records:
        if desired_n and len(kept) >= desired_n:
            break
        ticker = r["TICKER"]
        setor = setor_map.get(ticker, "Desconhecido")
        r["setor"] = setor
        count = sector_count.get(setor, 0)
        if setor == "Desconhecido" or count < max_per_sector:
            sector_count[setor] = count + 1
            kept.append(r)
        else:
            removidos.append({
                "ticker": ticker,
                "etapa": "Limite de setor",
                "motivo": f"Setor '{setor}' já tem {max_per_sector} representantes",
            })

    if removidos:
        print(f"[filtros] Removidos por limite de setor (max {max_per_sector}): {[r['ticker'] for r in removidos]}")
    print(f"[filtros] {len(kept)} empresas apos limite de setor")
    return kept, removidos


def apply_filters(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Aplica filtros básicos à Magic Formula.
    Retorna (df_filtrado, lista_removidos) onde cada remoção tem ticker+etapa+motivo.
    """
    total = len(df)
    removidos: list[dict] = []

    m_fin  = df["TICKER"].apply(_is_financial)
    m_liq  = df["LIQUIDEZ MEDIA DIARIA"].fillna(0) < 500_000
    m_ev   = df["EV/EBIT"].fillna(0) <= 0
    m_roic = df["ROIC"].fillna(0) <= 0
    m_div  = df["DIVIDA LIQUIDA / EBIT"].fillna(99) >= 5

    # P/VP <= 0 => patrimonio liquido negativo (empresa tecnicamente insolvente).
    # Ausente na fonte = beneficio da duvida.
    if "P/VP" in df.columns:
        m_pl = pd.to_numeric(df["P/VP"], errors="coerce").fillna(1) <= 0
    else:
        m_pl = pd.Series(False, index=df.index)

    m_out = (df["EV/EBIT"].fillna(99) < MIN_EV_EBIT) | (df["ROIC"].fillna(0) > MAX_ROIC)

    mask_keep = ~m_fin & ~m_liq & ~m_ev & ~m_roic & ~m_div & ~m_pl & ~m_out

    for idx in df[~mask_keep].index:
        row    = df.loc[idx]
        ticker = str(row["TICKER"])
        if m_fin[idx]:
            motivo = "Setor financeiro (MF não aplicável)"
        elif m_liq[idx]:
            liq = _safe_float(row.get("LIQUIDEZ MEDIA DIARIA"), 0)
            motivo = f"Liquidez R${liq/1_000:,.0f}k/dia < R$500k"
        elif m_ev[idx]:
            ev = _safe_float(row.get("EV/EBIT"), 0)
            motivo = f"EV/EBIT {ev:.1f} ≤ 0"
        elif m_roic[idx]:
            roic = _safe_float(row.get("ROIC"), 0)
            motivo = f"ROIC {roic:.1f}% ≤ 0"
        elif m_pl[idx]:
            pvp = _safe_float(row.get("P/VP"), 0)
            motivo = f"Patrimônio líquido negativo (P/VP {pvp:.2f} ≤ 0)"
        elif m_out[idx]:
            ev = _safe_float(row.get("EV/EBIT"), 0)
            roic = _safe_float(row.get("ROIC"), 0)
            if ev < MIN_EV_EBIT:
                motivo = f"Outlier: EV/EBIT {ev:.2f} < {MIN_EV_EBIT} (EBIT provavelmente contaminado)"
            else:
                motivo = f"Outlier: ROIC {roic:.0f}% > {MAX_ROIC:.0f}% (EBIT provavelmente contaminado)"
        else:
            div = _safe_float(row.get("DIVIDA LIQUIDA / EBIT"), 0)
            motivo = f"Dívida/EBIT {div:.1f}x ≥ 5"
        removidos.append({"ticker": ticker, "etapa": "Filtros básicos", "motivo": motivo})

    result = df[mask_keep].copy()
    print(f"[filtros] {total} -> {len(result)} empresas apos filtros basicos")

    result, removidos_dup = deduplicate_by_company(result)
    removidos.extend(removidos_dup)
    print(f"[filtros] {len(result)} empresas unicas apos deduplicacao")

    return result, removidos
