import pandas as pd


def compute_magic_formula(df: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    df = df.copy()

    # Menor EV/EBIT = mais barato = melhor rank
    df["rank_ev_ebit"] = df["EV/EBIT"].rank(ascending=True, method="min")
    # Maior ROIC = melhor empresa = melhor rank
    df["rank_roic"] = df["ROIC"].rank(ascending=False, method="min")
    # Magic Formula Score: menor = melhor
    df["mf_score"] = df["rank_ev_ebit"] + df["rank_roic"]

    top = df.nsmallest(top_n, "mf_score").reset_index(drop=True)
    top.insert(0, "posicao_mf", range(1, len(top) + 1))

    print(f"[ranking] Top {top_n} calculado. Melhor: {top.iloc[0]['TICKER']} (score={top.iloc[0]['mf_score']:.0f})", flush=True)
    return top


EXPORT_COLS = [
    "posicao_mf", "TICKER", "EV/EBIT", "ROIC", "mf_score",
    "MARGEM EBIT", "ROE", "DIVIDA LIQUIDA / EBIT",
    "LIQUIDEZ MEDIA DIARIA", "CAGR RECEITAS 5 ANOS",
    "CAGR LUCROS 5 ANOS", "VALOR DE MERCADO", "PRECO",
    "rank_ev_ebit", "rank_roic",
]


def to_records(df: pd.DataFrame) -> list[dict]:
    cols = [c for c in EXPORT_COLS if c in df.columns]
    return df[cols].to_dict(orient="records")
