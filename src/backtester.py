"""
Backtester Magic Formula BR.
Reconstroi rankings historicos usando yfinance e calcula retorno do portfolio.

Limitacao conhecida: survivorship bias — universo fixo no CSV de hoje.
Tickers que sairam da B3 antes nao aparecem. Retorno sera otimista.
"""

import sys
import io
import json
import time
import logging
import warnings
import argparse
from pathlib import Path
from datetime import datetime, date

import pandas as pd
import numpy as np
import yfinance as yf

warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / "output" / "backtest_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sa(ticker: str) -> str:
    return ticker.upper() + ".SA"


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return f if not np.isnan(f) else None
    except Exception:
        return None


# ── Cache de fundamentals ─────────────────────────────────────────────────────

def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}.json"


def _load_cache(ticker: str) -> dict | None:
    p = _cache_path(ticker)
    if not p.exists():
        return None
    age_hours = (time.time() - p.stat().st_mtime) / 3600
    if age_hours > 48:
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save_cache(ticker: str, data: dict):
    with open(_cache_path(ticker), "w", encoding="utf-8") as f:
        json.dump(data, f)


# ── Fetch fundamental data por ticker ────────────────────────────────────────

def _fetch_fundamentals(ticker: str) -> dict:
    """
    Retorna fundamentals historicos:
    - ebit_q: EBIT trimestral (ultimos 4-8 trimestres)
    - ebit_a: EBIT anual (ultimos 4 anos fiscais — cobre backtest desde 2022)
    - inv_cap, net_debt, shares: trimestral + anual como fallback
    Versao 2: suporta dados anuais para backtest historico real.
    """
    cached = _load_cache(ticker)
    if cached and cached.get("_v") == 2:
        return cached

    result = {"ebit_q": {}, "ebit_a": {}, "inv_cap": {}, "net_debt": {}, "shares": {}, "_v": 2}
    try:
        t = yf.Ticker(_sa(ticker))

        # Dados trimestrais (ultimos ~4-8 trimestres)
        qf = t.quarterly_financials
        qbs = t.quarterly_balance_sheet

        if not qf.empty and "EBIT" in qf.index:
            for col, val in qf.loc["EBIT"].items():
                v = _safe_float(val)
                if v is not None:
                    result["ebit_q"][str(col.date())] = v

        if not qbs.empty:
            for row, key in [
                ("Invested Capital", "inv_cap"),
                ("Net Debt", "net_debt"),
                ("Ordinary Shares Number", "shares"),
            ]:
                if row in qbs.index:
                    for col, val in qbs.loc[row].items():
                        v = _safe_float(val)
                        if v is not None:
                            result[key][str(col.date())] = v

        # Dados anuais (ultimos 4 anos fiscais — essencial para backtest 2022-2024)
        af = t.financials  # income statement anual
        abs_ = t.balance_sheet  # balanco anual

        if not af.empty and "EBIT" in af.index:
            for col, val in af.loc["EBIT"].items():
                v = _safe_float(val)
                if v is not None:
                    result["ebit_a"][str(col.date())] = v

        if not abs_.empty:
            for row, key in [
                ("Invested Capital", "inv_cap"),
                ("Net Debt", "net_debt"),
                ("Ordinary Shares Number", "shares"),
            ]:
                if row in abs_.index:
                    for col, val in abs_.loc[row].items():
                        v = _safe_float(val)
                        if v is not None:
                            date_str = str(col.date())
                            # trimestral tem prioridade; anual preenche lacunas
                            if date_str not in result[key]:
                                result[key][date_str] = v

    except Exception:
        pass

    _save_cache(ticker, result)
    return result


