"""
Pipeline Magic Formula Small Cap US — S&P 600.
Gera output/candidates_smallcap.json.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from loader_smallcap import load_smallcap

EXCLUDED_SECTORS = {
    "Financial Services", "Financial", "Banks", "Insurance",
    "Real Estate", "Mortgage Finance",
}

# min_ev_ebit e guarda de outlier: EV/EBIT abaixo de 1 nao existe em empresa sa, e EBIT
# contaminado por ganho nao-operacional. Mesmo limite do pipeline BR. Nao ha teto de
# ROIC: ROIC alto sozinho e empresa otima (a Apple passa de 100% por causa das recompras).
FILTERS = {
    "min_liq_usd": 500_000,     # Small caps: threshold menor
    "max_ev_ebit": 50,
    "min_ev_ebit": 1.0,
    "max_div_ebit": 5,
}


def _compute_raw_mf_rank(records: list) -> dict[str, int]:
    valid = [r for r in records if r.get("EV/EBIT") and r.get("ROIC") and r["EV/EBIT"] > 0 and r["ROIC"] > 0]
    if not valid:
        return {}
    df = pd.DataFrame(valid).dropna(subset=["EV/EBIT", "ROIC"])
    df["_rev"] = df["EV/EBIT"].rank(ascending=True)
    df["_rroic"] = df["ROIC"].rank(ascending=False)
    df["_score"] = df["_rev"] + df["_rroic"]
    df = df.sort_values("_score").reset_index(drop=True)
    df["_pos"] = df.index + 1
    return dict(zip(df["TICKER"], df["_pos"].astype(int)))


def apply_filters(records: list) -> tuple[list, list[dict]]:
    kept = []
    removidos = []
    for r in records:
        ticker = r.get("TICKER", "?")
        ev = r.get("EV/EBIT")
        roic = r.get("ROIC")
        div = r.get("DIVIDA LIQUIDA / EBIT")
        liq = r.get("LIQUIDEZ MEDIA DIARIA") or 0
        setor = r.get("setor", "")

        if not ev or not roic:
            removidos.append({"ticker": ticker, "etapa": "Filtros básicos", "motivo": "EV/EBIT ou ROIC indisponível"})
            continue
        if ev < FILTERS["min_ev_ebit"] or ev > FILTERS["max_ev_ebit"]:
            removidos.append({"ticker": ticker, "etapa": "Filtros básicos", "motivo": f"EV/EBIT {ev:.1f}x fora do range [{FILTERS['min_ev_ebit']}, {FILTERS['max_ev_ebit']}]"})
            continue
        if roic <= 0:
            removidos.append({"ticker": ticker, "etapa": "Filtros básicos", "motivo": f"ROIC {roic:.1f}% ≤ 0"})
            continue
        if liq < FILTERS["min_liq_usd"]:
            removidos.append({"ticker": ticker, "etapa": "Filtros básicos", "motivo": f"Liquidez ${liq:,.0f}/dia < ${FILTERS['min_liq_usd']:,.0f}"})
            continue
        if div is not None and div >= FILTERS["max_div_ebit"]:
            removidos.append({"ticker": ticker, "etapa": "Filtros básicos", "motivo": f"Dívida/EBIT {div:.1f}x ≥ {FILTERS['max_div_ebit']}"})
            continue
        if setor in EXCLUDED_SECTORS:
            removidos.append({"ticker": ticker, "etapa": "Filtros básicos", "motivo": f"Setor excluído: {setor}"})
            continue
        kept.append(r)
    return kept, removidos


def compute_magic_formula(records: list, top_n: int = 30) -> list:
    df = pd.DataFrame(records)
    if df.empty or "EV/EBIT" not in df.columns or "ROIC" not in df.columns:
        return []
    df = df.dropna(subset=["EV/EBIT", "ROIC"])
    if df.empty:
        return []
    df["rank_ev_ebit"] = df["EV/EBIT"].rank(ascending=True)
    df["rank_roic"] = df["ROIC"].rank(ascending=False)
    df["mf_score"] = df["rank_ev_ebit"] + df["rank_roic"]
    df = df.sort_values("mf_score").head(top_n).reset_index(drop=True)
    df["posicao_mf"] = df.index + 1
    return df.to_dict(orient="records")


def apply_sector_limit(records: list, max_per_sector: int = 3) -> tuple[list, list[dict]]:
    counts: dict[str, int] = {}
    result = []
    removidos = []
    for r in records:
        setor = r.get("setor") or "Outros"
        ticker = r.get("TICKER", "?")
        if counts.get(setor, 0) < max_per_sector:
            counts[setor] = counts.get(setor, 0) + 1
            result.append(r)
        else:
            removidos.append({"ticker": ticker, "etapa": "Limite de setor", "motivo": f"Setor '{setor}' já tem {max_per_sector} representantes"})
    return result, removidos


def run(top_n: int = 30, force_refresh: bool = False):
    print(f"[main_smallcap] Iniciando pipeline S&P 600 Small Cap — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    raw = load_smallcap(force_refresh=force_refresh)
    print(f"[main_smallcap] Total carregado: {len(raw)}")

    rank_lookup = _compute_raw_mf_rank(raw)

    filtered, removidos_filtros = apply_filters(raw)
    print(f"[main_smallcap] Após filtros: {len(filtered)}")

    ranked = compute_magic_formula(filtered, top_n=top_n)
    print(f"[main_smallcap] Top {top_n} Magic Formula calculado")

    final, removidos_setor = apply_sector_limit(ranked, max_per_sector=3)
    print(f"[main_smallcap] Após limite setorial: {len(final)}")

    all_removidos = removidos_filtros + removidos_setor
    for r in all_removidos:
        r["posicao_mf_bruta"] = rank_lookup.get(r["ticker"])

    output = {
        "data_execucao": datetime.now().strftime("%Y-%m-%d"),
        "total_empresas": len(raw),
        "apos_filtros": len(filtered),
        "apos_setor_limit": len(final),
        "mercado": "US-SmallCap",
        "indice": "S&P 600",
        "removidos": all_removidos,
        "candidatos": final,
    }

    out_path = Path("output/candidates_smallcap.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[main_smallcap] Salvo: {out_path}")
    print(f"[main_smallcap] {len(final)} candidatos prontos para análise IA")

    for c in final[:5]:
        print(f"  #{c['posicao_mf']} {c['TICKER']} | EV/EBIT={c.get('EV/EBIT'):.1f}x | ROIC={c.get('ROIC'):.1f}% | Score={c.get('mf_score'):.0f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()
    run(top_n=args.top, force_refresh=args.force_refresh)
