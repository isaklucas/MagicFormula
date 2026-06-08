"""
Enriquece FIIs/FIAgros com dados yfinance:
- Fase 1 (rápida): P/VP + preço via .info para todos os fundos
- Fase 2 (completa): dividendos 24M + idade via history(max, actions=True)

Usar em duas fases para reduzir chamadas:
  1. get_pvp_batch(all_tickers)  →  filtra P/VP < 0.90  (0.3s por ticker)
  2. enrich_fiis(filtered_tickers)  →  dados completos  (1.0s por ticker)
"""

import time
import warnings
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")


def _ticker_sa(ticker: str) -> str:
    t = ticker.upper().strip()
    return t if t.endswith(".SA") else t + ".SA"


# ── Fase 1: scan rápido P/VP ─────────────────────────────────────────────────

def get_pvp_batch(tickers: list[str], delay: float = 0.3) -> dict[str, dict]:
    """
    Busca P/VP + preço via yfinance .info para lista de tickers.
    Retorna {ticker: {"pvp": float|None, "preco": float|None}}.
    Delay baixo (0.3s) pois só faz uma chamada leve por fundo.
    """
    results: dict[str, dict] = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        print(f"\r[fii_enricher] P/VP scan {i}/{total} ({ticker})    ", end="", flush=True)
        try:
            info  = yf.Ticker(_ticker_sa(ticker)).info or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            book  = info.get("bookValue")
            ptb   = info.get("priceToBook")

            if ptb is not None:
                pvp = round(float(ptb), 4)
            elif price and book and float(book) > 0:
                pvp = round(float(price) / float(book), 4)
            else:
                pvp = None

            results[ticker] = {
                "pvp":   pvp,
                "preco": round(float(price), 2) if price else None,
            }
        except Exception:
            results[ticker] = {"pvp": None, "preco": None}

        time.sleep(delay)

    print(f"\r[fii_enricher] P/VP scan concluído: {total} fundos          ")
    return results


# ── Fase 2: enriquecimento completo ──────────────────────────────────────────

def enrich_fii(ticker: str) -> dict:
    """
    Coleta dividendos 24M + idade via uma única chamada history(max, actions=True).
    Nunca lança exceção — retorna erro em result["erro"].
    """
    result: dict = {
        "ticker":          ticker,
        "dividendos_24m":  pd.Series(dtype=float),
        "idade_dias":      -1,
        "preco_yf":        None,
        "ultimo_div":      None,
        "data_ultimo_div": None,
        "erro":            None,
    }
    try:
        yft  = yf.Ticker(_ticker_sa(ticker))
        hist = yft.history(period="max", auto_adjust=True, actions=True)

        if hist.empty:
            result["erro"] = "sem historico"
            return result

        # Idade: data mais antiga do histórico
        oldest = hist.index.min()
        if oldest.tzinfo is None:
            oldest = oldest.tz_localize("UTC")
        result["idade_dias"] = int((pd.Timestamp.now(tz="UTC") - oldest).days)

        # Preço: fechamento mais recente
        result["preco_yf"] = round(float(hist["Close"].iloc[-1]), 2)

        # Dividendos: coluna "Dividends" do history com actions=True
        if "Dividends" in hist.columns:
            all_divs = hist["Dividends"][hist["Dividends"] > 0]
            if not all_divs.empty:
                if all_divs.index.tz is None:
                    all_divs.index = all_divs.index.tz_localize("UTC")
                cutoff   = pd.Timestamp.now(tz="UTC") - pd.DateOffset(months=24)
                divs_24m = all_divs[all_divs.index >= cutoff].copy()
                result["dividendos_24m"] = divs_24m
                if not divs_24m.empty:
                    result["ultimo_div"]      = round(float(divs_24m.iloc[-1]), 4)
                    result["data_ultimo_div"] = divs_24m.index[-1].strftime("%d/%m/%Y")

    except Exception as e:
        result["erro"] = str(e)

    return result


def enrich_fiis(tickers: list[str], delay: float = 1.0) -> dict[str, dict]:
    """Enriquece lista de tickers com dados completos. Retorna {ticker: dados}."""
    results: dict[str, dict] = {}
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        print(f"[fii_enricher] {ticker} ({i}/{total})...", end=" ", flush=True)
        data = enrich_fii(ticker)
        n_divs = len(data["dividendos_24m"])
        age    = data["idade_dias"]
        preco  = data["preco_yf"]
        erro   = data.get("erro") or ""
        status = f"divs={n_divs}  idade={age}d  preco={preco}" + (f"  ERRO={erro}" if erro else "")
        print(status)
        results[ticker] = data
        time.sleep(delay)
    return results
