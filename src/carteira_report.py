"""
Relatório HTML da carteira — output/carteira.html (LOCAL, nunca vai para docs/).

Uso: python src/carteira_report.py
"""

import sys
import json
import html
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT = ROOT / "output"

_REC_COR = {
    "REFORCAR": ("#1f6feb", "REFORÇAR"),
    "MANTER":   ("#3fb950", "MANTER"),
    "TROCAR":   ("#d29922", "TROCAR"),
    "VENDER":   ("#f85149", "VENDER"),
}
_ORDEM = {"VENDER": 0, "TROCAR": 1, "REFORCAR": 2, "MANTER": 3}


def _e(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


def _fmt(v, fmt: str) -> str:
    return fmt.format(v) if isinstance(v, (int, float)) else "—"


def _badge(rec: str) -> str:
    cor, label = _REC_COR.get(rec, ("#8b949e", rec or "—"))
    return f'<span class="badge" style="background:{cor}">{label}</span>'


def _metricas(a: dict) -> str:
    f = a.get("fundamentos", {})
    if a["classe"] == "ACAO":
        return (f"EV/EBIT {_fmt(f.get('EV/EBIT'), '{:.1f}x')} · ROIC {_fmt(f.get('ROIC'), '{:.1f}%')} · "
                f"Margem EBIT {_fmt(f.get('MARGEM EBIT'), '{:.1f}%')} · Dív/EBIT {_fmt(f.get('DIVIDA LIQUIDA / EBIT'), '{:.2f}x')}")
    return (f"P/VP {_fmt(f.get('PVP'), '{:.2f}')} · DY Limpo {_fmt(f.get('dy_limpo_12m'), '{:.2f}%')} · "
            f"Segmento {_e(f.get('SEGMENTO'))}")


def _row(a: dict, ag: dict) -> str:
    troca = ag.get("destino_final") or "—"
    res = a.get("variacao_total")
    cor = "#3fb950" if (res or 0) >= 0 else "#f85149"
    return (f'<tr><td><a href="#{a["TICKER"]}">{a["TICKER"]}</a></td><td>{a["classe"]}</td>'
            f'<td class="num">{_fmt(a.get("peso_pct"), "{:.1f}%")}</td>'
            f'<td class="num" style="color:{cor}">{_fmt(res, "{:+.1f}%")}</td>'
            f'<td>{_badge(ag.get("recomendacao"))}</td>'
            f'<td class="num">{_e(ag.get("score_conviccao"))}</td><td>{_e(troca)}</td>'
            f'<td class="motivo">{_e(ag.get("motivo"))}</td></tr>')


def _lista(itens: list) -> str:
    return "".join(f"<li>{_e(i)}</li>" for i in itens) or "<li>—</li>"


def _embasamento(a: dict, ag: dict) -> str:
    emb = ag.get("embasamento") or {}
    if ag.get("recomendacao") in ("VENDER", "TROCAR"):
        perda = ""
        if a.get("em_prejuizo"):
            perda = (f'<p class="perda">⚠ Realiza prejuízo de R$ {abs(a.get("resultado_rs") or 0):,.2f} '
                     f'(precisaria subir {_fmt(a.get("upside_ate_pm"), "{:.1f}%")} para voltar ao PM)</p>')
        comp = (f'<p><b>Destino vs atual:</b> {_e(emb.get("comparacao_destino"))}</p>'
                if emb.get("comparacao_destino") else "")
        return (f'<div class="emb">{perda}<p><b>Tese quebrada:</b> {_e(emb.get("tese_quebrada"))}</p>'
                f'<h4>Evidências</h4><ul>{_lista(emb.get("evidencias", []))}</ul>{comp}</div>')
    if emb.get("gatilho_venda"):
        return f'<p class="web"><b>Vender se:</b> {_e(emb.get("gatilho_venda"))}</p>'
    return ""


def _card(a: dict, ag: dict) -> str:
    trocas = "".join(
        f'<li><b>{_e(t.get("ticker"))}</b> — {_e(t.get("motivo"))}'
        f'{" <b>← destino escolhido</b>" if t.get("ticker") in {d["ticker"] for d in (ag.get("alocacao") or {}).get("destinos", [])} else ""}</li>'
        for t in ag.get("troca_por", []) if isinstance(t, dict))
    aloc = ag.get("alocacao")
    if aloc:
        rej = "".join(f"<li>{_e(r)}</li>" for r in aloc["rejeitados"])
        trocas += (f'<p class="web"><b>Alocador:</b> {_e(aloc["acao_final"])} '
                   f'{_e(aloc["destino"] or "")} ({_e(aloc["origem"])})</p>'
                   + (f'<ul class="web">{rej}</ul>' if rej else ""))
    alts = "".join(
        f'<li><b>{_e(x["ticker"])}</b> [{_e(x["setor"])}] score {_e(x["score_ia"])} — {_e(x["metricas"])}</li>'
        for x in a.get("alternativas", []))
    screener = "no screener atual" if a.get("no_screener") else "fora do screener atual"
    si = "fundos-imobiliarios" if a["classe"] == "FII" else ("fiagros" if a["classe"] == "FIAGRO" else "acoes")
    return f"""
<div class="card" id="{a['TICKER']}">
  <div class="card-h">
    <h3><a href="https://statusinvest.com.br/{si}/{a['TICKER'].lower()}" target="_blank">{a['TICKER']}</a>
      <small>{a['classe']} · {_e(a.get('setor'))} · {screener}</small></h3>
    <div>{_badge(ag.get('recomendacao'))} <span class="score">convicção {_e(ag.get('score_conviccao'))}/10</span></div>
  </div>
  <p class="pos">Qtd {_fmt(a.get('quantidade'), '{:.0f}')} · PM R$ {_fmt(a.get('preco_medio'), '{:.2f}')} ·
     Atual R$ {_fmt(a.get('preco_atual'), '{:.2f}')} · Resultado {_fmt(a.get('variacao_total'), '{:+.1f}%')} ·
     Peso {_fmt(a.get('peso_pct'), '{:.1f}%')}</p>
  <p class="met">{_metricas(a)}</p>
  <p><b>Tese:</b> {_e(ag.get('tese_atual'))}</p>
  {_embasamento(a, ag)}
  <div class="cols">
    <div><h4>Pontos fortes</h4><ul>{_lista(ag.get('pontos_fortes', []))}</ul></div>
    <div><h4>Riscos</h4><ul>{_lista(ag.get('riscos', []))}</ul></div>
  </div>
  {f'<h4>Trocar por</h4><ul>{trocas}</ul>' if trocas else ''}
  <p class="web"><b>Web:</b> {_e(ag.get('web_resumo'))}</p>
  <details><summary>Alternativas consideradas</summary><ul>{alts or '<li>—</li>'}</ul></details>
</div>"""


def generate_html(data: dict, analyses: dict, path: Path) -> None:
    ativos = data["acoes"] + data["fiis"]
    ativos.sort(key=lambda a: (_ORDEM.get(analyses.get(a["TICKER"], {}).get("recomendacao"), 9),
                               -(a.get("peso_pct") or 0)))
    contagem = {}
    for a in ativos:
        r = analyses.get(a["TICKER"], {}).get("recomendacao", "—")
        contagem[r] = contagem.get(r, 0) + 1

    aloc = data.get("alocacao_pct", {})
    aloc_html = " · ".join(f"{k} {v:.1f}%" for k, v in aloc.items())
    etfs = " · ".join(f"{e['TICKER']} ({_fmt(e.get('peso_pct'), '{:.1f}%')})" for e in data.get("etfs", []))
    resumo = " · ".join(f"{_REC_COR.get(k, ('', k))[1]}: {v}" for k, v in sorted(contagem.items(), key=lambda x: _ORDEM.get(x[0], 9)))

    rows = "".join(_row(a, analyses.get(a["TICKER"], {})) for a in ativos)
    cards = "".join(_card(a, analyses.get(a["TICKER"], {})) for a in ativos)

    page = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minha Carteira — {data['data_execucao']}</title>
<style>
body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px}}
.wrap{{max-width:1200px;margin:0 auto}} a{{color:#58a6ff;text-decoration:none}}
h1{{margin:0 0 4px}} .sub{{color:#8b949e;margin-bottom:20px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
.kpi{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px}}
.kpi b{{display:block;font-size:1.2rem;color:#f0f6fc}}
table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden;margin-bottom:28px}}
th,td{{padding:8px 10px;border-bottom:1px solid #21262d;text-align:left;font-size:.88rem;vertical-align:top}}
th{{background:#1c2128;color:#8b949e;font-weight:600}} .num{{text-align:right;white-space:nowrap}}
.motivo{{color:#8b949e;max-width:420px}}
.badge{{color:#fff;padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:700;white-space:nowrap}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 20px;margin-bottom:16px}}
.card-h{{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}
.card h3{{margin:0}} .card h3 small{{color:#8b949e;font-weight:400;font-size:.8rem;margin-left:8px}}
.score{{color:#8b949e;font-size:.85rem}} .pos,.met{{color:#8b949e;font-size:.85rem;margin:6px 0}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} h4{{margin:10px 0 4px;font-size:.9rem;color:#f0f6fc}}
ul{{margin:0;padding-left:18px}} li{{margin:2px 0;font-size:.88rem}} .web{{font-size:.85rem;color:#8b949e}}
details{{font-size:.85rem;color:#8b949e;margin-top:6px}}
.emb{{border-left:3px solid #d29922;padding:4px 12px;margin:8px 0;background:#1c1a12}}
.perda{{color:#f85149;font-weight:600;margin:4px 0}}
.aviso{{background:#1a1000;border:1px solid #d29922;border-radius:8px;padding:10px 14px;font-size:.85rem;margin-bottom:20px}}
@media(max-width:700px){{.cols{{grid-template-columns:1fr}} body{{padding:16px}} table{{display:block;overflow-x:auto}}}}
</style></head><body><div class="wrap">
<h1>Minha Carteira</h1>
<div class="sub">{data['data_execucao']} · fonte: {_e(data.get('arquivo'))} · relatório local — não publicar</div>
<div class="kpis">
  <div class="kpi">Patrimônio<b>R$ {data['patrimonio_total']:,.2f}</b></div>
  <div class="kpi">Alocação<b style="font-size:.95rem">{aloc_html}</b></div>
  <div class="kpi">Recomendações<b style="font-size:.95rem">{resumo}</b></div>
</div>
<div class="aviso">Análise automatizada por IA com base em screeners quantitativos e busca web. Não é recomendação de investimento.
ETFs (só alocação, sem análise): {etfs or '—'}</div>
<table><thead><tr><th>Ativo</th><th>Classe</th><th class="num">Peso</th><th class="num">Resultado</th>
<th>Ação</th><th class="num">Convicção</th><th>Trocar por</th><th>Motivo</th></tr></thead><tbody>{rows}</tbody></table>
{cards}
</div></body></html>"""
    path.write_text(page, encoding="utf-8")


def main() -> None:
    data = json.loads((OUT / "carteira_candidates.json").read_text(encoding="utf-8"))
    analyses = json.loads((OUT / "carteira_analyses.json").read_text(encoding="utf-8"))
    # Plano do alocador sobrepõe a decisão isolada do agente nas trocas
    aloc_path = OUT / "carteira_alocacao.json"
    if aloc_path.exists():
        for p in json.loads(aloc_path.read_text(encoding="utf-8"))["plano"]:
            ag = analyses.get(p["ticker"])
            if ag is not None:
                ag["recomendacao"] = p["acao_final"]
                ag["destino_final"] = p["destino"]
                ag["alocacao"] = p
    path = OUT / "carteira.html"
    generate_html(data, analyses, path)
    print(f"[carteira_report] HTML gerado: {path}")


if __name__ == "__main__":
    main()
