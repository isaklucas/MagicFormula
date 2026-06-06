"""
EVAL anti-alucinacao: valida JSON de analise do agente contra dados quantitativos reais.
Detecta afirmacoes inconsistentes com os numeros do CSV antes de aceitar a analise.

Nao usa IA — validacao deterministica pura. Rapido e sem custo adicional.
Se falhar: analise e rejeitada e o agente deve reanalisar (max 2 tentativas na skill).
"""

from dataclasses import dataclass


@dataclass
class EvalResult:
    valido: bool
    inconsistencias: list[str]
    avisos: list[str]  # nao bloqueiam, mas sao registrados no HTML


def validate_analysis(analysis: dict, candidate: dict) -> EvalResult:
    """
    analysis: JSON retornado pelo agente
    candidate: dict com dados quantitativos do candidato
    """
    inconsistencias = []
    avisos = []

    roic = candidate.get("ROIC") or 0
    ev_ebit = candidate.get("EV/EBIT") or 0
    div_ebit = candidate.get("DIVIDA LIQUIDA / EBIT") or 0
    cagr_lucros = candidate.get("CAGR LUCROS 5 ANOS")
    cagr_receitas = candidate.get("CAGR RECEITAS 5 ANOS")
    margem_ebit = candidate.get("MARGEM EBIT") or 0

    score = analysis.get("score_compra")
    recomendacao = analysis.get("recomendacao", "")
    pontos_fortes = [p.lower() for p in analysis.get("pontos_fortes", [])]
    riscos_texto = [r.lower() for r in analysis.get("riscos", [])]
    qualidade_roic = analysis.get("qualidade_roic", "")
    valuation = analysis.get("valuation", "")
    motivo = (analysis.get("motivo") or "").lower()

    # --- Validacoes de schema ---
    if score is None:
        inconsistencias.append("Campo 'score_compra' ausente")
    elif not (1 <= int(score) <= 10):
        inconsistencias.append(f"score_compra={score} fora do range 1-10")

    if recomendacao not in ("COMPRAR", "NEUTRO", "CAUTELA"):
        inconsistencias.append(f"recomendacao='{recomendacao}' invalida")

    # Optional fields — only validate if present (slim schema omits them)
    if qualidade_roic and qualidade_roic not in ("SUSTENTAVEL", "PONTUAL", "INCERTO"):
        inconsistencias.append(f"qualidade_roic='{qualidade_roic}' invalido")

    if valuation and valuation not in ("MUITO_BARATO", "BARATO", "JUSTO", "CARO", "INCERTO"):
        inconsistencias.append(f"valuation='{valuation}' invalido")

    # --- Consistencia score x metricas ---
    if score is not None:
        score = int(score)

        # ROIC baixo nao justifica score altissimo
        if roic < 10 and score >= 9:
            inconsistencias.append(
                f"score={score} inconsistente: ROIC={roic:.1f}% e muito baixo para score 9+"
            )

        # EV/EBIT alto + COMPRAR so com ROIC excelente
        if ev_ebit > 15 and recomendacao == "COMPRAR" and roic < 25:
            inconsistencias.append(
                f"recomendacao=COMPRAR inconsistente: EV/EBIT={ev_ebit:.1f}x alto e ROIC={roic:.1f}% nao justifica"
            )

        # Divida alta nao pode ter score > 7 sem ressalva
        if div_ebit > 4 and score > 7:
            tem_ressalva = (
                any("divida" in r or "endividamento" in r for r in riscos_texto)
                or "divida" in motivo or "endividamento" in motivo
            )
            if not tem_ressalva:
                inconsistencias.append(
                    f"score={score} com DIV/EBIT={div_ebit:.1f}x sem mencao ao risco de divida"
                )

        # CAGR lucros negativo + score 9+ e suspeito
        if cagr_lucros is not None and cagr_lucros < -10 and score >= 9:
            inconsistencias.append(
                f"score={score} suspeito: CAGR Lucros={cagr_lucros:.1f}% fortemente negativo"
            )

    # --- Consistencia pontos_fortes / motivo x dados ---
    all_positive_text = list(pontos_fortes) + ([motivo] if motivo else [])
    for pf in all_positive_text:
        if any(k in pf for k in ("divida baixa", "sem divida", "caixa liquido", "divida negativa")):
            if div_ebit > 1:
                inconsistencias.append(
                    f"Analise menciona 'divida baixa/negativa' mas DIV/EBIT={div_ebit:.1f}x"
                )
        if any(k in pf for k in ("crescimento", "cagr", "crescendo")):
            if cagr_receitas is not None and cagr_receitas < 0:
                avisos.append(
                    f"Analise menciona crescimento mas CAGR Receitas={cagr_receitas:.1f}%"
                )
        if "margem" in pf and "alta" in pf:
            if margem_ebit < 10:
                inconsistencias.append(
                    f"Analise menciona 'margem alta' mas Margem EBIT={margem_ebit:.1f}%"
                )

    # --- Consistencia valuation tag ---
    if valuation == "MUITO_BARATO" and ev_ebit > 8:
        avisos.append(f"valuation=MUITO_BARATO mas EV/EBIT={ev_ebit:.1f}x (acima de 8x)")

    if valuation == "CARO" and ev_ebit < 10:
        inconsistencias.append(
            f"valuation=CARO inconsistente: EV/EBIT={ev_ebit:.1f}x e considerado barato"
        )

    # --- Consistencia qualidade_roic ---
    if qualidade_roic == "SUSTENTAVEL" and roic < 8:
        inconsistencias.append(
            f"qualidade_roic=SUSTENTAVEL inconsistente: ROIC={roic:.1f}% e muito baixo"
        )

    return EvalResult(
        valido=len(inconsistencias) == 0,
        inconsistencias=inconsistencias,
        avisos=avisos,
    )


def validate_all(analyses: dict, candidates: list[dict]) -> dict:
    """
    Valida todas as analises. Retorna dict com resultado por ticker.
    """
    cand_map = {c["TICKER"]: c for c in candidates}
    results = {}
    for ticker, analysis in analyses.items():
        if not isinstance(analysis, dict):
            results[ticker] = EvalResult(
                valido=False,
                inconsistencias=["Analise nao e um JSON valido"],
                avisos=[],
            )
            continue
        cand = cand_map.get(ticker, {})
        results[ticker] = validate_analysis(analysis, cand)
    return results


def print_eval_report(results: dict) -> int:
    """Imprime relatorio e retorna numero de analises invalidas."""
    invalidas = 0
    print("\n[EVAL] Resultado da validacao anti-alucinacao:")
    print("-" * 60)
    for ticker, r in results.items():
        status = "OK" if r.valido else "FALHOU"
        print(f"  {ticker}: {status}")
        for inc in r.inconsistencias:
            print(f"    INCONSISTENCIA: {inc}")
            invalidas += 1
        for av in r.avisos:
            print(f"    AVISO: {av}")
    print("-" * 60)
    print(f"[EVAL] {len(results)} analises | {invalidas} inconsistencias encontradas\n")
    return invalidas
