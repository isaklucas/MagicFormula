"""
Pré-check do /aporte: a carteira e os screeners estão atualizados?

Compara o export mais recente da carteira (data/carteira.xlsx ou ~/Downloads) com a
última análise (/carteira) e checa a idade dos screeners BR/FII.

Saída: uma linha por item + veredito final. Exit code:
  0 = tudo ok · 1 = precisa rodar /carteira · 2 = sem export da carteira
Uso: python src/aporte_check.py
"""

import sys
import json
from datetime import datetime, date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT = ROOT / "output"
MAX_DIAS_ANALISE = 7
MAX_DIAS_SCREENER = 7


def _mtime(p: Path) -> datetime | None:
    return datetime.fromtimestamp(p.stat().st_mtime) if p.exists() else None


def _export_mais_recente() -> Path | None:
    cands = [ROOT / "data" / "carteira.xlsx"]
    cands += list((Path.home() / "Downloads").glob("carteira-patrimonio-export*.xlsx"))
    cands = [c for c in cands if c.exists()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def _dias(d: datetime | None) -> int | None:
    return (datetime.now() - d).days if d else None


def main() -> None:
    exp = _export_mais_recente()
    analise = _mtime(OUT / "carteira_analyses.json")
    coleta = _mtime(OUT / "carteira_candidates.json")
    status = 0

    if exp is None:
        print("[check] Export da carteira: NÃO ENCONTRADO (StatusInvest → Carteira → Patrimônio → Exportar)")
        sys.exit(2)
    t_exp = _mtime(exp)
    print(f"[check] Export da carteira: {exp.name} — {t_exp:%d/%m/%Y %H:%M} ({_dias(t_exp)} dia(s))")

    if analise is None or coleta is None:
        print("[check] Análise da carteira: NUNCA RODADA")
        status = 1
    else:
        print(f"[check] Análise da carteira: {analise:%d/%m/%Y %H:%M} ({_dias(analise)} dia(s))")
        if t_exp > coleta:
            print("[check]   → export é MAIS NOVO que a análise: posições podem ter mudado")
            status = 1
        elif _dias(analise) > MAX_DIAS_ANALISE:
            print(f"[check]   → análise com mais de {MAX_DIAS_ANALISE} dias")
            status = 1

    for nome, arq in (("Screener Ações BR", "candidates.json"), ("Screener FIIs", "fii_candidates.json")):
        p = OUT / arq
        try:
            d = date.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["data_execucao"])
            idade = (date.today() - d).days
            flag = f" → VELHO (> {MAX_DIAS_SCREENER} dias, rode o screener)" if idade > MAX_DIAS_SCREENER else ""
            print(f"[check] {nome}: {d:%d/%m/%Y} ({idade} dia(s)){flag}")
        except Exception:
            print(f"[check] {nome}: AUSENTE")

    print("[check] VEREDITO: " + ("OK — pode seguir com o aporte" if status == 0
                                  else "rodar /carteira antes do aporte"))
    sys.exit(status)


if __name__ == "__main__":
    main()
