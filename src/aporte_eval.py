"""
EVAL + plano do aporte.

Junta output/aporte_out/<CLASSE>.json, valida contra os limites de aporte_candidates.json
e calcula quantidades (cotas inteiras) com o preço atual. Grava output/aporte_plano.json.

Validações (inconsistência → exit > 0):
  - soma da classe = orçamento ±2%
  - ticker ∈ candidatos da classe; ≤ MAX_ATIVOS; valor ≥ ordem mínima
  - peso final por ativo ≤ teto da classe; peso por setor ≤ teto da classe
  - ETF novo precisa ter preço no yfinance (confirma que o ticker existe)

Uso: python src/aporte_eval.py
"""

import sys
import json
import math
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT = ROOT / "output"


def _preco_yf(ticker: str) -> float | None:
    try:
        import yfinance as yf
        hist = yf.Ticker(f"{ticker}.SA").history(period="5d")
        return round(float(hist["Close"].iloc[-1]), 2) if not hist.empty else None
    except Exception:
        return None


def validar(data: dict, propostas: dict) -> tuple[list[dict], list[str], list[str]]:
    lim = data["limites"]
    total_pos = data["patrimonio_pos"]
    atuais = data["ativos_atuais"]
    erros, avisos, linhas = [], [], []

    for classe, orc in data["orcamento"].items():
        if orc < lim["min_ordem"]:
            continue
        prop = propostas.get(classe)
        if prop is None:
            erros.append(f"{classe}: proposta ausente")
            continue
        cands = {c["ticker"]: c for c in data["candidatos"][classe]}
        alocs = prop.get("alocacoes") or []
        soma = sum(a.get("valor") or 0 for a in alocs)
        if abs(soma - orc) > 0.02 * orc:
            erros.append(f"{classe}: soma R$ {soma:,.2f} ≠ orçamento R$ {orc:,.2f}")
        if len(alocs) > lim["max_ativos_por_classe"]:
            erros.append(f"{classe}: {len(alocs)} ativos > máx {lim['max_ativos_por_classe']}")

        base_classe = sum(v["patrimonio"] for v in atuais.values() if v["classe"] == classe) + orc
        setor_final: dict[str, float] = {}
        for v in atuais.values():
            if v["classe"] == classe:
                setor_final[v["setor"]] = setor_final.get(v["setor"], 0) + v["patrimonio"]
        setor_inicial = dict(setor_final)

        for a in alocs:
            t, val = a.get("ticker"), a.get("valor") or 0
            c = cands.get(t)
            if c is None:
                erros.append(f"{classe}: {t} fora da lista de candidatos")
                continue
            if val < lim["min_ordem"]:
                erros.append(f"{classe}: {t} R$ {val:,.2f} < ordem mínima R$ {lim['min_ordem']:.0f}")
            final = c["patrimonio_atual"] + val
            teto = lim["max_peso_ativo"].get(classe)
            if teto and final / total_pos * 100 > teto + 0.1:
                erros.append(f"{classe}: {t} iria a {final / total_pos * 100:.1f}% > teto {teto:.0f}%")
            setor_final[c["setor"]] = setor_final.get(c["setor"], 0) + val

            preco = c.get("preco") or _preco_yf(t)
            if not preco:
                erros.append(f"{classe}: {t} sem preço (ticker existe?)")
                continue
            qtd = math.floor(val / preco)
            if qtd == 0:
                erros.append(f"{classe}: {t} R$ {val:,.2f} não compra 1 cota a R$ {preco:.2f}")
            linhas.append({
                "classe": classe, "ticker": t, "novo": c["novo"], "setor": c["setor"],
                "valor_planejado": round(val, 2), "preco": preco, "quantidade": qtd,
                "valor_executado": round(qtd * preco, 2),
                "pct_aporte": round(qtd * preco / data["valor"] * 100, 1),
                "peso_antes": round(c["patrimonio_atual"] / data["patrimonio_antes"] * 100, 2),
                "peso_depois": round((c["patrimonio_atual"] + qtd * preco) / total_pos * 100, 2),
                "motivo": a.get("motivo", ""),
            })

        teto_setor = lim["max_peso_setor"].get(classe)
        if teto_setor:
            for s, v in setor_final.items():
                if v / base_classe * 100 <= teto_setor + 0.1:
                    continue
                if v > setor_inicial.get(s, 0) + 0.01:
                    erros.append(f"{classe}: aporte aumenta setor {s} para {v / base_classe * 100:.0f}% da classe (teto {teto_setor:.0f}%)")
                else:
                    avisos.append(f"{classe}: setor {s} já acima do teto ({v / base_classe * 100:.0f}% da classe) — "
                                  "aporte não aumentou; diluir nos próximos aportes")
    return linhas, erros, avisos


def main() -> None:
    data = json.loads((OUT / "aporte_candidates.json").read_text(encoding="utf-8"))
    propostas = {}
    for p in sorted((OUT / "aporte_out").glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            propostas[j["classe"]] = j
        except Exception as e:
            print(f"[aporte_eval] {p.name}: JSON inválido — {e}")

    linhas, erros, avisos = validar(data, propostas)

    executado = sum(l["valor_executado"] for l in linhas)
    total_pos = data["patrimonio_antes"] + executado
    classe_depois = dict(data["classe_antes"])
    for l in linhas:
        classe_depois[l["classe"]] += l["valor_executado"]
    lo, hi = data["limites"]["banda_alerta"]
    for k, v in classe_depois.items():
        pct = v / total_pos * 100
        if not lo <= pct <= hi:
            avisos.append(f"classe {k} em {pct:.1f}% fora da banda {lo:.0f}–{hi:.0f}%")

    plano = {
        "data_execucao": data["data_execucao"], "valor": data["valor"],
        "valor_executado": round(executado, 2), "troco": round(data["valor"] - executado, 2),
        "classe_antes_pct": {k: round(v / data["patrimonio_antes"] * 100, 1) for k, v in data["classe_antes"].items()},
        "classe_depois_pct": {k: round(v / total_pos * 100, 1) for k, v in classe_depois.items()},
        "orcamento": data["orcamento"],
        "ordens": linhas,
        "comentarios": {k: v.get("comentario", "") for k, v in propostas.items()},
        "web": {k: v.get("web_resumo", "") for k, v in propostas.items()},
        "erros": erros, "avisos": avisos,
    }
    (OUT / "aporte_plano.json").write_text(json.dumps(plano, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[EVAL APORTE]")
    print("-" * 60)
    for e in erros:
        print(f"  INCONSISTENCIA: {e}")
    for w in avisos:
        print(f"  AVISO: {w}")
    print(f"  {len(linhas)} ordens | executado R$ {executado:,.2f} | troco R$ {plano['troco']:,.2f}")
    print("-" * 60)
    sys.exit(len(erros))


if __name__ == "__main__":
    main()
