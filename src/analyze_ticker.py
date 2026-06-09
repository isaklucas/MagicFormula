"""
Analise ad-hoc de qualquer ticker B3 via yfinance.
Nao requer CSV do StatusInvest. Usado pela skill /analisa-ticker.

Uso: python src/analyze_ticker.py ITSA4 TIMS3 WIZC3
Salva output/analyze_ticker_cache.json com dados prontos para o agente.
"""

import sys
import json
import math
import warnings
import time
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

import yfinance as yf
from enricher import enrich_ticker, format_for_agent, _compute_roic_quarterly


def _safe(val, default=None):
    if val is None:
        return default
    if isinstance(val, float) and math.isnan(val):
        return default
    return val


def _cagr(v_start, v_end, years: int):
    """CAGR entre dois valores. Retorna None se dados insuficientes."""
    try:
        if not v_start or not v_end or years <= 0:
            return None
        if v_start <= 0 or v_end <= 0:
            return None
        return round((v_end / v_start) ** (1.0 / years) * 100 - 100, 2)
    except Exception:
        return None


def fetch_ticker_fundamentals(ticker: str) -> dict | None:
    """
    Busca dados fundamentais de um ticker B3 via yfinance.
    Retorna dict com mesmas chaves-chave de candidates.json, ou None se falhar.
    """
    yf_sym = ticker.upper()
    if not yf_sym.endswith(".SA"):
        yf_sym += ".SA"

    try:
        t = yf.Ticker(yf_sym)
        info = t.info or {}

        if not info or info.get("quoteType") is None:
            print(f"[analyze] {ticker}: nao encontrado no yfinance")
            return None

        mktcap   = _safe(info.get("marketCap"))
        ev       = _safe(info.get("enterpriseValue"))
        price    = _safe(info.get("currentPrice")) or _safe(info.get("regularMarketPrice"))
        roe      = _safe(info.get("returnOnEquity"))
        total_debt = _safe(info.get("totalDebt"), 0)
        total_cash = _safe(info.get("totalCash"), 0)
        op_margin  = _safe(info.get("operatingMargins"))
        avg_vol    = _safe(info.get("averageVolume10days")) or _safe(info.get("averageVolume"))

        # EBIT TTM via financials trimestrais (soma dos 4 ultimos)
        ebit_ttm = None
        qf = qbs = None
        try:
            qf  = t.quarterly_financials
            qbs = t.quarterly_balance_sheet
            if qf is not None and "EBIT" in qf.index:
                ebit_series = qf.loc["EBIT"].dropna()
                if len(ebit_series) >= 4:
                    ebit_ttm = float(ebit_series.iloc[:4].sum())
        except Exception:
            pass

        # EV/EBIT
        ev_ebit = None
        if ev and ebit_ttm and ebit_ttm > 0:
            ev_ebit = round(ev / ebit_ttm, 2)

        # ROIC via logica do enricher (ultimo trimestre anualizado)
        roic_val = None
        try:
            if qf is not None and qbs is not None:
                roic_list = _compute_roic_quarterly(qf, qbs, n=4)
                if roic_list:
                    # media dos ultimos 4 trimestres anualizada
                    roic_val = round(sum(roic_list) / len(roic_list), 2)
        except Exception:
            pass

        # Margem EBIT
        margem_ebit = round(op_margin * 100, 2) if op_margin is not None else None

        # ROE
        roe_pct = round(roe * 100, 2) if roe is not None else None

        # Divida Liquida / EBIT
        div_ebit = None
        if ebit_ttm and ebit_ttm != 0:
            net_debt = (total_debt or 0) - (total_cash or 0)
            div_ebit = round(net_debt / ebit_ttm, 2)

        # CAGR Receitas e Lucros 5a via demonstrativo anual
        cagr_rec = cagr_luc = None
        try:
            ann = t.financials  # mais recente primeiro (colunas)
            if ann is not None and ann.shape[1] >= 2:
                rev_keys = [k for k in ann.index if "Revenue" in k and "Total" in k]
                if rev_keys:
                    rev = ann.loc[rev_keys[0]].dropna()
                    yrs = min(5, len(rev) - 1)
                    if yrs > 0:
                        cagr_rec = _cagr(float(rev.iloc[yrs]), float(rev.iloc[0]), yrs)

                net_keys = [k for k in ann.index if "Net Income" in k]
                if net_keys:
                    net = ann.loc[net_keys[0]].dropna()
                    yrs = min(5, len(net) - 1)
                    if yrs > 0:
                        cagr_luc = _cagr(float(net.iloc[yrs]), float(net.iloc[0]), yrs)
        except Exception:
            pass

        # Liquidez media diaria aproximada
        liquidez = round(avg_vol * price) if avg_vol and price else None

        return {
            "TICKER":                   ticker.upper(),
            "EV/EBIT":                  ev_ebit,
            "ROIC":                     roic_val,
            "MARGEM EBIT":              margem_ebit,
            "ROE":                      roe_pct,
            "DIVIDA LIQUIDA / EBIT":    div_ebit,
            "CAGR RECEITAS 5 ANOS":     cagr_rec,
            "CAGR LUCROS 5 ANOS":       cagr_luc,
            "VALOR DE MERCADO":         mktcap,
            "LIQUIDEZ MEDIA DIARIA":    liquidez,
            "PRECO":                    price,
            "setor":                    _safe(info.get("sector"), "Desconhecido"),
        }

    except Exception as e:
        print(f"[analyze] {ticker}: erro - {e}")
        return None


def build_candidates(tickers: list[str], delay: float = 1.5) -> list[dict]:
    """
    Para cada ticker: busca fundamentais + enriquece com yfinance.
    Retorna lista de dicts prontos para o prompt do agente.
    """
    results = []
    for ticker in tickers:
        print(f"[analyze] {ticker}: buscando fundamentais...")
        data = fetch_ticker_fundamentals(ticker)
        if data is None:
            continue

        print(f"[analyze] {ticker}: enriquecendo historico...")
        enriched = enrich_ticker(ticker)
        data["contexto_agente"] = format_for_agent(ticker, enriched, data)
        data["historico"] = enriched
        results.append(data)
        time.sleep(delay)

    return results


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    tickers = [t.upper() for t in sys.argv[1:]] if len(sys.argv) > 1 else ["ITSA4"]
    print(f"[analyze] Tickers: {tickers}")

    candidates = build_candidates(tickers)
    if not candidates:
        print("Nenhum ticker valido encontrado.")
        sys.exit(1)

    # Salva cache
    out_path = ROOT / "output" / "analyze_ticker_cache.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"tickers": tickers, "candidatos": candidates}, f, ensure_ascii=False, indent=2)

    print(f"\n[analyze] Salvo: {out_path}")
    print(f"[analyze] {len(candidates)} tickers prontos\n")

    # Sumario
    for c in candidates:
        ev   = c.get("EV/EBIT")
        roic = c.get("ROIC")
        div  = c.get("DIVIDA LIQUIDA / EBIT")
        print(f"  {c['TICKER']}: EV/EBIT={ev}x | ROIC={roic}% | Div/EBIT={div}x | Setor={c.get('setor','?')}")