def _ttm_ebit_at(fund: dict, cutoff: date) -> float | None:
    """
    TTM EBIT na data cutoff.
    Prioridade: soma dos ultimos 4 trimestres disponíveis antes de cutoff.
    Fallback: EBIT anual mais recente antes de cutoff.
    """
    ebit_q = fund.get("ebit_q", {})
    ebit_a = fund.get("ebit_a", {})

    valid_q = sorted(
        [(datetime.strptime(k, "%Y-%m-%d").date(), v)
         for k, v in ebit_q.items()
         if datetime.strptime(k, "%Y-%m-%d").date() <= cutoff],
        key=lambda x: x[0], reverse=True
    )
    if len(valid_q) >= 4:
        return sum(v for _, v in valid_q[:4])

    # Fallback para anual
    valid_a = {
        datetime.strptime(k, "%Y-%m-%d").date(): v
        for k, v in ebit_a.items()
        if datetime.strptime(k, "%Y-%m-%d").date() <= cutoff
    }
    if valid_a:
        return valid_a[max(valid_a.keys())]

    # Parcial trimestral (< 4 trimestres) — anualiza proporcionalmente
    if valid_q:
        return sum(v for _, v in valid_q) * (4 / len(valid_q))

    return None


def _latest_before(series: dict, cutoff: date) -> float | None:
    """Pega valor mais recente da serie antes de cutoff."""
    valid = {
        datetime.strptime(k, "%Y-%m-%d").date(): v
        for k, v in series.items()
        if datetime.strptime(k, "%Y-%m-%d").date() <= cutoff
    }
    if not valid:
        return None
    return valid[max(valid.keys())]


# ── Fetch precos mensais (batch) ──────────────────────────────────────────────

