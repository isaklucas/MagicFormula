"""
Detecção de dividendos extraordinários em FIIs/FIAgros.

Método IQR: remove meses com pagamento acima de Q3 + 1.5*IQR
(pagamentos por venda de ativo, amortização pontual, etc.).
DY limpo = média mensal limpa × 12 / preço.
"""

import pandas as pd

_MIN_MESES = 8  # mínimo de meses com dados para considerar o fundo válido


def _aggregate_monthly(divs: pd.Series) -> pd.Series:
    """Agrega por mês (alguns FIIs pagam duas vezes no mesmo mês)."""
    if divs.empty:
        return pd.Series(dtype=float)
    if divs.index.tz is None:
        divs.index = divs.index.tz_localize("UTC")
    monthly = divs.resample("ME").sum()
    return monthly[monthly > 0]


def clean_dy(divs_24m: pd.Series, price: float) -> dict:
    """
    Calcula DY limpo para os últimos 12 meses.

    Retorna dict com:
        dy_bruto_12m    — DY anualizado com todos os dividendos (%)
        dy_limpo_12m    — DY anualizado sem outliers (% — base do ranking)
        meses_com_dados — quantos meses tiveram pagamento nos últimos 12M
        meses_removidos — quantos meses foram detectados como extraordinários
        valores_removidos — lista dos dividendos removidos (R$/cota)
        valido          — False se dados insuficientes
        motivo_invalido — razão se valido=False
    """
    if not price or price <= 0:
        return _invalid("preco invalido ou ausente")

    if divs_24m is None or (hasattr(divs_24m, "empty") and divs_24m.empty):
        return _invalid("sem dados de dividendos no yfinance")

    monthly = _aggregate_monthly(divs_24m)
    if monthly.empty:
        return _invalid("sem dividendos nos ultimos 24 meses")

    # Filtra últimos 12 meses
    cutoff = pd.Timestamp.now(tz="UTC") - pd.DateOffset(months=12)
    if monthly.index.tz is None:
        monthly.index = monthly.index.tz_localize("UTC")
    last_12m = monthly[monthly.index >= cutoff]

    if len(last_12m) < _MIN_MESES:
        return _invalid(f"apenas {len(last_12m)} meses com dados (minimo {_MIN_MESES})")

    # DY bruto
    dy_bruto = last_12m.sum() / price

    # Detecção IQR
    Q1 = float(last_12m.quantile(0.25))
    Q3 = float(last_12m.quantile(0.75))
    IQR = Q3 - Q1

    if IQR == 0:
        clean = last_12m.copy()
        removed = pd.Series(dtype=float)
    else:
        upper_fence = Q3 + 1.5 * IQR
        clean   = last_12m[last_12m <= upper_fence]
        removed = last_12m[last_12m > upper_fence]

    if len(clean) < _MIN_MESES:
        return _invalid(
            f"apos remocao de anomalias, apenas {len(clean)} meses restantes"
        )

    # DY limpo: média mensal limpa × 12 (extrapola se removemos meses)
    media_mensal_limpa = float(clean.mean())
    dy_limpo = (media_mensal_limpa * 12) / price

    return {
        "dy_bruto_12m":    round(dy_bruto * 100, 2),
        "dy_limpo_12m":    round(dy_limpo * 100, 2),
        "meses_com_dados": int(len(last_12m)),
        "meses_removidos": int(len(removed)),
        "valores_removidos": [round(float(v), 4) for v in removed.values],
        "valido":          True,
        "motivo_invalido": "",
    }


def _invalid(motivo: str) -> dict:
    return {
        "dy_bruto_12m":    None,
        "dy_limpo_12m":    None,
        "meses_com_dados": 0,
        "meses_removidos": 0,
        "valores_removidos": [],
        "valido":          False,
        "motivo_invalido": motivo,
    }
