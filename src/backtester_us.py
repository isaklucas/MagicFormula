"""
Backtester Magic Formula US (S&P 500 ou qualquer universo US).
Aceita --benchmark para escolher o índice de comparação.
Benchmark padrão: ^GSPC (S&P 500). Para small cap: ^SP600.

Limitacao: survivorship bias — universo fixo nos tickers atuais.
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
sys.path.insert(0, str(Path(__file__).parent))
CACHE_DIR = ROOT / "output" / "backtest_cache_us"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

from filters import apply_sector_limit

TAX_RATE = 0.25         # mesma aliquota dos loaders US (ebit * 0.75)
MAX_PER_SECTOR = 3      # mesmo teto do main_sp500.py / main_smallcap.py

# Guarda de outlier: EV/EBIT abaixo de 1 nao existe em empresa sa — e EBIT contaminado
# por ganho nao-operacional. NAO usar teto de ROIC aqui: ROIC alto sozinho e sinal de
# empresa otima, nao de dado ruim (a Apple opera acima de 100% por causa das recompras,
# que encolhem o patrimonio liquido).
MIN_EV_EBIT = 1.0

EQUITY_ROWS = ("Stockholders Equity", "Total Equity Gross Minority Interest")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return f if not np.isnan(f) else None
    except Exception:
        return None


# ── Cache de fundamentals ─────────────────────────────────────────────────────

def _cache_path(ticker: str, cache_dir: Path) -> Path:
    return cache_dir / f"{ticker}.json"


def _load_cache(ticker: str, cache_dir: Path) -> dict | None:
    p = _cache_path(ticker, cache_dir)
    if not p.exists():
        return None
    age_hours = (time.time() - p.stat().st_mtime) / 3600
    if age_hours > 48:
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save_cache(ticker: str, data: dict, cache_dir: Path):
    with open(_cache_path(ticker, cache_dir), "w", encoding="utf-8") as f:
        json.dump(data, f)


# ── Fetch fundamental data por ticker ─────────────────────────────────────────

def _fetch_fundamentals(ticker: str, cache_dir: Path) -> dict:
    """
    Versao 3: inclui patrimonio liquido (equity), para calcular capital investido com
    divida liquida e descartar PL negativo na data do rebalance.
    """
    cached = _load_cache(ticker, cache_dir)
    if cached and cached.get("_v") == 3:
        return cached

    result = {"ebit_q": {}, "ebit_a": {}, "inv_cap": {}, "net_debt": {}, "shares": {}, "equity": {}, "_v": 3}
    try:
        t = yf.Ticker(ticker)

        qf = t.quarterly_financials
        qbs = t.quarterly_balance_sheet

        if not qf.empty and "EBIT" in qf.index:
            for col, val in qf.loc["EBIT"].items():
                v = _safe_float(val)
                if v is not None:
                    result["ebit_q"][str(col.date())] = v

        bs_rows = [
            ("Invested Capital", "inv_cap"),
            ("Net Debt", "net_debt"),
            ("Ordinary Shares Number", "shares"),
        ] + [(row, "equity") for row in EQUITY_ROWS]  # 1o nome vence; 2o so preenche lacunas

        if not qbs.empty:
            for row, key in bs_rows:
                if row in qbs.index:
                    for col, val in qbs.loc[row].items():
                        v = _safe_float(val)
                        if v is not None:
                            date_str = str(col.date())
                            if date_str not in result[key]:
                                result[key][date_str] = v

        af = t.financials
        abs_ = t.balance_sheet

        if not af.empty and "EBIT" in af.index:
            for col, val in af.loc["EBIT"].items():
                v = _safe_float(val)
                if v is not None:
                    result["ebit_a"][str(col.date())] = v

        if not abs_.empty:
            for row, key in bs_rows:
                if row in abs_.index:
                    for col, val in abs_.loc[row].items():
                        v = _safe_float(val)
                        if v is not None:
                            date_str = str(col.date())
                            if date_str not in result[key]:
                                result[key][date_str] = v

    except Exception:
        pass

    _save_cache(ticker, result, cache_dir)
    return result


def _ttm_ebit_at(fund: dict, cutoff: date) -> float | None:
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

    valid_a = {
        datetime.strptime(k, "%Y-%m-%d").date(): v
        for k, v in ebit_a.items()
        if datetime.strptime(k, "%Y-%m-%d").date() <= cutoff
    }
    if valid_a:
        return valid_a[max(valid_a.keys())]

    if valid_q:
        return sum(v for _, v in valid_q) * (4 / len(valid_q))

    return None


def _latest_before(series: dict, cutoff: date) -> float | None:
    valid = {
        datetime.strptime(k, "%Y-%m-%d").date(): v
        for k, v in series.items()
        if datetime.strptime(k, "%Y-%m-%d").date() <= cutoff
    }
    if not valid:
        return None
    return valid[max(valid.keys())]


# ── Fetch precos mensais ───────────────────────────────────────────────────────

def fetch_prices(tickers: list[str], start: str, end: str,
                 benchmark: str = "^GSPC", benchmark_col: str = "BENCHMARK") -> pd.DataFrame:
    """Retorna DataFrame de precos mensais. Inclui BENCHMARK e TBILL (^IRX)."""
    print(f"[backtest_us] Baixando precos mensais para {len(tickers)} tickers + {benchmark} + ^IRX...")
    all_tickers = tickers + [benchmark, "^IRX"]
    raw = yf.download(all_tickers, start=start, end=end, interval="1mo", progress=False, auto_adjust=True)

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"].copy()
    else:
        prices = raw[["Close"]].copy()

    prices.index = pd.to_datetime(prices.index)

    rename_map = {}
    for c in prices.columns:
        cs = str(c)
        bm_clean = benchmark.lstrip("^")
        if benchmark in cs or bm_clean == cs:
            rename_map[c] = benchmark_col
        elif "^IRX" in cs or cs == "IRX":
            rename_map[c] = "TBILL"
    if rename_map:
        prices = prices.rename(columns=rename_map)

    return prices


# ── Metricas em cutoff ─────────────────────────────────────────────────────────

def compute_metrics_at(ticker: str, cutoff: date, fundamentals: dict,
                       price: float | None) -> dict | None:
    fund = fundamentals.get(ticker, {})
    ebit = _ttm_ebit_at(fund, cutoff)
    net_debt = _latest_before(fund.get("net_debt", {}), cutoff)
    shares = _latest_before(fund.get("shares", {}), cutoff)
    equity = _latest_before(fund.get("equity", {}), cutoff)

    # Capital investido = patrimonio liquido + divida LIQUIDA. A linha "Invested Capital"
    # do yfinance usa divida BRUTA e ignora o caixa, o que infla o capital de empresas
    # cheias de caixa (metade do S&P 500) e corta o ROIC delas pela metade.
    if equity is not None and net_debt is not None:
        inv_cap = equity + net_debt
    else:
        inv_cap = _latest_before(fund.get("inv_cap", {}), cutoff)

    if ebit is None or ebit <= 0: return None
    if inv_cap is None or inv_cap <= 0: return None
    if price is None or price <= 0: return None
    if shares is None or shares <= 0: return None
    # PL negativo na data do rebalance: empresa tecnicamente insolvente. Point-in-time.
    if equity is not None and equity <= 0: return None

    market_cap = price * shares
    ev = market_cap + (net_debt or 0)
    if ev <= 0: return None

    ev_ebit = ev / ebit
    roic = (ebit * (1 - TAX_RATE) / inv_cap) * 100   # NOPAT, igual aos loaders US
    if ev_ebit <= 0 or roic <= 0: return None
    if ev_ebit < MIN_EV_EBIT: return None

    return {"TICKER": ticker, "EV/EBIT": round(ev_ebit, 2), "ROIC": round(roic, 2), "preco": round(price, 2)}


# ── Ranking numa data ─────────────────────────────────────────────────────────

def rank_at_date(tickers: list[str], cutoff: date, fundamentals: dict,
                 prices_df: pd.DataFrame, top_n: int = 20,
                 setor_map: dict[str, str] | None = None) -> list[dict]:
    price_row = prices_df[prices_df.index.date <= cutoff]
    if price_row.empty: return []
    price_row = price_row.iloc[-1]

    metrics = []
    for ticker in tickers:
        price = _safe_float(price_row.get(ticker))
        m = compute_metrics_at(ticker, cutoff, fundamentals, price)
        if m:
            metrics.append(m)

    if not metrics: return []

    df = pd.DataFrame(metrics)
    df["rank_ev"] = df["EV/EBIT"].rank(ascending=True, method="min")
    df["rank_roic"] = df["ROIC"].rank(ascending=False, method="min")
    df["mf_score"] = df["rank_ev"] + df["rank_roic"]

    if not setor_map:
        top = df.nsmallest(top_n, "mf_score").reset_index(drop=True)
        return top.to_dict(orient="records")

    ranked = df.sort_values("mf_score").to_dict(orient="records")
    kept, _ = apply_sector_limit(ranked, setor_map, max_per_sector=MAX_PER_SECTOR, desired_n=top_n)
    return kept


# ── Loop principal ─────────────────────────────────────────────────────────────

def run_backtest(tickers: list[str], start: str = "2023-01-01", end: str | None = None,
                 top_n: int = 15, hold_buffer: float = 2.0,
                 benchmark: str = "^GSPC", benchmark_name: str = "S&P 500",
                 cache_dir: Path = CACHE_DIR,
                 setor_map: dict[str, str] | None = None) -> dict:
    end = end or str(date.today())
    buffer_n = int(top_n * hold_buffer)
    bm_col = "BENCHMARK"

    prices_df = fetch_prices(tickers, start, end, benchmark=benchmark, benchmark_col=bm_col)

    print(f"[backtest_us] Buscando fundamentals para {len(tickers)} tickers...")
    fundamentals = {}
    for i, ticker in enumerate(tickers):
        fundamentals[ticker] = _fetch_fundamentals(ticker, cache_dir)
        if (i + 1) % 10 == 0:
            print(f"[backtest_us]   {i+1}/{len(tickers)} fundamentals carregados")
        time.sleep(0.3)

    rebal_dates = pd.date_range(start=start, end=end, freq="ME")
    if rebal_dates.empty:
        return {}

    monthly_results = []
    portfolio: set[str] = set()
    portfolio_value = 100.0
    first_active_date = None

    for i, rebal_dt in enumerate(rebal_dates[:-1]):
        cutoff = rebal_dt.date()
        next_dt = rebal_dates[i + 1]

        all_ranked = rank_at_date(tickers, cutoff, fundamentals, prices_df,
                                  top_n=buffer_n, setor_map=setor_map)
        buffer_set = {r["TICKER"] for r in all_ranked}
        ranked_tickers = [r["TICKER"] for r in all_ranked]

        keep = portfolio & buffer_set
        slots = top_n - len(keep)
        new_portfolio: set[str] = set(keep)
        for t in ranked_tickers:
            if slots <= 0: break
            if t not in new_portfolio:
                new_portfolio.add(t)
                slots -= 1

        entries = new_portfolio - portfolio
        exits = portfolio - new_portfolio
        top_detail = [r for r in all_ranked if r["TICKER"] in new_portfolio]

        cur_price_row = prices_df[prices_df.index.date <= cutoff]
        cur_price_row = cur_price_row.iloc[-1] if not cur_price_row.empty else pd.Series(dtype=float)

        if new_portfolio and first_active_date is None:
            first_active_date = str(cutoff)

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

        bm_ret = None
        if bm_col in prices_df.columns:
            b0_s = prices_df.loc[prices_df.index <= rebal_dt, bm_col]
            b1_s = prices_df.loc[prices_df.index <= next_dt, bm_col]
            b0 = _safe_float(b0_s.iloc[-1]) if not b0_s.empty else None
            b1 = _safe_float(b1_s.iloc[-1]) if not b1_s.empty else None
            if b0 and b1 and b0 > 0:
                bm_ret = (b1 - b0) / b0 * 100

        tbill_ret = None
        if "TBILL" in prices_df.columns:
            tb_s = prices_df.loc[prices_df.index <= rebal_dt, "TBILL"]
            tbill_ann = _safe_float(tb_s.iloc[-1]) if not tb_s.empty else None
            if tbill_ann and tbill_ann > 0:
                tbill_ret = ((1 + tbill_ann / 100) ** (1 / 12) - 1) * 100

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
            "benchmark_retorno_mes_pct": round(bm_ret, 2) if bm_ret is not None else None,
            "tbill_retorno_mes_pct": round(tbill_ret, 2) if tbill_ret is not None else None,
            "detalhes": [
                {"ticker": r["TICKER"], "ev_ebit": r["EV/EBIT"], "roic": r["ROIC"],
                 "mf_score": r.get("mf_score"), "preco": r.get("preco"), "setor": r.get("setor")}
                for r in top_detail
            ],
        })

        portfolio = new_portfolio
        print(f"[backtest_us] {cutoff} | top{top_n}: {len(new_portfolio)} | +{len(entries)} -{len(exits)} | ret: {f'{monthly_return:.1f}%' if monthly_return is not None else 'N/A'} | port: ${portfolio_value:.1f}")

    active_results = [r for r in monthly_results if r["top15"]]
    retornos = [r["retorno_mes_pct"] for r in monthly_results if r["retorno_mes_pct"] is not None]
    total_return = portfolio_value - 100

    bm_vals = []
    bm_acc = 100.0
    for r in monthly_results:
        if r["benchmark_retorno_mes_pct"] is not None:
            bm_acc *= (1 + r["benchmark_retorno_mes_pct"] / 100)
        bm_vals.append(round(bm_acc, 2))
    bm_total = bm_acc - 100

    tbill_vals = []
    tbill_acc = 100.0
    for r in monthly_results:
        if r["tbill_retorno_mes_pct"] is not None:
            tbill_acc *= (1 + r["tbill_retorno_mes_pct"] / 100)
        tbill_vals.append(round(tbill_acc, 2))
    tbill_total = tbill_acc - 100

    peak = 100.0
    max_dd = 0.0
    for r in active_results:
        v = r["portfolio_valor"]
        if v > peak: peak = v
        dd = (v - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    periodo_start = first_active_date or start
    stats = {
        "periodo": f"{periodo_start} ate {end}",
        "periodo_completo": f"{start} ate {end}",
        "meses": len(retornos),
        "retorno_total_pct": round(total_return, 2),
        "benchmark_name": benchmark_name,
        "benchmark_total_pct": round(bm_total, 2),
        "tbill_total_pct": round(tbill_total, 2),
        "alpha_pct": round(total_return - bm_total, 2),
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
        "benchmark_acumulado": bm_vals,
        "tbill_acumulado": tbill_vals,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", required=True)
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default=str(date.today()))
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--hold-buffer", type=float, default=2.0)
    parser.add_argument("--benchmark", default="SPY", help="ETF de benchmark total return (ex: SPY, IJR)")
    parser.add_argument("--benchmark-name", default="S&P 500 (SPY)", help="Nome legível do benchmark")
    parser.add_argument("--cache-dir", default=str(CACHE_DIR))
    parser.add_argument("--sectors", default=None,
                        help="JSON ticker->setor GICS. Ativa o teto de 3 por setor, igual a carteira ao vivo")
    parser.add_argument("--output", default=str(ROOT / "output" / "backtest_us.json"))
    args = parser.parse_args()

    with open(args.tickers, encoding="utf-8") as f:
        tickers = json.load(f)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    setor_map = None
    if args.sectors and Path(args.sectors).exists():
        with open(args.sectors, encoding="utf-8") as f:
            setor_map = json.load(f)
        print(f"[backtest_us] Teto de {MAX_PER_SECTOR} por setor ativo ({len(setor_map)} tickers mapeados)")
    else:
        print("[backtest_us] Sem mapa de setores — teto por setor desativado")

    result = run_backtest(
        tickers, start=args.start, end=args.end, top_n=args.top,
        hold_buffer=args.hold_buffer, benchmark=args.benchmark,
        benchmark_name=args.benchmark_name, cache_dir=cache_dir,
        setor_map=setor_map,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[backtest_us] Resultado salvo em {args.output}")
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
