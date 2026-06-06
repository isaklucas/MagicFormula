"""
Enriquece candidatos Magic Formula com dados históricos via yfinance.
Adiciona: setor, tendência ROIC/receita/margem (8 trimestres), preço 52 semanas, beta.
Dados usados pelos agentes para análise de tendência, não só snapshot do CSV.
"""

import time
import warnings
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")


def _safe_get(info: dict, key: str, default=None):
    v = info.get(key, default)
    return v if v not in (None, "N/A", "") else default


def _pct_change_series(series: pd.Series, n: int = 6) -> list[float]:
    """Últimos n valores de uma série numérica, do mais antigo para mais recente."""
    s = series.dropna()
    if s.empty:
        return []
    vals = s.iloc[:n][::-1].tolist()  # yfinance: mais recente primeiro → invertemos
    return [round(float(v), 2) for v in vals]


def _trend_label(values: list[float]) -> str:
    """Classifica tendência: CRESCENTE, ESTAVEL, DECRESCENTE, VOLATIL."""
    if len(values) < 3:
        return "INSUFICIENTE"
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    if pos >= len(diffs) - 1:
        return "CRESCENTE"
    if neg >= len(diffs) - 1:
        return "DECRESCENTE"
    if pos == neg:
        return "VOLATIL"
    return "ESTAVEL"


def _compute_roic_quarterly(qf: pd.DataFrame, qbs: pd.DataFrame, n: int = 6) -> list[float]:
    """ROIC trimestral = EBIT / Invested Capital (anualizado)."""
    try:
        ebit = qf.loc["EBIT"].dropna() if "EBIT" in qf.index else pd.Series(dtype=float)
        ic = qbs.loc["Invested Capital"].dropna() if "Invested Capital" in qbs.index else pd.Series(dtype=float)
        if ebit.empty or ic.empty:
            return []
        common = ebit.index.intersection(ic.index)
        if common.empty:
            return []
        roic_vals = ((ebit[common] * 4) / ic[common] * 100).dropna()
        return _pct_change_series(roic_vals, n)
    except Exception:
        return []


def _compute_ebit_margin_quarterly(qf: pd.DataFrame, n: int = 6) -> list[float]:
    """Margem EBIT trimestral = EBIT / Total Revenue."""
    try:
        ebit = qf.loc["EBIT"].dropna() if "EBIT" in qf.index else pd.Series(dtype=float)
        rev_keys = [k for k in qf.index if "Revenue" in k and "Total" in k]
        if not rev_keys or ebit.empty:
            return []
        rev = qf.loc[rev_keys[0]].dropna()
        common = ebit.index.intersection(rev.index)
        if common.empty:
            return []
        margin = (ebit[common] / rev[common] * 100).dropna()
        return _pct_change_series(margin, n)
    except Exception:
        return []


def _compute_revenue_quarterly(qf: pd.DataFrame, n: int = 6) -> list[float]:
    """Receita trimestral em milhões BRL."""
    try:
        rev_keys = [k for k in qf.index if "Revenue" in k and "Total" in k]
        if not rev_keys:
            return []
        rev = qf.loc[rev_keys[0]].dropna()
        vals = _pct_change_series(rev, n)
        return [round(v / 1_000_000, 1) for v in vals]
    except Exception:
        return []


def _price_context(hist: pd.DataFrame, info: dict) -> dict:
    """Contexto de preço: posição vs 52 semanas."""
    high52 = _safe_get(info, "fiftyTwoWeekHigh")
    low52 = _safe_get(info, "fiftyTwoWeekLow")
    current = hist["Close"].iloc[-1] if not hist.empty else None

    pct_from_high = None
    pct_from_low = None
    if current and high52 and low52 and high52 > low52:
        pct_from_high = round((current - high52) / high52 * 100, 1)
        pct_from_low = round((current - low52) / low52 * 100, 1)

    return {
        "preco_atual": round(float(current), 2) if current else None,
        "max_52sem": round(float(high52), 2) if high52 else None,
        "min_52sem": round(float(low52), 2) if low52 else None,
        "pct_vs_max": float(pct_from_high) if pct_from_high is not None else None,
        "pct_vs_min": float(pct_from_low) if pct_from_low is not None else None,
    }


