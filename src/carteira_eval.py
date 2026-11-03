"""
EVAL anti-alucinação para a análise da carteira.

Regras por ativo:
  - recomendacao ∈ MANTER | REFORCAR | VENDER | TROCAR
  - TROCAR  → troca_por não vazio e todos os tickers ∈ alternativas do contexto
  - VENDER/TROCAR → riscos não vazio
  - score_conviccao (1-10, convicção em manter) coerente com a recomendação:
      MANTER/REFORCAR com score ≤ 3  → inconsistente
      VENDER/TROCAR   com score ≥ 7  → inconsistente
  - Ações: margem/dívida/CAGR não podem contradizer os dados
  - FIIs:  DY Limpo < 6% não pode ser chamado de "DY alto"
"""

import re

_RECS = {"MANTER", "REFORCAR", "VENDER", "TROCAR"}
# Motivos que, sozinhos, não justificam realizar a posição
_TESE_INVALIDA = re.compile(r"pre[çc]o (caiu|em queda)|fora do screener|score (maior|superior)|abaixo da m[áa]xima", re.I)


def _texto(ag: dict) -> str:
    partes = [ag.get("motivo", ""), ag.get("tese_atual", "")]
    partes += ag.get("pontos_fortes", []) + ag.get("riscos", [])
    partes += [t.get("motivo", "") for t in ag.get("troca_por", []) if isinstance(t, dict)]
    return " ".join(str(p) for p in partes).lower()


def _regras_acao(f: dict, txt: str) -> list[str]:
    erros = []
    margem = f.get("MARGEM EBIT")
    div = f.get("DIVIDA LIQUIDA / EBIT")
    cagr_l = f.get("CAGR LUCROS 5 ANOS")
    if isinstance(margem, (int, float)) and margem < 10 and re.search(r"margem (ebit )?(alta|elevada)", txt):
        erros.append(f"menciona margem alta mas Margem EBIT={margem:.1f}%")
    if isinstance(div, (int, float)) and div > 1 and re.search(r"caixa l[ií]quido|d[ií]vida baixa", txt):
        erros.append(f"menciona caixa líquido/dívida baixa mas Dív/EBIT={div:.2f}x")
    if isinstance(cagr_l, (int, float)) and cagr_l < 0 and re.search(r"crescimento (consistente |forte )?de lucros", txt):
        erros.append(f"menciona crescimento de lucros mas CAGR Lucros={cagr_l:.1f}%")
    return erros


def _regras_fii(f: dict, txt: str) -> list[str]:
    dy = f.get("dy_limpo_12m")
    if isinstance(dy, (int, float)) and dy < 6 and re.search(r"(dy|dividendo|yield) (alto|elevado)", txt):
        return [f"menciona DY alto mas DY Limpo={dy:.2f}%"]
    return []


def validate_one(ag: dict, ativo: dict) -> dict:
    erros, avisos = [], []
    rec = str(ag.get("recomendacao", "")).upper()
    score = ag.get("score_conviccao")
    alts = {a["ticker"] for a in ativo.get("alternativas", [])}

    if rec not in _RECS:
        erros.append(f"recomendacao inválida: {rec!r}")
    if not isinstance(score, (int, float)) or not 1 <= score <= 10:
        erros.append(f"score_conviccao inválido: {score!r}")
    else:
        if rec in ("MANTER", "REFORCAR") and score <= 3:
            erros.append(f"{rec} com score_conviccao {score} (≤3)")
        if rec in ("VENDER", "TROCAR") and score >= 5:
            erros.append(f"{rec} com score_conviccao {score} (≥5 = tese não quebrou)")

    troca = ag.get("troca_por") or []
    if rec == "TROCAR":
        if not troca:
            erros.append("TROCAR sem troca_por")
        elif len(troca) < 2:
            avisos.append("TROCAR com 1 opção só — alocador tem pouca margem para diversificar")
        for t in troca:
            tk = t.get("ticker") if isinstance(t, dict) else t
            if tk not in alts:
                erros.append(f"troca_por {tk} fora das alternativas fornecidas")
    elif troca:
        avisos.append(f"troca_por preenchido com recomendacao {rec}")

    if rec in ("VENDER", "TROCAR") and not ag.get("riscos"):
        erros.append(f"{rec} sem riscos")

    # Vender é irreversível: exige embasamento estruturado
    emb = ag.get("embasamento") or {}
    if rec in ("VENDER", "TROCAR"):
        tese = str(emb.get("tese_quebrada") or "").strip()
        evid = [e for e in emb.get("evidencias") or [] if str(e).strip()]
        if len(tese) < 30:
            erros.append(f"{rec} sem tese_quebrada concreta")
        elif _TESE_INVALIDA.search(tese) and len(evid) < 3:
            erros.append(f"{rec} com tese fraca (preço/screener/score não são tese quebrada)")
        if len(evid) < 2:
            erros.append(f"{rec} com {len(evid)} evidência(s) — mínimo 2")
        if rec == "TROCAR" and len(str(emb.get("comparacao_destino") or "").strip()) < 30:
            erros.append("TROCAR sem comparacao_destino quantitativa")
        if ativo.get("em_prejuizo") and len(evid) < 3:
            avisos.append(f"realiza prejuízo de R$ {abs(ativo.get('resultado_rs') or 0):,.2f} com só {len(evid)} evidências")
    elif rec in ("MANTER", "REFORCAR") and not str(emb.get("gatilho_venda") or "").strip():
        avisos.append("sem gatilho_venda definido")

    txt = _texto(ag)
    f = ativo.get("fundamentos", {})
    erros += _regras_acao(f, txt) if ativo.get("classe") == "ACAO" else _regras_fii(f, txt)

    if not ag.get("web_resumo"):
        avisos.append("web_resumo vazio")
    return {"ticker": ativo["TICKER"], "valido": not erros, "erros": erros, "avisos": avisos}


def validate_all(analyses: dict, ativos: list[dict]) -> list[dict]:
    results = []
    for a in ativos:
        ag = analyses.get(a["TICKER"])
        if ag is None:
            results.append({"ticker": a["TICKER"], "valido": False, "erros": ["análise ausente"], "avisos": []})
        else:
            results.append(validate_one(ag, a))
    return results


def print_eval_report(results: list[dict]) -> int:
    print("\n[EVAL CARTEIRA] Resultado da validação anti-alucinação:")
    print("-" * 60)
    for r in results:
        print(f"  {r['ticker']}: {'OK' if r['valido'] else 'FALHOU'}")
        for e in r["erros"]:
            print(f"    INCONSISTENCIA: {e}")
        for w in r["avisos"]:
            print(f"    AVISO: {w}")
    print("-" * 60)
    invalidas = sum(1 for r in results if not r["valido"])
    print(f"[EVAL CARTEIRA] {len(results)} análises | {invalidas} inconsistências\n")
    return invalidas


if __name__ == "__main__":
    # Junta output/carteira_out/*.json → output/carteira_analyses.json e valida
    import sys
    import json
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8")
    out = Path(__file__).parent.parent / "output"
    analyses = {}
    for p in sorted((out / "carteira_out").glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            analyses[j["ticker"]] = j
        except Exception as e:
            print(f"[EVAL CARTEIRA] {p.name}: JSON inválido — {e}")
    with open(out / "carteira_analyses.json", "w", encoding="utf-8") as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)
    print(f"[EVAL CARTEIRA] {len(analyses)} análises → output/carteira_analyses.json")

    data = json.loads((out / "carteira_candidates.json").read_text(encoding="utf-8"))
    sys.exit(print_eval_report(validate_all(analyses, data["acoes"] + data["fiis"])))
