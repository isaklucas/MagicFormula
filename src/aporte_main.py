"""
Aporte — distribui um aporte novo entre ETF internacional / FIIs / Ações mantendo ~1/3 cada.

Pré-requisito: /carteira rodado (output/carteira_candidates.json + carteira_analyses.json)
e screeners atualizados (output/candidates.json, output/fii_candidates.json).

Passos deste script (determinístico):
  1. Divide o aporte entre as classes priorizando quem está abaixo do alvo (sem vender nada)
  2. Monta candidatos por classe: posições atuais com convicção ≥ MIN_CONVICCAO (não VENDER/TROCAR)
     + COMPRAR do screener fora da carteira; ETFs atuais + lista fechada de ETFs internacionais
  3. Gera um prompt por classe em output/aporte_prompts/<CLASSE>.txt

Uso: python src/aporte_main.py --valor 10000
"""

import sys
import json
import shutil
import argparse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from carteira_main import (_screener_acoes, _screener_fiis, _setor_acao,
                           _metricas_acao, _metricas_fii)

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT = ROOT / "output"
PROMPTS = OUT / "aporte_prompts"
RESULTS = OUT / "aporte_out"

# Classes do aporte: FIAgro concorre junto com FIIs
CLASSES = ("ETF", "FII", "ACAO")
ALVO_PCT = {"ETF": 100 / 3, "FII": 100 / 3, "ACAO": 100 / 3}
BANDA_ALERTA = (26.0, 40.0)            # fora disso após o aporte → alerta
MAX_PESO_ATIVO = {"ACAO": 5.0, "FII": 8.0, "ETF": None}   # % do patrimônio total pós-aporte
MAX_PESO_SETOR = {"ACAO": 30.0, "FII": 40.0}              # % da classe pós-aporte
MIN_ORDEM = 300.0                      # R$ — abaixo disso não vale a ordem
MAX_ATIVOS_POR_CLASSE = 4              # aporte concentrado é mais fácil de executar e acompanhar
MIN_CONVICCAO = 6

# ETFs internacionais listados na B3 que o agente pode sugerir além dos atuais.
# O agente deve confirmar pela busca web que o ticker existe e o que replica.
ETFS_PERMITIDOS = {
    "IVVB11": "S&P 500 (EUA, large caps)",
    "SPXI11": "S&P 500 (EUA, large caps)",
    "NASD11": "Nasdaq-100 (EUA, tecnologia)",
    "WRLD11": "Ações globais (mercados desenvolvidos)",
    "ACWI11": "MSCI ACWI (global, desenvolvidos + emergentes)",
    "XINA11": "Ações chinesas",
}


def _classe(c: str) -> str:
    return "FII" if c in ("FII", "FIAGRO") else c


def dividir_por_classe(valor: float, atual: dict[str, float]) -> dict[str, float]:
    """Aporte vai primeiro para as classes abaixo do alvo, proporcional ao déficit."""
    total_pos = sum(atual.values()) + valor
    deficit = {k: max(0.0, ALVO_PCT[k] / 100 * total_pos - atual.get(k, 0)) for k in CLASSES}
    soma_def = sum(deficit.values())
    if soma_def >= valor:
        return {k: valor * d / soma_def for k, d in deficit.items()}
    # Sobra depois de zerar os déficits → divide pelo alvo
    sobra = valor - soma_def
    return {k: deficit[k] + sobra * ALVO_PCT[k] / 100 for k in CLASSES}