def enrich_ticker(ticker: str) -> dict:
    """
    Retorna dict com dados históricos enriquecidos para um ticker.
    Nunca lança exceção — retorna dict vazio em caso de falha.
    """
    result = {"ticker": ticker, "erro": None}
    yf_ticker = ticker.upper()
    if not yf_ticker.endswith(".SA"):
        yf_ticker = yf_ticker + ".SA"

    try:
        t = yf.Ticker(yf_ticker)
        info = t.info or {}

        if not info or info.get("quoteType") is None:
            result["erro"] = "ticker nao encontrado no yfinance"
            return result

        # Setor e industria
        result["setor"] = _safe_get(info, "sector", "Desconhecido")
        result["industria"] = _safe_get(info, "industry", "Desconhecido")
        result["beta"] = _safe_get(info, "beta")

        # Preço histórico
        hist = t.history(period="1y")
        result["preco"] = _price_context(hist, info)

        # Dados trimestrais
        qf = t.quarterly_financials
        qbs = t.quarterly_balance_sheet

        roic_hist = _compute_roic_quarterly(qf, qbs, n=6)
        ebit_margin_hist = _compute_ebit_margin_quarterly(qf, n=6)
        receita_hist = _compute_revenue_quarterly(qf, n=6)

        result["roic_trimestral"] = roic_hist
        result["roic_tendencia"] = _trend_label(roic_hist)

        result["margem_ebit_trimestral"] = ebit_margin_hist
        result["margem_tendencia"] = _trend_label(ebit_margin_hist)

        result["receita_trimestral_mi"] = receita_hist
        result["receita_tendencia"] = _trend_label(receita_hist)

    except Exception as e:
        result["erro"] = str(e)

    return result


def enrich_candidates(candidates: list[dict], delay: float = 1.5) -> dict[str, dict]:
    """
    Enriquece lista de candidatos. Retorna dict {ticker: dados_enriquecidos}.
    """
    results = {}
    total = len(candidates)
    for i, c in enumerate(candidates):
        ticker = c["TICKER"]
        print(f"[enricher] {ticker} ({i+1}/{total})...", end=" ", flush=True)
        data = enrich_ticker(ticker)
        results[ticker] = data
        if data.get("erro"):
            print(f"ERRO: {data['erro']}")
        else:
            print(f"setor={data.get('setor','?')} roic_tend={data.get('roic_tendencia','?')}")
        time.sleep(delay)
    return results


def format_for_agent(ticker: str, enriched: dict, candidate: dict) -> str:
    """
    Formata dados enriquecidos como bloco de texto para o prompt do agente.
    """
    if not enriched or enriched.get("erro"):
        return ""

    lines = [f"\nDADOS HISTÓRICOS ({ticker}):"]

    setor = enriched.get("setor")
    if setor:
        lines.append(f"- Setor: {setor} | Indústria: {enriched.get('industria','?')}")

    beta = enriched.get("beta")
    if beta:
        lines.append(f"- Beta: {beta:.2f} ({'alta volatilidade' if beta > 1.3 else 'baixa volatilidade' if beta < 0.7 else 'volatilidade moderada'})")

    preco = enriched.get("preco", {})
    if preco.get("max_52sem"):
        p_max = preco["max_52sem"]
        p_min = preco["min_52sem"]
        p_cur = preco.get("preco_atual", candidate.get("PRECO", "?"))
        pct_max = preco.get("pct_vs_max")
        pct_min = preco.get("pct_vs_min")
        lines.append(
            f"- Preço 52 semanas: Mín R${p_min} | Máx R${p_max} | "
            f"Atual {pct_max:+.1f}% vs máx / {pct_min:+.1f}% vs mín"
        )

    roic_hist = enriched.get("roic_trimestral", [])
    roic_tend = enriched.get("roic_tendencia", "")
    if roic_hist:
        hist_str = " → ".join(f"{v:.1f}%" for v in roic_hist)
        lines.append(f"- ROIC trimestral (antigo→recente): {hist_str} [{roic_tend}]")

    mg_hist = enriched.get("margem_ebit_trimestral", [])
    mg_tend = enriched.get("margem_tendencia", "")
    if mg_hist:
        hist_str = " → ".join(f"{v:.1f}%" for v in mg_hist)
        lines.append(f"- Margem EBIT trimestral: {hist_str} [{mg_tend}]")

    rec_hist = enriched.get("receita_trimestral_mi", [])
    rec_tend = enriched.get("receita_tendencia", "")
    if rec_hist:
        hist_str = " → ".join(f"R${v}M" for v in rec_hist)
        lines.append(f"- Receita trimestral: {hist_str} [{rec_tend}]")

    return "\n".join(lines)
