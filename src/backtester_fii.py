"""
Backtester FII — DY Limpo 12M ranking vs IFIX.
Universo: todos os FIIs do cache Fundamentus.
Benchmark: IFIX11.SA (ETF que replica o índice IFIX).
"""

import re
import sys
import io
import json
import time
import logging
import warnings
import argparse
import glob
from pathlib import Path
from datetime import date

_VALID_FII = re.compile(r"^[A-Z]{4}11$")

import pandas as pd
import numpy as np
import yfinance as yf

warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT      = Path(__file__).parent.parent
CACHE_DIR = ROOT / "output" / "backtest_fii_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _sa(ticker: str) -> str:
    return ticker.upper() + ".SA"


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return f if not np.isnan(f) else None
    except Exception:
        return None


# ── Preços mensais ────────────────────────────────────────────────────────────

_IFIX_CANDIDATES = ["IFIX11.SA", "XFIX11.SA", "BVAR11.SA"]


def fetch_prices(tickers: list[str], start: str, end: str) -> tuple[pd.DataFrame, str | None]:
    """
    Usa auto_adjust=False (preços brutos) para evitar distorções de dividendos mensais.
    Retorna (prices_df, ifix_base_name) onde ifix_base_name é o ticker sem .SA (ex: "XFIX11").
    """
    # Detecta qual ticker IFIX tem dados disponíveis
    ifix_ticker = None
    for candidate in _IFIX_CANDIDATES:
        test = yf.download(candidate, start=start, end=end, interval="1mo",
                           progress=False, auto_adjust=False)
        if not test.empty and len(test) > 3:
            ifix_ticker = candidate
            print(f"[backtest_fii] Benchmark IFIX: {candidate}")
            break
    if ifix_ticker is None:
        print("[backtest_fii] AVISO: nenhum benchmark IFIX encontrado — gráfico sem referência")

    ifix_base = ifix_ticker.replace(".SA", "") if ifix_ticker else None

    print(f"[backtest_fii] Baixando preços para {len(tickers)} tickers...")
    sa_tickers = [_sa(t) for t in tickers]
    if ifix_ticker:
        sa_tickers.append(ifix_ticker)

    raw = yf.download(sa_tickers, start=start, end=end, interval="1mo",
                      progress=False, auto_adjust=False)

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"].copy()
    else:
        prices = raw[["Close"]].copy()

    prices.index = pd.to_datetime(prices.index)

    rename_map = {}
    for c in prices.columns:
        cs = str(c)
        if ifix_base and ifix_base in cs:
            rename_map[c] = "IFIX"
        elif cs.endswith(".SA"):
            rename_map[c] = cs[:-3]
    if rename_map:
        prices = prices.rename(columns=rename_map)

    return prices, ifix_base


# ── Dividendos com cache ──────────────────────────────────────────────────────

def fetch_dividends(tickers: list[str]) -> dict[str, pd.Series]:
    print(f"[backtest_fii] Buscando dividendos para {len(tickers)} tickers...")
    result: dict[str, pd.Series] = {}

    for i, ticker in enumerate(tickers):
        cache_path = CACHE_DIR / f"{ticker}_div.json"
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) / 3600 < 48:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            s = pd.Series(data, dtype=float)
            s.index = pd.to_datetime(s.index)
            result[ticker] = s
        else:
            try:
                t = yf.Ticker(_sa(ticker))
                divs = t.dividends
                if divs is not None and not divs.empty:
                    divs.index = divs.index.tz_localize(None) if divs.index.tz else divs.index
                    result[ticker] = divs
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump({str(k.date()): float(v) for k, v in divs.items()}, f)
                else:
                    result[ticker] = pd.Series(dtype=float)
            except Exception:
                result[ticker] = pd.Series(dtype=float)

        if (i + 1) % 20 == 0:
            print(f"[backtest_fii]   {i+1}/{len(tickers)} dividendos")
        time.sleep(0.15)

    filled = sum(1 for s in result.values() if not s.empty)
    print(f"[backtest_fii] {filled}/{len(tickers)} tickers com histórico de dividendos")
    return result


# ── DY helpers ───────────────────────────────────────────────────────────────