def _candidatos_existentes(ativos: list[dict], analyses: dict, classe: str) -> list[dict]:
    out = []
    for a in ativos:
        if _classe(a["classe"]) != classe:
            continue
        ag = analyses.get(a["TICKER"], {})
        rec, conv = ag.get("recomendacao"), ag.get("score_conviccao") or 0
        if rec in ("VENDER", "TROCAR") or conv < MIN_CONVICCAO:
            continue
        metr = _metricas_acao(a["fundamentos"]) if classe == "ACAO" else (
            f"P/VP {a['fundamentos'].get('PVP') or 0:.2f} | DY Limpo "
            f"{a['fundamentos'].get('dy_limpo_12m') or 0:.2f}% | Segmento {a.get('setor')}")
        out.append({
            "ticker": a["TICKER"], "novo": False, "setor": a.get("setor") or "—",
            "preco": a.get("preco_atual"), "patrimonio_atual": a.get("patrimonio") or 0,
            "recomendacao": rec, "conviccao": conv, "metricas": metr,
            "motivo_ia": ag.get("motivo", ""),
            "gatilho_venda": (ag.get("embasamento") or {}).get("gatilho_venda", ""),
        })
    return out


def _candidatos_novos(classe: str, held: set[str]) -> list[dict]:
    if classe == "ACAO":
        lookup, analyses, _ = _screener_acoes()
        setor_fn, metric_fn, preco_k = _setor_acao, _metricas_acao, "PRECO"
    else:
        lookup, analyses, _ = _screener_fiis()
        setor_fn, metric_fn, preco_k = (lambda c: c.get("SEGMENTO") or "—"), _metricas_fii, "PRECO"
    out = []
    for t, ag in analyses.items():
        if t in held or t not in lookup or ag.get("recomendacao") != "COMPRAR":
            continue
        c = lookup[t]
        riscos = ag.get("bear_case") or ag.get("alertas") or []
        out.append({
            "ticker": t, "novo": True, "setor": setor_fn(c), "preco": c.get(preco_k),
            "patrimonio_atual": 0, "recomendacao": "COMPRAR (screener)",
            "conviccao": ag.get("score_compra"), "metricas": metric_fn(c),
            "motivo_ia": ag.get("motivo", ""), "risco_principal": riscos[0] if riscos else "",
        })
    out.sort(key=lambda x: -(x["conviccao"] or 0))
    return out


def _candidatos_etf(etfs: list[dict]) -> list[dict]:
    """ETFs atuais + permitidos. ETF novo só entra se tiver cotação recente (confirma que existe/negocia)."""
    from aporte_eval import _preco_yf
    held = {e["TICKER"]: e for e in etfs}
    out = []
    for t, desc in ETFS_PERMITIDOS.items():
        e = held.get(t)
        preco = e.get("preco_atual") if e else _preco_yf(t)
        if preco is None:
            print(f"[aporte] ETF {t}: sem cotação no yfinance — fora dos candidatos")
            continue
        out.append({
            "ticker": t, "novo": e is None, "setor": desc, "preco": preco,
            "patrimonio_atual": e.get("patrimonio") or 0 if e else 0,
        })
    return out


def _geo_etf(etfs: list[dict]) -> str:
    """Resumo da exposição atual dos ETFs pelo que cada um replica (ETFS_PERMITIDOS)."""
    total = sum(e.get("patrimonio") or 0 for e in etfs) or 1
    partes = [f"{e['TICKER']} {ETFS_PERMITIDOS.get(e['TICKER'], 'desconhecido')} "
              f"{(e.get('patrimonio') or 0) / total * 100:.0f}%" for e in etfs]
    return "; ".join(partes) or "nenhum ETF"


def _fmt_cand(c: dict, total_pos: float, classe: str) -> str:
    cap = MAX_PESO_ATIVO.get(classe)
    peso = c["patrimonio_atual"] / total_pos * 100
    folga = f" | folga até teto {cap:.0f}%: R$ {max(0.0, cap / 100 * total_pos - c['patrimonio_atual']):,.0f}" if cap else ""
    tag = "NOVO" if c["novo"] else f"JÁ TEM R$ {c['patrimonio_atual']:,.0f} ({peso:.1f}% pós-aporte)"
    preco = f"R$ {c['preco']:.2f}" if c.get("preco") else "preço a confirmar"
    linha = f"- {c['ticker']} [{c['setor']}] {tag}{folga} | {preco}"
    if classe != "ETF":
        linha += f"\n    {c['recomendacao']} conv/score {c['conviccao']} | {c['metricas']}\n    {c['motivo_ia']}"
        if c.get("gatilho_venda"):
            linha += f"\n    Gatilho de venda: {c['gatilho_venda'][:180]}"
        if c.get("risco_principal"):
            linha += f"\n    Risco principal: {c['risco_principal'][:180]}"
    return linha


