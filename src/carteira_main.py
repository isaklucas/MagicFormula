"""
Carteira — analisa as posições do usuário (export StatusInvest) contra os screeners.

Entrada: export da carteira do StatusInvest (xlsx, uma aba por classe:
         Ações / FIIs / ETF / FIAGRO). Procura, nesta ordem:
           1. --file <caminho>
           2. data/carteira.xlsx
           3. export mais recente em ~/Downloads (carteira-patrimonio-export*.xlsx)

Saída:   output/carteira_candidates.json — uma entrada por ativo analisável
         (ações, FIIs, FIAgros) com contexto_agente + alternativas de troca
         tiradas dos últimos screeners (output/candidates.json, output/fii_candidates.json).

NUNCA commitar a carteira — fica só em data/ (gitignored) e output/ (gitignored).

Uso: python src/carteira_main.py [--file caminho.xlsx]
"""

import sys
import json
import argparse
from datetime import date
from pathlib import Path

import pandas as pd

# reconfigure (não TextIOWrapper): fii_main re-embrulha stdout ao ser importado
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

_N_ALTERNATIVAS = 8
_MAX_ALT_POR_SETOR = 2

# Aba do export → classe interna
_ABAS = {
    "AÇÕES":  "ACAO",
    "ACOES":  "ACAO",
    "FIIS":   "FII",
    "FIAGRO": "FIAGRO",
    "ETF":    "ETF",
}


def _step(n: int, label: str) -> None:
    print(f"\n[carteira] Passo {n} — {label}")


