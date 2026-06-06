"""Exporta lista de tickers do CSV para uso no backtester."""
import sys, io, json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from loader import load_csv
from filters import apply_filters

df = load_csv(str(ROOT / "data" / "statusinvest-busca-avancada.csv"))
df2 = apply_filters(df)
tickers = df2["TICKER"].tolist()

out = ROOT / "output" / "universe_tickers.json"
out.parent.mkdir(exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(tickers, f)

print(f"[export] {len(tickers)} tickers exportados para {out}")
