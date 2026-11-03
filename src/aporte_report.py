"""
Relatório HTML do aporte — output/aporte.html (LOCAL, nunca vai para docs/).

Uso: python src/aporte_report.py
"""

import sys
import json
import html
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT = ROOT / "output"

_NOMES = {"ETF": "ETF internacional", "FII": "FIIs / FIAgro", "ACAO": "Ações"}
_CORES = {"ETF": "#58a6ff", "FII": "#d29922", "ACAO": "#3fb950"}


def _e(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


def _barra(pcts: dict) -> str:
    segs = "".join(
        f'<div style="width:{v}%;background:{_CORES[k]}" title="{_NOMES[k]} {v:.1f}%">{v:.0f}%</div>'
        for k, v in pcts.items())
    return f'<div class="barra">{segs}</div>'


def generate_html(p: dict, path: Path) -> None:
    linhas = "".join(
        f'<tr><td><b>{_e(o["ticker"])}</b> {"<span class=novo>NOVO</span>" if o["novo"] else ""}</td>'
        f'<td>{_NOMES[o["classe"]]}</td><td>{_e(o["setor"])}</td>'
        f'<td class="num">{o["quantidade"]}</td><td class="num">R$ {o["preco"]:,.2f}</td>'
        f'<td class="num"><b>R$ {o["valor_executado"]:,.2f}</b></td><td class="num">{o["pct_aporte"]:.1f}%</td>'
        f'<td class="num">{o["peso_antes"]:.1f}% → {o["peso_depois"]:.1f}%</td>'
        f'<td class="motivo">{_e(o["motivo"])}</td></tr>'
        for o in sorted(p["ordens"], key=lambda o: (list(_NOMES).index(o["classe"]), -o["valor_executado"])))
    classes = "".join(
        f'<tr><td><span class="dot" style="background:{_CORES[k]}"></span>{_NOMES[k]}</td>'
        f'<td class="num">{p["classe_antes_pct"][k]:.1f}%</td><td class="num">{p["classe_depois_pct"][k]:.1f}%</td>'
        f'<td class="num">R$ {p["orcamento"][k]:,.2f}</td><td class="motivo">{_e(p["comentarios"].get(k, ""))}</td></tr>'
        for k in _NOMES)
    alertas = "".join(f"<li>{_e(a)}</li>" for a in p["avisos"] + p["erros"])
    web = "".join(f"<li><b>{_NOMES[k]}:</b> {_e(v)}</li>" for k, v in p["web"].items() if v)

    page = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plano de Aporte — {p['data_execucao']}</title>
<style>
body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px}}
.wrap{{max-width:1200px;margin:0 auto}} h1{{margin:0 0 4px}} h2{{font-size:1.05rem;margin:24px 0 8px;color:#f0f6fc}}
.sub{{color:#8b949e;margin-bottom:20px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}}
.kpi{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px}}
.kpi b{{display:block;font-size:1.2rem;color:#f0f6fc}}
.barra{{display:flex;height:26px;border-radius:6px;overflow:hidden;margin:6px 0 4px;font-size:.75rem;font-weight:700;color:#0d1117}}
.barra div{{display:flex;align-items:center;justify-content:center}}
.lbl{{color:#8b949e;font-size:.8rem}}
table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden}}
th,td{{padding:8px 10px;border-bottom:1px solid #21262d;text-align:left;font-size:.88rem;vertical-align:top}}
th{{background:#1c2128;color:#8b949e;font-weight:600}} .num{{text-align:right;white-space:nowrap}}
.motivo{{color:#8b949e;max-width:380px}} .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}
.novo{{background:#1f6feb;color:#fff;font-size:.68rem;padding:1px 6px;border-radius:8px;margin-left:4px}}
ul{{padding-left:18px}} li{{font-size:.88rem;margin:3px 0}}
.aviso{{background:#1a1000;border:1px solid #d29922;border-radius:8px;padding:10px 14px;font-size:.85rem;margin-top:16px}}
@media(max-width:700px){{body{{padding:16px}} table{{display:block;overflow-x:auto}}}}
</style></head><body><div class="wrap">
<h1>Plano de Aporte</h1>
<div class="sub">{p['data_execucao']} · relatório local — não publicar</div>
<div class="kpis">
  <div class="kpi">Aporte<b>R$ {p['valor']:,.2f}</b></div>
  <div class="kpi">Executado<b>R$ {p['valor_executado']:,.2f}</b></div>
  <div class="kpi">Troco<b>R$ {p['troco']:,.2f}</b></div>
  <div class="kpi">Ordens<b>{len(p['ordens'])}</b></div>
</div>
<div class="lbl">Antes</div>{_barra(p['classe_antes_pct'])}
<div class="lbl">Depois (alvo ~33% cada)</div>{_barra(p['classe_depois_pct'])}
<h2>Por classe</h2>
<table><thead><tr><th>Classe</th><th class="num">Antes</th><th class="num">Depois</th><th class="num">Aporte</th><th>Lógica</th></tr></thead>
<tbody>{classes}</tbody></table>
<h2>Ordens de compra</h2>
<table><thead><tr><th>Ativo</th><th>Classe</th><th>Setor</th><th class="num">Qtd</th><th class="num">Preço</th>
<th class="num">Valor</th><th class="num">% aporte</th><th class="num">Peso</th><th>Motivo</th></tr></thead>
<tbody>{linhas}</tbody></table>
{f'<h2>Busca web</h2><ul>{web}</ul>' if web else ''}
{f'<div class="aviso"><b>Alertas</b><ul>{alertas}</ul></div>' if alertas else ''}
<div class="aviso">Preços do último fechamento — confira na corretora antes de enviar a ordem. Análise automatizada, não é recomendação de investimento.</div>
</div></body></html>"""
    path.write_text(page, encoding="utf-8")


def main() -> None:
    p = json.loads((OUT / "aporte_plano.json").read_text(encoding="utf-8"))
    path = OUT / "aporte.html"
    generate_html(p, path)
    print(f"[aporte_report] HTML gerado: {path}")


if __name__ == "__main__":
    main()