def _dy_monthly_at(
    ticker: str,
    rebal_dt: pd.Timestamp,
    next_dt: pd.Timestamp,
    dividends: dict,
    price: float | None,
) -> float | None:
    """DY mensal: dividendos pagos no período / preço."""
    divs = dividends.get(ticker, pd.Series(dtype=float))
    if divs.empty or price is None or price <= 0:
        return None
    period_divs = divs[(divs.index > rebal_dt) & (divs.index <= next_dt)].sum()
    return round(period_divs / price * 100, 2) if period_divs > 0 else None


def _dy_limpo_at(ticker: str, cutoff: date, dividends: dict, price: float | None) -> float | None:
    """Trailing 12M DY Limpo (IQR) na data cutoff."""
    divs = dividends.get(ticker, pd.Series(dtype=float))
    if divs.empty or price is None or price <= 0:
        return None

    end_dt   = pd.Timestamp(cutoff)
    start_24 = end_dt - pd.DateOffset(months=24)
    start_12 = end_dt - pd.DateOffset(months=12)

    divs_24m = divs[(divs.index >= start_24) & (divs.index <= end_dt)]
    if len(divs_24m) < 3:
        return None

    # Limiar IQR calculado na janela 24M
    vals = divs_24m.values
    q1, q3 = np.percentile(vals, 25), np.percentile(vals, 75)
    iqr    = q3 - q1
    upper  = q3 + 1.5 * iqr

    # Soma limpa dos últimos 12M
    divs_12m  = divs[(divs.index >= start_12) & (divs.index <= end_dt)]
    clean_12m = divs_12m[divs_12m.values <= upper]

    if clean_12m.empty:
        return None

    return round(clean_12m.sum() / price * 100, 2)


# ── Ranking numa data ─────────────────────────────────────────────────────────

def rank_at_date(
    tickers: list[str],
    cutoff: date,
    dividends: dict,
    prices_df: pd.DataFrame,
    pvp_current: dict[str, float | None],
    vpa_current: dict[str, float | None],
    top_n: int = 10,
) -> list[dict]:
    price_row = prices_df[prices_df.index.date <= cutoff]
    if price_row.empty:
        return []
    price_row = price_row.iloc[-1]

    metrics = []
    for ticker in tickers:
        if not _VALID_FII.match(ticker):
            continue
        price = _safe_float(price_row.get(ticker))
        if price is None or price < 5:   # exclui FIIs em liquidação (preço < R$5)
            continue

        # P/VP histórico estimado: preço_na_data / VPA_atual (VPA muda devagar)
        vpa = vpa_current.get(ticker)
        if vpa and vpa > 0:
            pvp_hist = price / vpa
        else:
            pvp_hist = pvp_current.get(ticker)  # fallback: P/VP snapshot atual

        # Filtro P/VP < 0.9 — mesmo critério do screener live
        if pvp_hist is None or pvp_hist >= 0.9:
            continue

        dy = _dy_limpo_at(ticker, cutoff, dividends, price)
        if dy is None or dy <= 0 or dy > 50:  # IQR já filtra amortização; 50% só bloqueia erros de dados
            continue
        metrics.append({
            "TICKER":   ticker,
            "dy_limpo": dy,
            "pvp":      round(pvp_hist, 3),
            "preco":    round(price, 2) if price else None,
        })

    metrics.sort(key=lambda x: x["dy_limpo"], reverse=True)
    return metrics[:top_n]


# ── Loop principal ────────────────────────────────────────────────────────────

