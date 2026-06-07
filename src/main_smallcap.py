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

FILTERS = {
    "min_liq_usd": 500_000,     # Small caps: threshold menor
    "max_ev_ebit": 50,
    "min_ev_ebit": 0,
    "max_div_ebit": 5,
}


def apply_filters(records: list) -> list:
    kept = []
    for r in records:
        ev = r.get("EV/EBIT")
        roic = r.get("ROIC")
        div = r.get("DIVIDA LIQUIDA / EBIT")
        liq = r.get("LIQUIDEZ MEDIA DIARIA") or 0
        setor = r.get("setor", "")

        if not ev or not roic:
            continue
        if ev <= FILTERS["min_ev_ebit"] or ev > FILTERS["max_ev_ebit"]:
            continue
        if roic <= 0:
            continue
        if liq < FILTERS["min_liq_usd"]:
            continue
        if div is not None and div >= FILTERS["max_div_ebit"]:
            continue
        if setor in EXCLUDED_SECTORS:
            continue
        kept.append(r)
    return kept


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


def apply_sector_limit(records: list, max_per_sector: int = 3) -> list:
    counts: dict[str, int] = {}
    result = []
    for r in records:
        setor = r.get("setor") or "Outros"
        if counts.get(setor, 0) < max_per_sector:
            counts[setor] = counts.get(setor, 0) + 1
            result.append(r)
    return result


def run(top_n: int = 30, force_refresh: bool = False):
    print(f"[main_smallcap] Iniciando pipeline S&P 600 Small Cap — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    raw = load_smallcap(force_refresh=force_refresh)
    print(f"[main_smallcap] Total carregado: {len(raw)}")

    filtered = apply_filters(raw)
    print(f"[main_smallcap] Após filtros: {len(filtered)}")

    ranked = compute_magic_formula(filtered, top_n=top_n)
    print(f"[main_smallcap] Top {top_n} Magic Formula calculado")

    final = apply_sector_limit(ranked, max_per_sector=3)
    print(f"[main_smallcap] Após limite setorial: {len(final)}")

    output = {
        "data_execucao": datetime.now().strftime("%Y-%m-%d"),
        "total_empresas": len(raw),
        "apos_filtros": len(filtered),
        "apos_setor_limit": len(final),
        "mercado": "US-SmallCap",
        "indice": "S&P 600",
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