TPL = """Você é gestor de carteira. O usuário vai APORTAR R$ {orcamento:,.2f} em {nome_classe}.
Decida em quais ativos colocar esse valor e quanto em cada um.

SITUAÇÃO DA CLASSE (pós-aporte, patrimônio total R$ {total_pos:,.2f}):
- Peso atual da classe: {peso_antes:.1f}% → alvo ~33% (o aporte desta classe já foi calculado para isso)
{setores}

REGRAS OBRIGATÓRIAS:
1. Soma das alocações = R$ {orcamento:,.2f} (tolerância ±2%).
2. Use SÓ tickers da lista CANDIDATOS. Máximo {max_ativos} ativos. Ordem mínima R$ {min_ordem:.0f}.
3. {regra_teto}
4. Prefira reforçar o que já existe e tem convicção alta antes de abrir posição nova — posição nova
   só se trouxer diversificação real (setor/segmento sub-representado) ou for claramente superior.
5. Não concentre: distribua entre setores/segmentos diferentes quando possível.
6. Preço caído NÃO é motivo isolado para comprar mais (preço médio para baixo só com tese intacta).
7. O valor vira COTAS INTEIRAS (valor ÷ preço, arredondado para baixo). Em ativo de cota cara, use
   múltiplos do preço para não sobrar troco grande.
{regra_extra}

CANDIDATOS:
{candidatos}

BUSCA WEB (máx 3 buscas): confirme fatos recentes dos 2-3 ativos que você mais pretende comprar
("<TICKER> último resultado" / "<TICKER> relatório gerencial"{busca_etf}). Sem ano fixo. Não invente.

Responda EXATAMENTE este JSON (sem markdown, sem texto fora):
{{
  "classe": "{classe}",
  "alocacoes": [
    {{"ticker": "<TICKER>", "valor": <R$>, "novo": <true|false>, "motivo": "<por que este ativo, máx 160 chars>"}}
  ],
  "comentario": "<1-2 frases sobre a lógica da distribuição>",
  "web_resumo": "<1-2 frases do que as buscas confirmaram>"
}}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--valor", type=float, required=True, help="valor do aporte em R$")
    args = parser.parse_args()
    valor = args.valor

    data = json.loads((OUT / "carteira_candidates.json").read_text(encoding="utf-8"))
    analyses = json.loads((OUT / "carteira_analyses.json").read_text(encoding="utf-8"))
    ativos = data["acoes"] + data["fiis"]
    etfs = data.get("etfs", [])
    held = {a["TICKER"] for a in ativos} | {e["TICKER"] for e in etfs}

    atual = {k: 0.0 for k in CLASSES}
    for a in ativos + etfs:
        atual[_classe(a["classe"])] += a.get("patrimonio") or 0
    total_antes = sum(atual.values())
    total_pos = total_antes + valor
    orcamento = dividir_por_classe(valor, atual)

    print(f"[aporte] Aporte R$ {valor:,.2f} | patrimônio R$ {total_antes:,.2f} → R$ {total_pos:,.2f}")
    for k in CLASSES:
        depois = (atual[k] + orcamento[k]) / total_pos * 100
        print(f"  {k:5s} {atual[k] / total_antes * 100:5.1f}% → {depois:5.1f}% | aporte R$ {orcamento[k]:,.2f}")

    shutil.rmtree(PROMPTS, ignore_errors=True)
    shutil.rmtree(RESULTS, ignore_errors=True)
    PROMPTS.mkdir(parents=True)
    RESULTS.mkdir(parents=True)

    nomes = {"ACAO": "AÇÕES brasileiras", "FII": "FIIs / FIAgros", "ETF": "ETFs internacionais (B3)"}
    candidatos = {}
    for k in CLASSES:
        if k == "ETF":
            cands = _candidatos_etf(etfs)
        else:
            cands = _candidatos_existentes(ativos, analyses, k) + _candidatos_novos(k, held)[:8]
        candidatos[k] = cands
        if orcamento[k] < MIN_ORDEM:
            print(f"[aporte] {k}: orçamento R$ {orcamento[k]:,.2f} < ordem mínima — sem agente")
            continue

        setor_pesos: dict[str, float] = {}
        for a in ativos:
            if _classe(a["classe"]) == k:
                setor_pesos[a.get("setor") or "—"] = setor_pesos.get(a.get("setor") or "—", 0) + (a.get("patrimonio") or 0)
        base_classe = atual[k] + orcamento[k]
        setores = "\n".join(f"- {s}: {v / base_classe * 100:.0f}% da classe pós-aporte"
                            for s, v in sorted(setor_pesos.items(), key=lambda x: -x[1])) if k != "ETF" else \
            "\n".join(f"- {e['TICKER']}: R$ {e.get('patrimonio') or 0:,.0f}" for e in etfs)

        if k == "ETF":
            regra_teto = "Sem teto por ETF, mas evite sobreposição (IVVB11, SPXI11 e NASD11 são todos EUA)."
            regra_extra = ("8. ETF novo só se a busca web confirmar que o ticker existe na B3 e o que replica.\n"
                           f"9. Considere diversificação geográfica — exposição atual: {_geo_etf(etfs)}.")
            busca_etf = ' / "<TICKER> ETF B3 taxa de administração"'
        else:
            regra_teto = (f"Peso final de cada ativo ≤ {MAX_PESO_ATIVO[k]:.0f}% do patrimônio total (veja 'folga até teto'); "
                          f"cada setor/segmento ≤ {MAX_PESO_SETOR[k]:.0f}% da classe.")
            regra_extra = ""
            busca_etf = ""

        txt = TPL.format(orcamento=orcamento[k], nome_classe=nomes[k], total_pos=total_pos,
                         peso_antes=atual[k] / total_antes * 100, setores=setores,
                         max_ativos=MAX_ATIVOS_POR_CLASSE, min_ordem=MIN_ORDEM, regra_teto=regra_teto,
                         regra_extra=regra_extra, busca_etf=busca_etf, classe=k,
                         candidatos="\n".join(_fmt_cand(c, total_pos, k) for c in cands))
        (PROMPTS / f"{k}.txt").write_text(txt, encoding="utf-8")
        print(f"[aporte] {k}: {len(cands)} candidatos → {PROMPTS / (k + '.txt')}")

    out = {
        "data_execucao": str(date.today()), "valor": valor,
        "patrimonio_antes": round(total_antes, 2), "patrimonio_pos": round(total_pos, 2),
        "classe_antes": {k: round(v, 2) for k, v in atual.items()},
        "orcamento": {k: round(v, 2) for k, v in orcamento.items()},
        "candidatos": candidatos,
        "ativos_atuais": {a["TICKER"]: {"classe": _classe(a["classe"]), "patrimonio": a.get("patrimonio") or 0,
                                        "setor": a.get("setor") or "—"} for a in ativos + etfs},
        "limites": {"alvo_pct": ALVO_PCT, "banda_alerta": BANDA_ALERTA, "max_peso_ativo": MAX_PESO_ATIVO,
                    "max_peso_setor": MAX_PESO_SETOR, "min_ordem": MIN_ORDEM,
                    "max_ativos_por_classe": MAX_ATIVOS_POR_CLASSE},
    }
    (OUT / "aporte_candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[aporte] Salvo: {OUT / 'aporte_candidates.json'}")


if __name__ == "__main__":
    main()