def run_backtest(
    tickers: list[str],
    pvp_current: dict[str, float | None],
    vpa_current: dict[str, float | None],
    start: str = "2022-01-01",
    end: str | None = None,
    top_n: int = 10,
    hold_buffer: float = 1.5,
) -> dict:
    end      = end or str(date.today())
    buffer_n = int(top_n * hold_buffer)

    prices_df, ifix_base = fetch_prices(tickers, start, end)
    div_tickers = list(tickers) + ([ifix_base] if ifix_base else [])
    dividends = fetch_dividends(div_tickers)

    rebal_dates = pd.date_range(start=start, end=end, freq="ME")
    if rebal_dates.empty:
        return {}

    monthly_results = []
    portfolio: set[str] = set()
    portfolio_value      = 100.0
    portfolio_price_val  = 100.0   # acumula só valorização de preço
    portfolio_dy_val     = 100.0   # acumula só retorno de DY
    first_active_date    = None

    for i, rebal_dt in enumerate(rebal_dates[:-1]):
        cutoff  = rebal_dt.date()
        next_dt = rebal_dates[i + 1]

        all_ranked  = rank_at_date(tickers, cutoff, dividends, prices_df, pvp_current, vpa_current, top_n=buffer_n)
        buffer_set  = {r["TICKER"] for r in all_ranked}
        ranked_list = [r["TICKER"] for r in all_ranked]

        keep  = portfolio & buffer_set
        slots = top_n - len(keep)
        new_portfolio: set[str] = set(keep)
        for t in ranked_list:
            if slots <= 0:
                break
            if t not in new_portfolio:
                new_portfolio.add(t)
                slots -= 1

        entries    = new_portfolio - portfolio
        exits      = portfolio - new_portfolio
        top_detail = [r for r in all_ranked if r["TICKER"] in new_portfolio]

        cur_row = prices_df[prices_df.index.date <= cutoff]
        cur_row = cur_row.iloc[-1] if not cur_row.empty else pd.Series(dtype=float)

        if new_portfolio and first_active_date is None:
            first_active_date = str(cutoff)

        # Retorno do portfolio anterior — rastreia preço e DY separadamente
        monthly_return      = None
        monthly_price_ret   = None
        monthly_dy_ret      = None
        if portfolio:
            price_rets = []
            dy_rets    = []
            for t in portfolio:
                if t in prices_df.columns:
                    p0_s = prices_df.loc[prices_df.index <= rebal_dt, t]
                    p1_s = prices_df.loc[prices_df.index <= next_dt, t]
                    p0   = _safe_float(p0_s.iloc[-1]) if not p0_s.empty else None
                    p1   = _safe_float(p1_s.iloc[-1]) if not p1_s.empty else None
                    if p0 and p1 and p0 > 0:
                        pr = (p1 - p0) / p0
                        # Dividendos pagos no período
                        divs_t = dividends.get(t, pd.Series(dtype=float))
                        dr = 0.0
                        if not divs_t.empty:
                            period_divs = divs_t[
                                (divs_t.index > rebal_dt) & (divs_t.index <= next_dt)
                            ].sum()
                            dr = period_divs / p0
                        total_ret = pr + dr
                        # Cap ±50%: filtra eventos corporativos e erros de dados
                        if -0.50 <= total_ret <= 0.50:
                            price_rets.append(pr)
                            dy_rets.append(dr)
            if price_rets:
                monthly_price_ret = np.mean(price_rets) * 100
                monthly_dy_ret    = np.mean(dy_rets) * 100
                monthly_return    = monthly_price_ret + monthly_dy_ret

        if monthly_return is not None:
            portfolio_value     *= (1 + monthly_return / 100)
        if monthly_price_ret is not None:
            portfolio_price_val *= (1 + monthly_price_ret / 100)
        if monthly_dy_ret is not None:
            portfolio_dy_val    *= (1 + monthly_dy_ret / 100)

        # IFIX benchmark — total return (preço + dividendos XFIX11)
        ifix_ret = None
        if "IFIX" in prices_df.columns:
            ib0_s = prices_df.loc[prices_df.index <= rebal_dt, "IFIX"]
            ib1_s = prices_df.loc[prices_df.index <= next_dt, "IFIX"]
            ib0   = _safe_float(ib0_s.iloc[-1]) if not ib0_s.empty else None
            ib1   = _safe_float(ib1_s.iloc[-1]) if not ib1_s.empty else None
            if ib0 and ib1 and ib0 > 0:
                ifix_price_ret = (ib1 - ib0) / ib0
                # Adiciona dividendos XFIX11 (total return)
                if ifix_base:
                    ifix_divs = dividends.get(ifix_base, pd.Series(dtype=float))
                    if not ifix_divs.empty:
                        ifix_period_divs = ifix_divs[
                            (ifix_divs.index > rebal_dt) & (ifix_divs.index <= next_dt)
                        ].sum()
                        ifix_price_ret += ifix_period_divs / ib0
                ifix_ret = ifix_price_ret * 100

        precos_saida = {}
        for t in exits:
            p = _safe_float(cur_row.get(t))
            if p:
                precos_saida[t] = round(p, 2)

        # DY mensal médio da carteira (dividendos pagos no período)
        dy_vals_mensal = []
        for r in top_detail:
            dy_m = _dy_monthly_at(r["TICKER"], rebal_dt, next_dt, dividends, r.get("preco"))
            if dy_m is not None:
                dy_vals_mensal.append(dy_m)
        dy_medio = round(np.mean(dy_vals_mensal), 2) if dy_vals_mensal else None

        # DY mensal IFIX (XFIX11)
        ifix_price_now = _safe_float(cur_row.get("IFIX")) if "IFIX" in cur_row.index else None
        ifix_dy = _dy_monthly_at(ifix_base, rebal_dt, next_dt, dividends, ifix_price_now) if ifix_base else None

        monthly_results.append({
            "data":                     str(cutoff),
            "top15":                    sorted(new_portfolio),
            "entradas":                 sorted(entries),
            "saidas":                   sorted(exits),
            "precos_saida":             precos_saida,
            "retorno_mes_pct":          round(monthly_return, 2) if monthly_return is not None else None,
            "retorno_preco_mes_pct":    round(monthly_price_ret, 2) if monthly_price_ret is not None else None,
            "retorno_dy_mes_pct":       round(monthly_dy_ret, 2) if monthly_dy_ret is not None else None,
            "portfolio_valor":          round(portfolio_value, 2),
            "portfolio_preco_valor":    round(portfolio_price_val, 2),
            "portfolio_dy_valor":       round(portfolio_dy_val, 2),
            "ifix_retorno_mes_pct":     round(ifix_ret, 2) if ifix_ret is not None else None,
            "dy_medio_pct":             dy_medio,
            "ifix_dy_pct":              ifix_dy,
            "detalhes": [
                {
                    "ticker":   r["TICKER"],
                    "dy_limpo": r["dy_limpo"],
                    "pvp":      r.get("pvp"),
                    "preco":    r.get("preco"),
                }
                for r in top_detail
            ],
        })

        portfolio = new_portfolio
        ret_str   = f"{monthly_return:.1f}%" if monthly_return is not None else "N/A"
        print(f"[backtest_fii] {cutoff} | top{top_n}: {len(new_portfolio)} | retorno: {ret_str} | portfolio: {portfolio_value:.1f}")

    # ── Estatísticas ──────────────────────────────────────────────────────────
    retornos    = [r["retorno_mes_pct"] for r in monthly_results if r["retorno_mes_pct"] is not None]
    total_return = portfolio_value - 100

    ifix_acc = 100.0
    ifix_vals = []
    for r in monthly_results:
        if r["ifix_retorno_mes_pct"] is not None:
            ifix_acc *= (1 + r["ifix_retorno_mes_pct"] / 100)
        ifix_vals.append(round(ifix_acc, 2))
    ifix_total = ifix_acc - 100

    peak   = 100.0
    max_dd = 0.0
    for r in [x for x in monthly_results if x.get("top15")]:
        v  = r["portfolio_valor"]
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    periodo_start = first_active_date or start
    retorno_preco_total = portfolio_price_val - 100
    retorno_dy_total    = portfolio_dy_val - 100
    stats = {
        "periodo":                  f"{periodo_start} ate {end}",
        "periodo_completo":         f"{start} ate {end}",
        "meses":                    len(retornos),
        "retorno_total_pct":        round(total_return, 2),
        "retorno_preco_total_pct":  round(retorno_preco_total, 2),
        "retorno_dy_total_pct":     round(retorno_dy_total, 2),
        "ifix_total_pct":           round(ifix_total, 2),
        "alpha_pct":                round(total_return - ifix_total, 2),
        "retorno_medio_mensal_pct": round(np.mean(retornos), 2) if retornos else None,
        "volatilidade_mensal_pct":  round(np.std(retornos), 2) if retornos else None,
        "max_drawdown_pct":         round(max_dd, 2),
        "meses_positivos":          sum(1 for r in retornos if r > 0),
        "meses_negativos":          sum(1 for r in retornos if r < 0),
        "hold_buffer":              hold_buffer,
        "top_n":                    top_n,
    }

    return {
        "stats":           stats,
        "monthly":         monthly_results,
        "ifix_acumulado":  ifix_vals,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

_MIN_LIQUIDEZ_UNIV = 500_000   # R$500k/dia — exclui FIIs em liquidação
_MIN_PATRIM_UNIV   = 100_000_000  # R$100M patrimônio mínimo


def _row_valido(r: dict) -> bool:
    """Filtra ticker válido + liquidez + patrimônio mínimos."""
    if not _VALID_FII.match(r.get("TICKER", "")):
        return False
    liq    = _safe_float(r.get("LIQUIDEZ"))
    patrim = _safe_float(r.get("PATRIMONIO"))
    if liq is not None and liq < _MIN_LIQUIDEZ_UNIV:
        return False
    if patrim is not None and patrim < _MIN_PATRIM_UNIV:
        return False
    return True


def _load_universe() -> tuple[list[str], dict, dict]:
    """Carrega universo de FIIs: Fundamentus cache + yfinance cache mesclados.
    Retorna (tickers, pvp_current, vpa_current).
    """
    tickers_set: set[str] = set()
    pvp_current: dict[str, float | None] = {}
    vpa_current: dict[str, float | None] = {}

    # Fonte 1: Fundamentus cache mensal
    cache_files = sorted(glob.glob(str(ROOT / "data" / "fii_cache" / "????_??.json")))
    if cache_files:
        with open(cache_files[-1], encoding="utf-8") as f:
            data = json.load(f)
        rows = [r for r in data.get("rows", []) if _row_valido(r)]
        for r in rows:
            t = r["TICKER"]
            tickers_set.add(t)
            pvp_current[t] = _safe_float(r.get("PVP"))
            vpa_current[t] = _safe_float(r.get("VPA"))
        print(f"[backtest_fii] Fundamentus: {len(rows)} FIIs — {Path(cache_files[-1]).name}")

    # Fonte 2: yfinance cache por ticker (output/fii_yf_cache/)
    yf_cache_dir = ROOT / "output" / "fii_yf_cache"
    if yf_cache_dir.exists():
        added = 0
        for jf in yf_cache_dir.glob("*.json"):
            try:
                with open(jf, encoding="utf-8") as f:
                    r = json.load(f)
                if not _row_valido(r):
                    continue
                t = r.get("TICKER", "")
                if not t:
                    continue
                if t not in tickers_set:
                    tickers_set.add(t)
                    added += 1
                # yfinance cache tem VPA mais atualizado — prefere sobre Fundamentus
                pvp_yf = _safe_float(r.get("PVP"))
                vpa_yf = _safe_float(r.get("VPA"))
                if pvp_yf is not None:
                    pvp_current[t] = pvp_yf
                if vpa_yf is not None:
                    vpa_current[t] = vpa_yf
            except Exception:
                continue
        if added:
            print(f"[backtest_fii] yfinance cache: +{added} FIIs adicionais")

    if tickers_set:
        tickers = sorted(tickers_set)
        vpa_filled = sum(1 for v in vpa_current.values() if v is not None)
        print(f"[backtest_fii] Universo total: {len(tickers)} FIIs | VPA disponível: {vpa_filled}")
        return tickers, pvp_current, vpa_current

    # Último fallback: fii_candidates.json
    cand_path = ROOT / "output" / "fii_candidates.json"
    if cand_path.exists():
        with open(cand_path, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("top10", [])
        tickers = [r["TICKER"] for r in rows]
        pvp_current = {r["TICKER"]: _safe_float(r.get("PVP")) for r in rows}
        vpa_current = {r["TICKER"]: _safe_float(r.get("VPA")) for r in rows}
        print(f"[backtest_fii] Universo (fallback): {len(tickers)} candidatos")
        return tickers, pvp_current, vpa_current

    raise FileNotFoundError("Nenhum cache de FIIs encontrado. Execute fii_main.py primeiro.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest FII — DY Limpo vs IFIX")
    parser.add_argument("--start",       default="2023-01-01")
    parser.add_argument("--end",         default=str(date.today()))
    parser.add_argument("--top",         type=int,   default=10)
    parser.add_argument("--hold-buffer", type=float, default=1.5)
    parser.add_argument("--output",      default=str(ROOT / "output" / "backtest_fii.json"))
    args = parser.parse_args()

    tickers, pvp_current, vpa_current = _load_universe()

    result = run_backtest(
        tickers,
        pvp_current,
        vpa_current,
        start=args.start,
        end=args.end,
        top_n=args.top,
        hold_buffer=args.hold_buffer,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[backtest_fii] Resultado salvo: {args.output}")
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
