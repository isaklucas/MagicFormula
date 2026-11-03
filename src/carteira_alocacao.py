"""
Alocador de carteira — resolve as trocas sugeridas pelos agentes em nível de carteira.

Cada agente analisa um ativo isolado e ranqueia 2-3 destinos em troca_por. Sem
coordenação, todos tendem a escolher o mesmo destino (maior score). Aqui as trocas
são atribuídas uma a uma respeitando limites de concentração:

  - MAX_TROCAS_POR_DESTINO: cada destino recebe no máximo N trocas
  - MAX_PESO_ATIVO:  peso final do destino ≤ X% do patrimônio total
  - MAX_PESO_SETOR:  peso do setor (ações) / segmento (FIIs) ≤ Y% da classe

Ordem de atribuição: menor convicção primeiro (troca mais urgente), depois maior posição.
Para cada troca tenta SÓ as preferências justificadas pelo agente, em ordem — vender é
irreversível, então nunca usa destino sem embasamento. Se nada couber, a troca vira MANTER.

Uso: python src/carteira_alocacao.py   → output/carteira_alocacao.json
"""

import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT = ROOT / "output"

MAX_TROCAS_POR_DESTINO = 1
MAX_PESO_ATIVO = 5.0          # % do patrimônio total
MAX_PESO_SETOR = {"ACAO": 30.0, "FII": 40.0}   # % da classe
MAX_DESTINOS_POR_TROCA = 3    # posição grande pode ser dividida
MIN_PARCELA = 0.5             # % do patrimônio — abaixo disso não vale a ordem


def _grupo(classe: str) -> str:
    return "ACAO" if classe == "ACAO" else "FII"   # FIAgro concorre com FIIs


def alocar(data: dict, analyses: dict) -> dict:
    ativos = data["acoes"] + data["fiis"]
    total = data["patrimonio_total"] or 1

    # Peso atual por ativo (% do total) e por setor dentro de cada classe
    peso = {a["TICKER"]: a.get("peso_pct") or 0 for a in ativos}
    setor_de = {a["TICKER"]: a.get("setor") or "—" for a in ativos}
    grupo_de = {a["TICKER"]: _grupo(a["classe"]) for a in ativos}
    peso_classe = {g: sum(peso[t] for t in peso if grupo_de[t] == g) for g in ("ACAO", "FII")}

    def peso_setor(g: str, setor: str) -> float:
        return sum(peso[t] for t in peso if grupo_de.get(t) == g and setor_de.get(t) == setor)

    trocas = [a for a in ativos if analyses.get(a["TICKER"], {}).get("recomendacao") == "TROCAR"]
    trocas.sort(key=lambda a: (analyses[a["TICKER"]].get("score_conviccao", 5), -(a.get("peso_pct") or 0)))

    recebidas: dict[str, int] = {}
    plano = []
    for a in trocas:
        t, g = a["TICKER"], _grupo(a["classe"])
        ag = analyses[t]
        alts = {x["ticker"]: x for x in a.get("alternativas", [])}
        prefs = [p["ticker"] for p in ag.get("troca_por", []) if isinstance(p, dict) and p.get("ticker") in alts]
        valor = a.get("peso_pct") or 0

        # Posição maior que o limite por ativo é dividida entre até MAX_DESTINOS_POR_TROCA destinos
        restante, destinos_t, origens, rejeitados = valor, [], set(), []
        peso[t] = 0   # o ativo vendido libera peso no próprio setor antes de testar destinos
        limite_setor = MAX_PESO_SETOR[g] / 100 * peso_classe[g]
        for cand, fonte in [(c, "preferência do agente") for c in prefs]:
            if restante <= 0.01 or len(destinos_t) >= MAX_DESTINOS_POR_TROCA:
                break
            setor_c = alts[cand]["setor"]
            folga_ativo = MAX_PESO_ATIVO - peso.get(cand, 0)
            folga_setor = limite_setor - peso_setor(g, setor_c)
            if recebidas.get(cand, 0) >= MAX_TROCAS_POR_DESTINO:
                rejeitados.append(f"{cand}: já recebe outra troca")
                continue
            parcela = min(restante, folga_ativo, folga_setor)
            if parcela < MIN_PARCELA:
                motivo = (f"peso já em {peso.get(cand, 0):.1f}% (máx {MAX_PESO_ATIVO:.0f}%)" if folga_ativo <= folga_setor
                          else f"setor {setor_c} sem folga ({MAX_PESO_SETOR[g]:.0f}% da classe)")
                rejeitados.append(f"{cand}: {motivo}")
                continue
            recebidas[cand] = recebidas.get(cand, 0) + 1
            peso[cand] = peso.get(cand, 0) + parcela
            setor_de[cand], grupo_de[cand] = setor_c, g
            restante -= parcela
            origens.add(fonte)
            motivo_d = next((p.get("motivo", "") for p in ag.get("troca_por", [])
                             if isinstance(p, dict) and p.get("ticker") == cand), alts[cand]["motivo_ia"])
            destinos_t.append({"ticker": cand, "peso": round(parcela, 2), "motivo": motivo_d})

        if destinos_t and restante <= 0.01:
            plano.append({"ticker": t, "acao_final": "TROCAR",
                          "destino": " + ".join(f"{d['ticker']} ({d['peso']:.1f}%)" for d in destinos_t)
                                     if len(destinos_t) > 1 else destinos_t[0]["ticker"],
                          "destinos": destinos_t, "origem": " / ".join(sorted(origens)),
                          "peso_movido": round(valor, 2),
                          "motivo_destino": destinos_t[0]["motivo"], "rejeitados": rejeitados})
            continue
        # Não coube por completo → desfaz as parcelas e mantém
        peso[t] = valor
        for d in destinos_t:
            recebidas[d["ticker"]] -= 1
            peso[d["ticker"]] -= d["peso"]
        plano.append({"ticker": t, "acao_final": "MANTER", "destino": None, "destinos": [],
                      "origem": "sem destino viável dentro dos limites — manter até próxima revisão",
                      "peso_movido": 0, "motivo_destino": "", "rejeitados": rejeitados})

    destinos = {d["ticker"]: round(peso[d["ticker"]], 2) for p in plano for d in p.get("destinos", [])}

    return {
        "limites": {"max_trocas_por_destino": MAX_TROCAS_POR_DESTINO, "max_peso_ativo": MAX_PESO_ATIVO,
                    "max_peso_setor": MAX_PESO_SETOR},
        "plano": plano,
        "peso_final_destinos": destinos,
    }


def main() -> None:
    data = json.loads((OUT / "carteira_candidates.json").read_text(encoding="utf-8"))
    analyses = json.loads((OUT / "carteira_analyses.json").read_text(encoding="utf-8"))
    res = alocar(data, analyses)
    (OUT / "carteira_alocacao.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[alocacao] Plano de trocas (limites: 1 troca/destino, "
          f"{MAX_PESO_ATIVO:.0f}%/ativo, setor {MAX_PESO_SETOR['ACAO']:.0f}% ações / {MAX_PESO_SETOR['FII']:.0f}% FIIs)")
    for p in res["plano"]:
        dest = p["destino"] or "—"
        print(f"  {p['ticker']:7s} → {p['acao_final']:6s} {dest:7s} ({p['origem']}) peso {p['peso_movido']:.1f}%")
        for r in p["rejeitados"]:
            print(f"      rejeitado {r}")
    print(f"[alocacao] Peso final dos destinos: {res['peso_final_destinos']}")
    print(f"[alocacao] Salvo: {OUT / 'carteira_alocacao.json'}")


if __name__ == "__main__":
    main()
