"""
EVAL FII — validação anti-alucinação para análise IA de FIIs/FIAgros.
Valida consistência do JSON do agente contra dados quantitativos reais.
Sem IA — validação determinística pura.
"""

from dataclasses import dataclass, field


@dataclass
class EvalResult:
    valido: bool
    inconsistencias: list[str] = field(default_factory=list)
    avisos: list[str]          = field(default_factory=list)


def validate_analysis(analysis: dict, candidate: dict) -> EvalResult:
    """
    analysis : JSON retornado pelo agente
    candidate: dict com dados quantitativos do fundo (um item de top10)
    """
    inconsistencias: list[str] = []
    avisos:          list[str] = []

    pvp      = float(candidate.get("PVP") or 0)
    dy_info  = candidate.get("dy_info") or {}
    dy_limpo = float(dy_info.get("dy_limpo_12m") or 0)
    n_remov  = int(dy_info.get("meses_removidos") or 0)

    score        = analysis.get("score_compra")
    recomendacao = analysis.get("recomendacao", "")
    nivel_risco  = analysis.get("nivel_risco", "")
    alertas      = [a.lower() for a in (analysis.get("alertas") or [])]
    pontos       = [p.lower() for p in (analysis.get("pontos_fortes") or [])]
    motivo       = (analysis.get("motivo") or "").lower()
    hipotese     = (analysis.get("hipotese_desconto") or "").lower()

    # ── Schema ───────────────────────────────────────────────────────────
    if score is None:
        inconsistencias.append("Campo 'score_compra' ausente")
    elif not (1 <= int(score) <= 10):
        inconsistencias.append(f"score_compra={score} fora do range 1-10")

    if recomendacao not in ("COMPRAR", "NEUTRO", "CAUTELA"):
        inconsistencias.append(
            f"recomendacao='{recomendacao}' inválida (esperado COMPRAR/NEUTRO/CAUTELA)"
        )

    if nivel_risco and nivel_risco not in ("BAIXO", "MEDIO", "ALTO"):
        inconsistencias.append(
            f"nivel_risco='{nivel_risco}' inválido (esperado BAIXO/MEDIO/ALTO)"
        )

    if score is None:
        return EvalResult(valido=False, inconsistencias=inconsistencias, avisos=avisos)

    score = int(score)

    # ── Score × DY ───────────────────────────────────────────────────────
    if dy_limpo < 6 and recomendacao == "COMPRAR" and score >= 8:
        inconsistencias.append(
            f"COMPRAR/score={score} inconsistente: DY Limpo={dy_limpo:.1f}% muito baixo"
        )

    if score >= 9 and dy_limpo < 8:
        inconsistencias.append(
            f"score={score} inconsistente: DY Limpo={dy_limpo:.1f}% insuficiente para score 9+"
        )

    # ── Score × P/VP ─────────────────────────────────────────────────────
    if pvp < 0.50 and score <= 2 and not alertas:
        avisos.append(
            f"P/VP={pvp:.3f} fortemente descontado mas score={score} sem alertas — revisar"
        )

    # ── CAUTELA sem alertas é inválida ───────────────────────────────────
    if recomendacao == "CAUTELA" and score <= 3 and not alertas:
        inconsistencias.append(
            "recomendacao=CAUTELA/score baixo mas campo 'alertas' vazio — motivo ausente"
        )

    # ── Pontos fortes × dados ────────────────────────────────────────────
    all_pos = pontos + ([motivo] if motivo else []) + ([hipotese] if hipotese else [])
    for pf in all_pos:
        if any(k in pf for k in ("dy alto", "dividendo alto", "rendimento alto", "yield alto")):
            if dy_limpo < 9:
                inconsistencias.append(
                    f"Análise menciona 'DY/dividendo alto' mas DY Limpo={dy_limpo:.1f}%"
                )
        if any(k in pf for k in ("dividendo regular", "sem irregularidade", "dividendo estável")):
            if n_remov >= 3:
                avisos.append(
                    f"Análise menciona regularidade mas {n_remov} meses removidos pelo IQR"
                )

    return EvalResult(
        valido=len(inconsistencias) == 0,
        inconsistencias=inconsistencias,
        avisos=avisos,
    )


def validate_all(analyses: dict, candidates: list[dict]) -> dict:
    cand_map = {c["TICKER"]: c for c in candidates}
    results  = {}
    for ticker, analysis in analyses.items():
        if not isinstance(analysis, dict):
            results[ticker] = EvalResult(
                valido=False,
                inconsistencias=["Análise não é JSON válido"],
            )
            continue
        results[ticker] = validate_analysis(analysis, cand_map.get(ticker, {}))
    return results


def print_eval_report(results: dict) -> int:
    invalidas = 0
    print("\n[EVAL FII] Resultado da validação anti-alucinação:")
    print("-" * 60)
    for ticker, r in results.items():
        status = "OK" if r.valido else "FALHOU"
        print(f"  {ticker}: {status}")
        for inc in r.inconsistencias:
            print(f"    INCONSISTÊNCIA: {inc}")
            invalidas += 1
        for av in r.avisos:
            print(f"    AVISO: {av}")
    print("-" * 60)
    print(f"[EVAL FII] {len(results)} análises | {invalidas} inconsistências\n")
    return invalidas
