import sys
import io
import json
import os
from datetime import date
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from loader import load_csv
from filters import apply_filters, apply_sector_limit
from ranking import compute_magic_formula, to_records
from scraper import check_recuperacao_judicial
from enricher import enrich_candidates, format_for_agent


def _compute_raw_mf_rank_br(df_raw: pd.DataFrame) -> dict[str, int]:
    try:
        df = df_raw[["TICKER", "EV/EBIT", "ROIC"]].dropna()
        df = df[(df["EV/EBIT"] > 0) & (df["ROIC"] > 0)].copy()
        if df.empty:
            return {}
        df["_rev"] = df["EV/EBIT"].rank(ascending=True)
        df["_rroic"] = df["ROIC"].rank(ascending=False)
        df["_score"] = df["_rev"] + df["_rroic"]
        df = df.sort_values("_score").reset_index(drop=True)
        df["_pos"] = df.index + 1
        return dict(zip(df["TICKER"], df["_pos"].astype(int)))
    except Exception:
        return {}


CSV_PATH = ROOT / "data" / "statusinvest-busca-avancada.csv"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=100)
    args = parser.parse_args()
    top_n = args.top

    # Tenta yfinance (xlsx B3) → fallback SI API → fallback CSV
    df_raw = None
    try:
        from yf_fetcher import fetch_all_stocks
        print("[main] Buscando dados via yfinance (EmpresasB3Porsetor.xlsx)...")
        df_raw = fetch_all_stocks()
        print(f"[main] {len(df_raw)} ações carregadas via yfinance")
    except Exception as e:
        print(f"[main] yfinance fetcher falhou: {e}")

    if df_raw is None or df_raw.empty:
        try:
            from si_fetcher import fetch_all_stocks as _si_fetch
            print("[main] Fallback → Status Invest API...")
            df_raw = _si_fetch()
            print(f"[main] {len(df_raw)} ações carregadas via SI API")
        except Exception as e2:
            print(f"[main] SI API falhou: {e2}")

    if df_raw is None or df_raw.empty:
        if CSV_PATH.exists():
            print(f"[main] Fallback → CSV: {CSV_PATH}")
            df_raw = load_csv(str(CSV_PATH))
        else:
            print("[main] Sem dados. Abortando.")
            sys.exit(1)

    total_csv = len(df_raw)

    rank_lookup = _compute_raw_mf_rank_br(df_raw)

    print("[main] Aplicando filtros...")
    df_filtered, removidos_filtros = apply_filters(df_raw)

    print(f"[main] Calculando Magic Formula (top {top_n})...")
    df_top30 = compute_magic_formula(df_filtered, top_n=top_n)

    print("[main] Verificando recuperacao judicial no StatusInvest (guardrail duplo)...")
    tickers = df_top30["TICKER"].tolist()
    rj_results = check_recuperacao_judicial(tickers)

    # Remove empresas em RJ (apenas alta/media confianca)
    def _em_rj(ticker):
        r = rj_results.get(ticker, {})
        return bool(r.get("em_rj", False))

    df_top30["em_rj"] = df_top30["TICKER"].apply(_em_rj)
    df_clean = df_top30[~df_top30["em_rj"]].reset_index(drop=True)
    df_clean["posicao_mf"] = range(1, len(df_clean) + 1)

    removidos_rj_tickers = [t for t in tickers if _em_rj(t)]
    removidos_rj = [
        {"ticker": t, "etapa": "Recuperação Judicial", "motivo": "Em recuperação judicial (guardrail StatusInvest)"}
        for t in removidos_rj_tickers
    ]
    if removidos_rj_tickers:
        print(f"[main] Removidos por RJ: {removidos_rj_tickers}")
    print(f"[main] Apos remocao RJ: {len(df_clean)} candidatos")

    records = to_records(df_clean)
    for r in records:
        ticker = r["TICKER"]
        grd = rj_results.get(ticker, {})
        r["em_rj"] = bool(grd.get("em_rj", False))
        r["rj_confianca"] = grd.get("confianca", "")
        r["rj_sinais"] = grd.get("sinais", [])
        for k, v in r.items():
            if hasattr(v, "item"):
                r[k] = v.item()

    # Aplica limite de setor ANTES do yfinance (economiza requisicoes)
    setor_map = {t: rj_results[t].get("setor", "Desconhecido") for t in rj_results}
    records, removidos_setor = apply_sector_limit(records, setor_map, max_per_sector=5, desired_n=30)

    # Enriquece apenas os sobreviventes com dados históricos yfinance
    print(f"[main] Enriquecendo {len(records)} candidatos com yfinance...")
    enriched_map = enrich_candidates(records, delay=1.5)

    # Injeta dados históricos e prompt de agente em cada record
    for r in records:
        ticker = r["TICKER"]
        enriched = enriched_map.get(ticker, {})
        r["historico"] = {
            "setor": enriched.get("setor", "Desconhecido"),
            "industria": enriched.get("industria", "Desconhecido"),
            "beta": enriched.get("beta"),
            "preco_52sem": enriched.get("preco", {}),
            "roic_trimestral": enriched.get("roic_trimestral", []),
            "roic_tendencia": enriched.get("roic_tendencia", "INSUFICIENTE"),
            "margem_ebit_trimestral": enriched.get("margem_ebit_trimestral", []),
            "margem_tendencia": enriched.get("margem_tendencia", "INSUFICIENTE"),
            "receita_trimestral_mi": enriched.get("receita_trimestral_mi", []),
            "receita_tendencia": enriched.get("receita_tendencia", "INSUFICIENTE"),
            "erro_yfinance": enriched.get("erro"),
        }
        r["contexto_agente"] = format_for_agent(ticker, enriched, r)

    all_removidos = removidos_filtros + removidos_rj + removidos_setor
    for r in all_removidos:
        r["posicao_mf_bruta"] = rank_lookup.get(r["ticker"])

    output = {
        "data_execucao": str(date.today()),
        "total_empresas_csv": int(total_csv),
        "apos_filtros": int(len(df_filtered)),
        "apos_rj_check": int(len(df_clean)),
        "apos_setor_limit": len(records),
        "removidos_rj": removidos_rj_tickers,
        "removidos": all_removidos,
        "guardrail_detalhes": {t: rj_results[t] for t in tickers},
        "candidatos": records,
    }

    json_path = OUTPUT_DIR / "candidates.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[main] JSON salvo em {json_path}")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