def fetch_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Retorna DataFrame de precos mensais com tickers como colunas."""
    print(f"[backtest] Baixando precos mensais para {len(tickers)} tickers...")
    # BOVA11.SA = ETF Ibovespa total return (inclui dividendos) — benchmark justo vs portfolio total return
    sa_tickers = [_sa(t) for t in tickers] + ["BOVA11.SA"]
    raw = yf.download(sa_tickers, start=start, end=end, interval="1mo", progress=False, auto_adjust=True)

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"].copy()
    else:
        prices = raw[["Close"]].copy()

    prices.index = pd.to_datetime(prices.index)

    # Normaliza: remove .SA, mapeia BOVA11 -> IBOV
    rename_map = {}
    for c in prices.columns:
        cs = str(c)
        if "BOVA11" in cs:
            rename_map[c] = "IBOV"
        elif cs.endswith(".SA"):
            rename_map[c] = cs[:-3]
    if rename_map:
        prices = prices.rename(columns=rename_map)

    return prices


# ── Reconstroi metricas numa data ─────────────────────────────────────────────

def compute_metrics_at(
    ticker: str,
    cutoff: date,
    fundamentals: dict,
    price: float | None,
) -> dict | None:
    """
    Reconstroi EV/EBIT e ROIC para ticker em cutoff.
    Retorna None se dados insuficientes.
    """
    fund = fundamentals.get(ticker, {})

    ebit_anual = _ttm_ebit_at(fund, cutoff)
    inv_cap = _latest_before(fund.get("inv_cap", {}), cutoff)
    net_debt = _latest_before(fund.get("net_debt", {}), cutoff)
    shares = _latest_before(fund.get("shares", {}), cutoff)

    if ebit_anual is None or ebit_anual <= 0:
        return None
    if inv_cap is None or inv_cap <= 0:
        return None
    if price is None or price <= 0:
        return None
    if shares is None or shares <= 0:
        return None
    market_cap = price * shares
    ev = market_cap + (net_debt or 0)

    if ev <= 0:
        return None

    ev_ebit = ev / ebit_anual
    roic = (ebit_anual / inv_cap) * 100

    if ev_ebit <= 0 or roic <= 0:
        return None

    return {
        "TICKER": ticker,
        "EV/EBIT": round(ev_ebit, 2),
        "ROIC": round(roic, 2),
        "preco": round(price, 2),
    }


# ── Ranking Magic Formula numa data ──────────────────────────────────────────

def rank_at_date(
    tickers: list[str],
    cutoff: date,
    fundamentals: dict,
    prices_df: pd.DataFrame,
    top_n: int = 20,
) -> list[dict]:
    """Retorna top_n empresas ranqueadas pela Magic Formula em cutoff."""
    # Pega preco no mes mais proximo antes de cutoff
    price_row = prices_df[prices_df.index.date <= cutoff]
    if price_row.empty:
        return []
    price_row = price_row.iloc[-1]

    metrics = []
    for ticker in tickers:
        price = _safe_float(price_row.get(ticker))
        m = compute_metrics_at(ticker, cutoff, fundamentals, price)
        if m:
            metrics.append(m)

    if not metrics:
        return []

    df = pd.DataFrame(metrics)
    df["rank_ev"] = df["EV/EBIT"].rank(ascending=True, method="min")
    df["rank_roic"] = df["ROIC"].rank(ascending=False, method="min")
    df["mf_score"] = df["rank_ev"] + df["rank_roic"]
    top = df.nsmallest(top_n, "mf_score").reset_index(drop=True)
    return top.to_dict(orient="records")


# ── Loop principal do backtest ────────────────────────────────────────────────

def run_backtest(
    tickers: list[str],
    start: str = "2023-01-01",
    end: str | None = None,
    top_n: int = 15,
    hold_buffer: float = 2.0,
) -> dict:
    """
    hold_buffer: fator de buffer para reducao de turnover.
    Uma acao so sai do portfolio se cair abaixo do top (top_n * hold_buffer).
    Ex: buffer=2.0 com top_n=15 → so sai se cair do top 30.
    """
    end = end or str(date.today())
    buffer_n = int(top_n * hold_buffer)

    # 1. Precos mensais
    prices_df = fetch_prices(tickers, start, end)

    # 2. Fundamentals (com cache)
    print(f"[backtest] Buscando fundamentals para {len(tickers)} tickers...")
    fundamentals = {}
    for i, ticker in enumerate(tickers):
        fundamentals[ticker] = _fetch_fundamentals(ticker)
        if (i + 1) % 10 == 0:
            print(f"[backtest]   {i+1}/{len(tickers)} fundamentals carregados")
        time.sleep(0.3)

    # 3. Datas de rebalanceamento (fim de cada mes)
    rebal_dates = pd.date_range(start=start, end=end, freq="ME")
    if rebal_dates.empty:
        print("[backtest] Nenhuma data de rebalanceamento no periodo")
        return {}

    # 4. Loop mensal
    monthly_results = []
    portfolio: set[str] = set()
    portfolio_value = 100.0  # base 100
    ibov_base = None
    first_active_date = None

    for i, rebal_dt in enumerate(rebal_dates[:-1]):
        cutoff = rebal_dt.date()
        next_dt = rebal_dates[i + 1]

        # Ranking com buffer: pega top buffer_n para decidir o que manter
        all_ranked = rank_at_date(tickers, cutoff, fundamentals, prices_df, top_n=buffer_n)
        buffer_set = {r["TICKER"] for r in all_ranked}
        ranked_tickers = [r["TICKER"] for r in all_ranked]

        # Hold buffer: manter posicoes que ainda estao no top buffer_n
        keep = portfolio & buffer_set
        slots = top_n - len(keep)

        # Preencher slots com melhores ranked nao mantidos
        new_portfolio: set[str] = set(keep)
        for t in ranked_tickers:
            if slots <= 0:
                break
            if t not in new_portfolio:
                new_portfolio.add(t)
                slots -= 1

        entries = new_portfolio - portfolio
        exits = portfolio - new_portfolio
        top_detail = [r for r in all_ranked if r["TICKER"] in new_portfolio]

        # Precos de referencia neste mes (para calcular P&L de entrada/saida)
        cur_price_row = prices_df[prices_df.index.date <= cutoff]
        cur_price_row = cur_price_row.iloc[-1] if not cur_price_row.empty else pd.Series(dtype=float)

        if new_portfolio and first_active_date is None:
            first_active_date = str(cutoff)

        # Retorno do portfolio anterior no proximo mes
        monthly_return = None
        if portfolio:
            rets = []
            for t in portfolio:
                p0 = _safe_float(prices_df.loc[prices_df.index <= rebal_dt, t].iloc[-1]) if t in prices_df.columns else None
                p1 = _safe_float(prices_df.loc[prices_df.index <= next_dt, t].iloc[-1]) if t in prices_df.columns else None
                if p0 and p1 and p0 > 0:
                    ret = (p1 - p0) / p0
                    if -0.60 <= ret <= 0.60:  # cap: filtra halts e erros de dados
                        rets.append(ret)
            if rets:
                monthly_return = np.mean(rets) * 100

        if monthly_return is not None:
            portfolio_value *= (1 + monthly_return / 100)

        # IBOV no mesmo periodo
        ibov_ret = None
        if "IBOV" in prices_df.columns:
            ib0 = _safe_float(prices_df.loc[prices_df.index <= rebal_dt, "IBOV"].iloc[-1]) if not prices_df.loc[prices_df.index <= rebal_dt, "IBOV"].empty else None
            ib1 = _safe_float(prices_df.loc[prices_df.index <= next_dt, "IBOV"].iloc[-1]) if not prices_df.loc[prices_df.index <= next_dt, "IBOV"].empty else None
            if ib0 and ib1 and ib0 > 0:
                ibov_ret = (ib1 - ib0) / ib0 * 100
                if ibov_base is None:
                    ibov_base = ib0

        # Precos de saida (tickers que sairam nao estao em top_detail)
        precos_saida = {}
        for t in exits:
            p = _safe_float(cur_price_row.get(t))
            if p:
                precos_saida[t] = round(p, 2)

        monthly_results.append({
            "data": str(cutoff),
            "top15": sorted(new_portfolio),
            "entradas": sorted(entries),
            "saidas": sorted(exits),
            "precos_saida": precos_saida,
            "retorno_mes_pct": round(monthly_return, 2) if monthly_return is not None else None,
            "portfolio_valor": round(portfolio_value, 2),
            "ibov_retorno_mes_pct": round(ibov_ret, 2) if ibov_ret is not None else None,
            "detalhes": [
                {"ticker": r["TICKER"], "ev_ebit": r["EV/EBIT"], "roic": r["ROIC"], "mf_score": r.get("mf_score"), "preco": r.get("preco")}
                for r in top_detail
            ],
        })

        portfolio = new_portfolio
        print(f"[backtest] {cutoff} | top{top_n}: {len(new_portfolio)} empresas | entradas: {len(entries)} saidas: {len(exits)} | retorno: {f'{monthly_return:.1f}%' if monthly_return else 'N/A'} | portfolio: R${portfolio_value:.1f}")

    # 5. Estatisticas (apenas meses com portfolio ativo)
    active_results = [r for r in monthly_results if r["top15"]]
    retornos = [r["retorno_mes_pct"] for r in monthly_results if r["retorno_mes_pct"] is not None]
    total_return = portfolio_value - 100

    ibov_vals = []
    ibov_acc = 100.0
    for r in monthly_results:
        if r["ibov_retorno_mes_pct"] is not None:
            ibov_acc *= (1 + r["ibov_retorno_mes_pct"] / 100)
        ibov_vals.append(round(ibov_acc, 2))
    ibov_total = ibov_acc - 100

    # Drawdown maximo (apenas periodo ativo)
    peak = 100.0
    max_dd = 0.0
    for r in active_results:
        v = r["portfolio_valor"]
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    periodo_start = first_active_date or start
    stats = {
        "periodo": f"{periodo_start} ate {end}",
        "periodo_completo": f"{start} ate {end}",
        "meses": len(retornos),
        "retorno_total_pct": round(total_return, 2),
        "ibov_total_pct": round(ibov_total, 2),
        "alpha_pct": round(total_return - ibov_total, 2),
        "retorno_medio_mensal_pct": round(np.mean(retornos), 2) if retornos else None,
        "volatilidade_mensal_pct": round(np.std(retornos), 2) if retornos else None,
        "max_drawdown_pct": round(max_dd, 2),
        "meses_positivos": sum(1 for r in retornos if r > 0),
        "meses_negativos": sum(1 for r in retornos if r < 0),
        "hold_buffer": hold_buffer,
    }

    return {
        "stats": stats,
        "monthly": monthly_results,
        "ibov_acumulado": ibov_vals,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", required=True, help="JSON file com lista de tickers")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default=str(date.today()))
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--hold-buffer", type=float, default=2.0, help="Buffer fator: acao so sai se cair do top (top*buffer). Default 2.0")
    parser.add_argument("--output", default=str(ROOT / "output" / "backtest.json"))
    args = parser.parse_args()

    with open(args.tickers, encoding="utf-8") as f:
        tickers = json.load(f)

    result = run_backtest(tickers, start=args.start, end=args.end, top_n=args.top, hold_buffer=args.hold_buffer)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[backtest] Resultado salvo em {args.output}")
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
