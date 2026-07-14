"""
Exporta o universo de tickers para o backtester.

Usa a MESMA cadeia de dados do main.py (yfinance/xlsx B3 → SI API → CSV) e o MESMO
guardrail de Recuperação Judicial. Antes, este script lia apenas o CSV estático e
pulava o guardrail, então empresas em RJ (ex.: AMER3) entravam no universo do
backtest com fundamentos defasados e apareciam no top15.

Viés conhecido: o guardrail marca quem está em RJ HOJE e remove a empresa de TODO o
período do backtest (look-ahead). Aceitável aqui — os fundamentos dessas empresas na
fonte estavam corrompidos de qualquer forma.

Saídas:
  output/universe_tickers.json  — lista de tickers (consumida por backtester.py --tickers)
  output/universe_sectors.json  — mapa ticker → setor B3 (consumida por --sectors)
"""
import sys, io, json
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from loader import load_csv
from filters import apply_filters
from scraper import check_recuperacao_judicial

CSV_PATH = ROOT / "data" / "statusinvest-busca-avancada.csv"


def _load_raw() -> pd.DataFrame:
    """Mesma cascata de fontes do main.py."""
    try:
        from yf_fetcher import fetch_all_stocks
        print("[export] Buscando dados via yfinance (EmpresasB3Porsetor.xlsx)...")
        df = fetch_all_stocks()
        if df is not None and not df.empty:
            print(f"[export] {len(df)} ações carregadas via yfinance")
            return df
    except Exception as e:
        print(f"[export] yfinance fetcher falhou: {e}")

    try:
        from si_fetcher import fetch_all_stocks as _si_fetch
        print("[export] Fallback → Status Invest API...")
        df = _si_fetch()
        if df is not None and not df.empty:
            print(f"[export] {len(df)} ações carregadas via SI API")
            return df
    except Exception as e:
        print(f"[export] SI API falhou: {e}")

    if CSV_PATH.exists():
        print(f"[export] Fallback → CSV: {CSV_PATH}")
        return load_csv(str(CSV_PATH))

    print("[export] Sem dados. Abortando.")
    sys.exit(1)


def main():
    df_raw = _load_raw()

    df, _ = apply_filters(df_raw)
    tickers = df["TICKER"].tolist()
    print(f"[export] {len(tickers)} tickers apos filtros basicos")

    print("[export] Guardrail de recuperacao judicial (StatusInvest)...")
    rj = check_recuperacao_judicial(tickers)

    em_rj = [t for t in tickers if rj.get(t, {}).get("em_rj")]
    universo = [t for t in tickers if t not in set(em_rj)]
    setores = {t: rj.get(t, {}).get("setor", "Desconhecido") for t in universo}

    if em_rj:
        print(f"[export] Removidos por RJ: {em_rj}")

    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)

    tickers_path = out_dir / "universe_tickers.json"
    with open(tickers_path, "w", encoding="utf-8") as f:
        json.dump(universo, f)

    sectors_path = out_dir / "universe_sectors.json"
    with open(sectors_path, "w", encoding="utf-8") as f:
        json.dump(setores, f, ensure_ascii=False, indent=2)

    print(f"[export] {len(universo)} tickers exportados para {tickers_path}")
    print(f"[export] setores exportados para {sectors_path}")


if __name__ == "__main__":
    main()