def _num(v):
    """Converte número do export (float ou string BR '1.234,56' / '-11,92%')."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace("R$", "").strip()
    if not s or s in ("-", "—"):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _resolve_file(arg: str | None) -> Path:
    if arg:
        p = Path(arg)
        if not p.exists():
            sys.exit(f"[carteira] Arquivo não encontrado: {p}")
        return p
    local = ROOT / "data" / "carteira.xlsx"
    if local.exists():
        return local
    downloads = sorted(
        (Path.home() / "Downloads").glob("carteira-patrimonio-export*.xlsx"),
        key=lambda p: p.stat().st_mtime,
    )
    if downloads:
        return downloads[-1]
    sys.exit("[carteira] Nenhum export encontrado. Exporte a carteira no StatusInvest "
             "ou salve em data/carteira.xlsx")


def load_carteira(path: Path) -> list[dict]:
    """Lê todas as abas do export e devolve uma lista de posições normalizadas."""
    sheets = pd.read_excel(path, sheet_name=None)
    posicoes = []
    for aba, df in sheets.items():
        classe = _ABAS.get(aba.strip().upper())
        if classe is None:
            print(f"[carteira] Aba ignorada: {aba}")
            continue
        cols = {c.strip().upper(): c for c in df.columns}
        for _, row in df.iterrows():
            ticker = str(row.get(cols.get("ATIVO", "ATIVO"), "")).strip().upper()
            if not ticker or ticker == "NAN":
                continue
            posicoes.append({
                "TICKER":         ticker,
                "classe":         classe,
                "preco_medio":    _num(row.get(cols.get("PREÇO MÉDIO"))),
                "preco_atual":    _num(row.get(cols.get("PREÇO ATUAL"))),
                "quantidade":     _num(row.get(cols.get("QUANTIDADE"))),
                "patrimonio":     _num(row.get(cols.get("PATRIMÔNIO ATUAL"))),
                "variacao_total": _num(row.get(cols.get("VARIAÇÃO ATUAL"))),
            })
    total = sum(p["patrimonio"] or 0 for p in posicoes)
    for p in posicoes:
        p["peso_pct"] = round((p["patrimonio"] or 0) / total * 100, 2) if total else None
        pm, pa, q = p["preco_medio"], p["preco_atual"], p["quantidade"]
        if pm and pa and q:
            p["resultado_rs"] = round((pa - pm) * q, 2)
            p["upside_ate_pm"] = round((pm / pa - 1) * 100, 1) if pa < pm else 0.0
        else:
            p["resultado_rs"], p["upside_ate_pm"] = None, None
        p["em_prejuizo"] = (p["resultado_rs"] or 0) < 0
    return posicoes


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _screener_acoes() -> tuple[dict, dict, str]:
    """Retorna (candidatos por ticker, análises IA por ticker, data do screener)."""
    cand = _load_json(OUTPUT_DIR / "candidates.json")
    an = _load_json(OUTPUT_DIR / "analyses.json")
    lookup = {c["TICKER"]: c for c in cand.get("candidatos", [])}
    return lookup, an, cand.get("data_execucao", "?")


def _screener_fiis() -> tuple[dict, dict, str]:
    cand = _load_json(OUTPUT_DIR / "fii_candidates.json")
    an = _load_json(OUTPUT_DIR / "fii_analyses.json")
    lookup = {c["TICKER"]: c for c in cand.get("top10", [])}
    return lookup, an, cand.get("data_execucao", "?")


def _setor_acao(c: dict) -> str:
    h = c.get("historico")
    if isinstance(h, dict) and h.get("setor"):
        return h["setor"]
    return c.get("setor") or "Desconhecido"


def _alternativas(setor: str, lookup: dict, analyses: dict, held: set[str],
                  setor_fn, metric_fn) -> list[dict]:
    """
    Alternativas de troca = ativos com recomendação COMPRAR no último screener,
    fora da carteira. Mesmo setor/segmento primeiro, depois melhor score geral.
    """
    pool = []
    for t, ag in analyses.items():
        if t in held or t not in lookup or ag.get("recomendacao") != "COMPRAR":
            continue
        c = lookup[t]
        pool.append({
            "ticker":       t,
            "setor":        setor_fn(c),
            "score_ia":     ag.get("score_compra"),
            "motivo_ia":    ag.get("motivo", ""),
            "metricas":     metric_fn(c),
            "mesmo_setor":  setor_fn(c) == setor,
        })
    pool.sort(key=lambda a: (not a["mesmo_setor"], -(a["score_ia"] or 0)))
    # Diversifica a lista: no máximo _MAX_ALT_POR_SETOR por setor, senão o
    # maior score (ex.: uma construtora) domina as alternativas de todo ativo
    por_setor: dict[str, int] = {}
    escolhidas = []
    for a in pool:
        if por_setor.get(a["setor"], 0) >= _MAX_ALT_POR_SETOR:
            continue
        por_setor[a["setor"]] = por_setor.get(a["setor"], 0) + 1
        escolhidas.append(a)
        if len(escolhidas) == _N_ALTERNATIVAS:
            break
    return escolhidas


def _metricas_acao(c: dict) -> str:
    def f(k, suf=""):
        v = c.get(k)
        return f"{v:.1f}{suf}" if isinstance(v, (int, float)) else "—"
    return (f"EV/EBIT {f('EV/EBIT', 'x')} | ROIC {f('ROIC', '%')} | "
            f"Margem EBIT {f('MARGEM EBIT', '%')} | Dív/EBIT {f('DIVIDA LIQUIDA / EBIT', 'x')}")


def _metricas_fii(c: dict) -> str:
    dy = (c.get("dy_info") or {}).get("dy_limpo_12m")
    pvp = c.get("PVP")
    dy_s = f"{dy:.2f}%" if isinstance(dy, (int, float)) else "—"
    pvp_s = f"{pvp:.2f}" if isinstance(pvp, (int, float)) else "—"
    return f"P/VP {pvp_s} | DY Limpo {dy_s} | Segmento {c.get('SEGMENTO') or '—'}"


def _bloco_posicao(p: dict) -> list[str]:
    def f(v, fmt):
        return fmt.format(v) if isinstance(v, (int, float)) else "—"
    lines = [
        "POSIÇÃO NA CARTEIRA DO USUÁRIO:",
        f"- Classe: {p['classe']} | Quantidade: {f(p['quantidade'], '{:.0f}')}",
        f"- Preço médio: R$ {f(p['preco_medio'], '{:.2f}')} | Preço atual: R$ {f(p['preco_atual'], '{:.2f}')}",
        f"- Resultado da posição: {f(p['variacao_total'], '{:+.2f}')}% (R$ {f(p.get('resultado_rs'), '{:+,.2f}')})",
        f"- Patrimônio: R$ {f(p['patrimonio'], '{:,.2f}')} | Peso na carteira: {f(p['peso_pct'], '{:.1f}')}%",
    ]
    if p.get("em_prejuizo"):
        compensa = "lucros futuros com ações" if p["classe"] == "ACAO" else "lucros futuros com FIIs/FIAgros"
        lines += [
            f"- ⚠ POSIÇÃO NO PREJUÍZO: vender REALIZA perda de R$ {abs(p['resultado_rs']):,.2f}. "
            f"Para voltar ao preço médio o ativo precisa subir {f(p.get('upside_ate_pm'), '{:.1f}')}%.",
            f"- Tributação: prejuízo realizado pode compensar {compensa} (IR), mas o capital perdido não volta",
        ]
    return lines


def _bloco_screener(ticker: str, lookup: dict, analyses: dict, data_scr: str, nome: str) -> list[str]:
    lines = ["", f"STATUS NO SCREENER {nome} (execução {data_scr}):"]
    if ticker in lookup:
        ag = analyses.get(ticker, {})
        lines.append(f"- Está entre os candidatos do screener. Análise IA do screener: "
                     f"{ag.get('recomendacao', '—')} score {ag.get('score_compra', '—')} — {ag.get('motivo', '')}")
    else:
        lines.append("- NÃO está entre os candidatos do screener atual (não passou nos filtros/ranking).")
    return lines


def _bloco_alternativas(alts: list[dict]) -> list[str]:
    lines = ["", "ALTERNATIVAS DE TROCA (únicas permitidas em troca_por — COMPRAR no screener atual):"]
    if not alts:
        lines.append("- Nenhuma alternativa disponível. NÃO recomende TROCAR.")
    for a in alts:
        tag = "mesmo setor" if a["mesmo_setor"] else a["setor"]
        lines.append(f"- {a['ticker']} [{tag}] score IA {a['score_ia']} | {a['metricas']} | {a['motivo_ia']}")
    return lines


def build_acoes(posicoes: list[dict], held: set[str]) -> list[dict]:
    from analyze_ticker import build_candidates

    lookup, analyses, data_scr = _screener_acoes()
    tickers = [p["TICKER"] for p in posicoes]
    fundamentals = {c["TICKER"]: c for c in build_candidates(tickers)}

    out = []
    for p in posicoes:
        t = p["TICKER"]
        c = fundamentals.get(t)
        if c is None:
            print(f"[carteira] {t}: sem fundamentos (yfinance) — analisado só com posição")
            c = {"TICKER": t, "setor": "Desconhecido", "contexto_agente": ""}
        setor = c.get("setor") or "Desconhecido"
        alts = _alternativas(setor, lookup, analyses, held, _setor_acao, _metricas_acao)
        ctx = (_bloco_posicao(p) + ["", "FUNDAMENTOS ATUAIS:", _metricas_acao(c), f"- Setor: {setor}",
               c.get("contexto_agente", "")]
               + _bloco_screener(t, lookup, analyses, data_scr, "MAGIC FORMULA BR")
               + _bloco_alternativas(alts))
        out.append({**p, "fundamentos": {k: v for k, v in c.items() if k not in ("historico", "contexto_agente")},
                    "setor": setor, "no_screener": t in lookup, "alternativas": alts,
                    "contexto_agente": "\n".join(ctx)})
    return out


def build_fiis(posicoes: list[dict], held: set[str]) -> list[dict]:
    from fii_si_scraper import fetch_all_si, fetch_all_fiagro
    from fii_enricher import enrich_fiis, get_pvp_batch
    from fii_dy_cleaner import clean_dy
    from fii_main import _build_contexto_agente

    frames = []
    for fetch in (fetch_all_si, fetch_all_fiagro):
        try:
            frames.append(fetch())
        except Exception as e:   # Fundamentus derruba a página de FIAgro às vezes
            print(f"[carteira] {fetch.__name__} falhou: {e}")
    universo = (pd.concat(frames, ignore_index=True).drop_duplicates(subset=["TICKER"]).set_index("TICKER")
                if frames else pd.DataFrame())

    lookup, analyses, data_scr = _screener_fiis()
    tickers = [p["TICKER"] for p in posicoes]
    enriched = enrich_fiis(tickers, delay=1.0)
    faltando = [t for t in tickers if t not in universo.index]
    pvp_yf = get_pvp_batch(faltando) if faltando else {}

    out = []
    for p in posicoes:
        t = p["TICKER"]
        base = universo.loc[t].to_dict() if t in universo.index else {}
        yf_data = enriched.get(t, {})
        price = base.get("PRECO") or yf_data.get("preco_yf") or p["preco_atual"]
        r = {
            "TICKER": t,
            "NOME": base.get("NOME") or t,
            "SEGMENTO": base.get("SEGMENTO") or "—",
            "TIPO": "FIAgro" if p["classe"] == "FIAGRO" else "FII",
            "PVP": base.get("PVP") or pvp_yf.get(t, {}).get("pvp"),
            "PRECO": price,
            "VPA": base.get("VPA"),
            "LIQUIDEZ": base.get("LIQUIDEZ"),
            "idade_dias": yf_data.get("idade_dias", -1),
            "ultimo_div": yf_data.get("ultimo_div"),
            "data_ultimo_div": yf_data.get("data_ultimo_div"),
            "dy_info": clean_dy(yf_data.get("dividendos_24m"), price),
        }
        if r["PVP"] is None:
            print(f"[carteira] {t}: sem P/VP (Fundamentus e yfinance)")
        seg = r["SEGMENTO"]
        alts = _alternativas(seg, lookup, analyses, held, lambda c: c.get("SEGMENTO") or "—", _metricas_fii)
        ctx = (_bloco_posicao(p) + ["", _build_contexto_agente({**r, "PVP": r["PVP"] or 0})]
               + _bloco_screener(t, lookup, analyses, data_scr, "FII DY LIMPO")
               + _bloco_alternativas(alts))
        dy = r["dy_info"]
        out.append({**p, "fundamentos": {
                        "PVP": r["PVP"], "SEGMENTO": seg, "PRECO": price, "VPA": r["VPA"],
                        "LIQUIDEZ": r["LIQUIDEZ"], "idade_dias": r["idade_dias"],
                        "dy_limpo_12m": dy.get("dy_limpo_12m"), "dy_bruto_12m": dy.get("dy_bruto_12m"),
                        "dy_valido": dy.get("valido", False)},
                    "setor": seg, "no_screener": t in lookup, "alternativas": alts,
                    "contexto_agente": "\n".join(ctx)})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="export xlsx da carteira do StatusInvest")
    args = parser.parse_args()

    _step(1, "Carregando carteira")
    path = _resolve_file(args.file)
    print(f"[carteira] Arquivo: {path}")
    posicoes = load_carteira(path)
    held = {p["TICKER"] for p in posicoes}
    por_classe = {k: [p for p in posicoes if p["classe"] == k] for k in ("ACAO", "FII", "FIAGRO", "ETF")}
    print("[carteira] " + " | ".join(f"{k}: {len(v)}" for k, v in por_classe.items()))

    _step(2, f"Ações ({len(por_classe['ACAO'])}) — fundamentos yfinance")
    acoes = build_acoes(por_classe["ACAO"], held) if por_classe["ACAO"] else []

    fiis_pos = por_classe["FII"] + por_classe["FIAGRO"]
    _step(3, f"FIIs/FIAgros ({len(fiis_pos)}) — Fundamentus + DY limpo")
    fiis = build_fiis(fiis_pos, held) if fiis_pos else []

    total = sum(p["patrimonio"] or 0 for p in posicoes)
    alocacao = {k: round(sum(p["patrimonio"] or 0 for p in v) / total * 100, 2) if total else 0
                for k, v in por_classe.items()}

    output = {
        "data_execucao": str(date.today()),
        "arquivo": path.name,
        "patrimonio_total": round(total, 2),
        "alocacao_pct": alocacao,
        "acoes": acoes,
        "fiis": fiis,
        "etfs": por_classe["ETF"],   # só alocação — sem análise de troca
    }
    out_path = OUTPUT_DIR / "carteira_candidates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n[carteira] Salvo: {out_path}")
    print(f"[carteira] Patrimônio R$ {total:,.2f} | " +
          " | ".join(f"{k} {v:.1f}%" for k, v in alocacao.items()))
    for a in acoes + fiis:
        flag = "no screener" if a["no_screener"] else "fora do screener"
        print(f"  {a['TICKER']:7s} {a['classe']:6s} peso {a['peso_pct'] or 0:5.1f}% | "
              f"{flag} | {len(a['alternativas'])} alternativas")


if __name__ == "__main__":
    main()
