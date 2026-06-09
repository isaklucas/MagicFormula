"""
Gera relatório HTML do Magic Formula Small Cap US (S&P 600).
Reutiliza helpers do report_us.py — accent laranja para diferenciação visual.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from report import (
    _fmt, _color_roic, _color_ev, _color_div, _motivo, _badge_rec,
    _build_removidos_section_mf,
)
from navbar import get_navbar
from report_us import _fmt_usd


def _build_card_sc(c, ag, rank, group):
    ticker = c["TICKER"]
    pos    = c.get("posicao_mf", "—")
    ev     = c.get("EV/EBIT")
    roic   = c.get("ROIC")
    margem = c.get("MARGEM EBIT")
    roe    = c.get("ROE")
    div    = c.get("DIVIDA LIQUIDA / EBIT")
    liq    = c.get("LIQUIDEZ MEDIA DIARIA")
    cagr_r = c.get("CAGR RECEITAS 5 ANOS")
    cagr_l = c.get("CAGR LUCROS 5 ANOS")
    vm     = c.get("VALOR DE MERCADO")
    preco  = c.get("PRECO")
    setor  = c.get("setor", "—")

    score_ia     = ag.get("score_compra", "—")
    recomendacao = ag.get("recomendacao", "")
    motivo_text  = ag.get("motivo") or "—"

    border_color  = "#f97316" if group == "COMPRAR" else "#d29922"
    motivo_bg     = "rgba(249,115,22,.1)" if group == "COMPRAR" else "rgba(210,153,34,.1)"
    motivo_border = "#f9731633" if group == "COMPRAR" else "#d2992233"
    motivo_icon   = "✓" if group == "COMPRAR" else "⚠"
    motivo_label  = "Por que COMPRAR" if group == "COMPRAR" else "Por que NEUTRO"

    metrics = [
        ("EV/EBIT",     f"{_fmt(ev)}x",     _color_ev(ev)),
        ("ROIC",        f"{_fmt(roic)}%",    _color_roic(roic)),
        ("Mg EBIT",     f"{_fmt(margem)}%",  ""),
        ("ROE",         f"{_fmt(roe)}%",     ""),
        ("Dív/EBIT",    f"{_fmt(div)}x",     _color_div(div)),
        ("CAGR Rec.",   f"{_fmt(cagr_r)}%",  ""),
        ("CAGR Luc.",   f"{_fmt(cagr_l)}%",  ""),
        ("Mkt Cap",     _fmt_usd(vm),        ""),
        ("Preço",       f"${_fmt(preco)}",   ""),
        ("Liq. Diária", _fmt_usd(liq),       ""),
    ]
    metrics_html = "".join(
        '<div class="col-6 col-sm-4">'
        '<div class="p-2 rounded-2" style="background:#0d1117">'
        f'<div class="text-muted" style="font-size:.65rem">{lbl}</div>'
        f'<div class="fw-semibold" style="font-size:.9rem;color:{clr if clr else "#e6edf3"}">{val}</div>'
        '</div></div>'
        for lbl, val, clr in metrics
    )

    return f"""
    <div class="col">
      <div class="card h-100" style="background:#161b22;border:1px solid #30363d;border-top:3px solid {border_color}">
        <div class="card-header d-flex align-items-center gap-2 py-2" style="background:#0d1117;border-bottom:1px solid #30363d">
          <span class="badge rounded-pill" style="background:{border_color}22;color:{border_color};border:1px solid {border_color}44">#{rank}</span>
          <span class="fw-bold" style="font-size:1.1rem;color:#fb923c">{ticker}</span>
          <span class="text-muted ms-auto" style="font-size:.7rem">{setor[:18]} · MF #{pos}</span>
        </div>
        <div class="card-body pb-2">
          <div class="row g-2 mb-3">{metrics_html}</div>
          <div class="d-flex align-items-center gap-2 mb-2 flex-wrap">
            {_badge_rec(recomendacao)}
            <span class="text-muted" style="font-size:.75rem">Score IA:</span>
            <span class="fw-bold" style="color:#fb923c">{score_ia}/10</span>
          </div>
          <div class="rounded-2 p-2" style="background:{motivo_bg};border:1px solid {motivo_border};font-size:.78rem">
            <span style="color:{border_color}">{motivo_icon}</span>
            <span class="text-muted fw-semibold"> {motivo_label}: </span>
            <span style="color:#e6edf3">{motivo_text}</span>
          </div>
        </div>
      </div>
    </div>"""


def _table_row_sc(c, ag, rank, group):
    ticker = c["TICKER"]
    pos    = c.get("posicao_mf", "—")
    ev     = c.get("EV/EBIT")
    roic   = c.get("ROIC")
    score  = c.get("mf_score")
    margem = c.get("MARGEM EBIT")
    roe    = c.get("ROE")
    div    = c.get("DIVIDA LIQUIDA / EBIT")
    liq    = c.get("LIQUIDEZ MEDIA DIARIA")
    cagr_r = c.get("CAGR RECEITAS 5 ANOS")
    cagr_l = c.get("CAGR LUCROS 5 ANOS")
    vm     = c.get("VALOR DE MERCADO")
    setor  = c.get("setor", "—")

    score_ia     = ag.get("score_compra", "—")
    recomendacao = ag.get("recomendacao", "")
    motivo       = ag.get("motivo") or "—"
    motivo_short = motivo[:65] + "…" if len(motivo) > 65 else motivo

    return f"""
    <tr>
      <td class="text-center fw-bold text-secondary">{rank}</td>
      <td>
        <a href="https://finance.yahoo.com/quote/{ticker}" target="_blank" rel="noopener"
           class="fw-bold text-decoration-none" style="color:#fb923c">{ticker}</a>
      </td>
      <td class="text-center text-muted" style="font-size:.78rem">{setor[:14]}</td>
      <td class="text-center fw-semibold" style="color:{_color_ev(ev)}">{_fmt(ev)}x</td>
      <td class="text-center fw-semibold" style="color:{_color_roic(roic)}">{_fmt(roic)}%</td>
      <td class="text-center text-secondary">{_fmt(score,0)}</td>
      <td class="text-center fw-bold" style="color:#fb923c">{score_ia}/10</td>
      <td class="text-center">{_badge_rec(recomendacao)}</td>
      <td class="text-center text-secondary">{_fmt(margem)}%</td>
      <td class="text-center text-secondary">{_fmt(roe)}%</td>
      <td class="text-center fw-semibold" style="color:{_color_div(div)}">{_fmt(div)}x</td>
      <td class="text-center text-secondary" style="font-size:.8rem">{_fmt_usd(liq)}</td>
      <td class="text-center text-secondary">{_fmt(cagr_r)}%</td>
      <td class="text-center text-secondary">{_fmt(cagr_l)}%</td>
      <td class="text-center text-secondary" style="font-size:.8rem">{_fmt_usd(vm)}</td>
      <td style="font-size:.72rem;color:#8b949e;max-width:160px">{motivo_short}</td>
    </tr>"""


def generate_html_sc(data: dict, analyses: dict, output_path: str, top_n: int = 20):
    cand_lookup = {c["TICKER"]: c for c in data["candidatos"]}
    data_exec   = data.get("data_execucao", "")
    total       = data.get("total_empresas", "—")
    apos_filtros = data.get("apos_filtros", "—")
    apos_setor  = data.get("apos_setor_limit", "—")
    removidos   = data.get("removidos", [])

    comprar_list, neutro_list = [], []
    for ticker, ag in analyses.items():
        if ticker not in cand_lookup:
            continue
        if isinstance(ag, str):
            try: ag = json.loads(ag)
            except Exception: ag = {"motivo": ag}
        rec      = ag.get("recomendacao", "NEUTRO")
        score_ia = ag.get("score_compra", 0) or 0
        mf       = cand_lookup[ticker].get("mf_score", 999)
        if rec == "COMPRAR":
            comprar_list.append((ticker, ag, score_ia, mf))
        else:
            neutro_list.append((ticker, ag, score_ia, mf))

    comprar_list.sort(key=lambda x: (-x[2], x[3]))
    neutro_list.sort(key=lambda x: (-x[2], x[3]))

    n_comprar = len(comprar_list)
    n_neutro  = len(neutro_list)
    n_total   = n_comprar + n_neutro
    now       = datetime.now().strftime("%d/%m/%Y %H:%M")

    rows_html = (
        f'<tr style="background:#1a0800"><td colspan="16" class="py-2 px-3 fw-bold" style="color:#f97316;font-size:.75rem;letter-spacing:.5px">▼ COMPRAR — {n_comprar} ações</td></tr>'
        + "".join(_table_row_sc(cand_lookup[t], ag, r+1, "COMPRAR") for r,(t,ag,*_) in enumerate(comprar_list))
        + f'<tr style="background:#1a1000"><td colspan="16" class="py-2 px-3 fw-bold" style="color:#d29922;font-size:.75rem;letter-spacing:.5px">▼ NEUTRO / CAUTELA — {n_neutro} ações</td></tr>'
        + "".join(_table_row_sc(cand_lookup[t], ag, r+1, "NEUTRO") for r,(t,ag,*_) in enumerate(neutro_list))
    )

    comprar_cards = "".join(_build_card_sc(cand_lookup[t], ag, r+1, "COMPRAR") for r,(t,ag,*_) in enumerate(comprar_list))
    neutro_cards  = "".join(_build_card_sc(cand_lookup[t], ag, r+1, "NEUTRO")  for r,(t,ag,*_) in enumerate(neutro_list))

    tickers_js = [t for t,*_ in comprar_list]
    roics_js   = [round(float(cand_lookup[t].get("ROIC") or 0), 2) for t in tickers_js]
    all_tickers = [t for t,*_ in comprar_list + neutro_list]
    all_roics   = [round(float(cand_lookup[t].get("ROIC") or 0), 2) for t in all_tickers]
    all_evs     = [round(float(cand_lookup[t].get("EV/EBIT") or 0), 2) for t in all_tickers]
    all_colors  = ["#f97316" if t in {x[0] for x in comprar_list} else "#d29922" for t in all_tickers]

    ticker_data = {}
    for ticker, ag in analyses.items():
        c = cand_lookup.get(ticker, {})
        ticker_data[ticker] = {
            "ticker": ticker, "setor": c.get("setor", "—"),
            "posicao_mf": c.get("posicao_mf", "—"), "mf_score": c.get("mf_score"),
            "ev_ebit": c.get("EV/EBIT"), "roic": c.get("ROIC"),
            "margem": c.get("MARGEM EBIT"), "roe": c.get("ROE"),
            "div_ebit": c.get("DIVIDA LIQUIDA / EBIT"),
            "cagr_r": c.get("CAGR RECEITAS 5 ANOS"), "cagr_l": c.get("CAGR LUCROS 5 ANOS"),
            "vm": c.get("VALOR DE MERCADO"), "liq": c.get("LIQUIDEZ MEDIA DIARIA"),
            "preco": c.get("PRECO"), "recomendacao": ag.get("recomendacao", ""),
            "score_ia": ag.get("score_compra", ""), "motivo": ag.get("motivo") or "",
            "moeda": "USD",
        }
    ticker_data_js = json.dumps(ticker_data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Magic Formula Small Cap US</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  [data-bs-theme=dark] {{ --bs-body-bg: #0d1117; --bs-body-color: #e6edf3; --bs-card-bg: #161b22; --bs-border-color: #30363d; }}
  body {{ font-family: -apple-system, 'Segoe UI', system-ui, sans-serif; }}
  .hero {{ background: linear-gradient(135deg, #1c0a00 0%, #431407 50%, #7c2d12 100%); padding: 2rem 0 1.5rem; }}
  .hero h1 {{ font-size: clamp(1.4rem, 4vw, 2rem); font-weight: 700; letter-spacing: -.5px; }}
  .hero h1 em {{ font-style: normal; color: #fb923c; }}
  .stat-pill {{ background: rgba(255,255,255,.1); border-radius: .75rem; padding: .6rem 1.1rem; text-align: center; }}
  .stat-pill .val {{ font-size: 1.4rem; font-weight: 700; color: #fff; line-height: 1.2; }}
  .stat-pill .lbl {{ font-size: .68rem; color: #fed7aa; }}
  .stat-pill.green {{ background: rgba(249,115,22,.2); }}
  .stat-pill.amber {{ background: rgba(210,153,34,.2); }}
  .section-title {{ font-size: .85rem; font-weight: 600; color: #fb923c; border-left: 3px solid #9a3412; padding-left: .6rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: .5px; }}
  .section-sep {{ display: flex; align-items: center; gap: 1rem; margin: 1.5rem 0 1rem; }}
  .section-sep::before, .section-sep::after {{ content: ""; flex: 1; height: 1px; background: var(--bs-border-color); }}
  .sep-badge {{ font-size: .78rem; font-weight: 700; padding: .3rem 1rem; border-radius: 20px; white-space: nowrap; }}
  .sep-orange {{ background: rgba(249,115,22,.12); color: #f97316; border: 1px solid #f9731644; }}
  .sep-amber  {{ background: rgba(210,153,34,.12); color: #d29922; border: 1px solid #d2992244; }}
  .chart-card {{ background: #161b22; border: 1px solid #30363d; border-radius: .75rem; padding: 1.25rem; }}
  .chart-card h3 {{ font-size: .82rem; color: #8b949e; margin-bottom: 1rem; }}
  .table-dark {{ --bs-table-bg: #161b22; --bs-table-hover-bg: #1f2937; --bs-table-border-color: #30363d; }}
  .table th {{ font-size: .72rem; white-space: nowrap; color: #fb923c; }}
  .table td {{ vertical-align: middle; }}
  .card {{ --bs-card-border-color: #30363d; }}
  .modal-content {{ background: #161b22; border: 1px solid #30363d; }}
  .modal-header {{ border-bottom: 1px solid #30363d; background: #0d1117; }}
  .modal-footer {{ border-top: 1px solid #30363d; background: #0d1117; }}
  .modal-metric {{ background: #0d1117; border-radius: .5rem; padding: .6rem .9rem; }}
  .modal-metric label {{ display: block; font-size: .65rem; color: #6e7681; margin-bottom: .2rem; }}
  .modal-metric span {{ font-size: .95rem; font-weight: 600; }}
  footer {{ font-size: .75rem; color: #6e7681; padding: 1.5rem; text-align: center; border-top: 1px solid #30363d; }}
  @media (max-width: 576px) {{ .hero {{ padding: 1.25rem 0 1rem; }} .stat-pill .val {{ font-size: 1.1rem; }} .table {{ font-size: .75rem; }} }}
</style>
</head>
<body>

{get_navbar("smallcap")}

<div class="hero">
  <div class="container-fluid px-3 px-md-4">
    <h1>Magic Formula <em>Small Cap US</em> &#128202; — S&amp;P 600</h1>
    <p class="text-light opacity-75 mb-3" style="font-size:.85rem">
      {now} · yfinance · S&amp;P 600 (~600 ações) · Metodologia Greenblatt · Análise Claude AI
    </p>
    <div class="d-flex flex-wrap gap-2">
      <div class="stat-pill"><div class="val">{total}</div><div class="lbl">S&amp;P 600 total</div></div>
      <div class="stat-pill"><div class="val">{apos_filtros}</div><div class="lbl">Após filtros</div></div>
      <div class="stat-pill"><div class="val">{apos_setor}</div><div class="lbl">Após setor limit</div></div>
      <div class="stat-pill"><div class="val">{n_total}</div><div class="lbl">Analisadas</div></div>
      <div class="stat-pill green"><div class="val">{n_comprar}</div><div class="lbl">✓ Comprar</div></div>
      <div class="stat-pill amber"><div class="val">{n_neutro}</div><div class="lbl">⚠ Neutro</div></div>
    </div>
  </div>
</div>

<div class="container-fluid px-3 px-md-4 py-4">

  <section class="mb-5">
    <div class="section-title">Tabela resumo — clique no ticker para abrir Yahoo Finance</div>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead>
          <tr>
            <th>#</th><th>Ticker</th><th>Setor</th><th>EV/EBIT</th><th>ROIC</th>
            <th>Score MF</th><th>Score IA</th><th>Rec.</th>
            <th>Mg EBIT</th><th>ROE</th><th>Dív/EBIT</th>
            <th>Liq Diária</th><th>CAGR Rec.</th><th>CAGR Luc.</th>
            <th>Mkt Cap</th><th>Motivo</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </section>

  <section class="mb-5">
    <div class="section-title">Gráficos</div>
    <div class="row g-3">
      <div class="col-12 col-lg-6">
        <div class="chart-card">
          <h3>ROIC — ações COMPRAR (%)</h3>
          <canvas id="chartRoic" style="max-height:280px"></canvas>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="chart-card">
          <h3>EV/EBIT vs ROIC · <span style="color:#f97316">●</span> COMPRAR <span style="color:#d29922">●</span> NEUTRO</h3>
          <canvas id="chartScatter" style="max-height:280px"></canvas>
        </div>
      </div>
    </div>
  </section>

  <section class="mb-5">
    <div class="section-title">Análise detalhada</div>
    <div class="section-sep"><span class="sep-badge sep-orange">✓ COMPRAR — {n_comprar} ações</span></div>
    <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3">{comprar_cards}</div>
    <div class="section-sep mt-5"><span class="sep-badge sep-amber">⚠ NEUTRO / CAUTELA — {n_neutro} ações</span></div>
    <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3">{neutro_cards}</div>
  </section>

{_build_removidos_section_mf(removidos)}

</div>

<footer>Magic Formula Small Cap US (S&amp;P 600) · {now} · Não é recomendação de investimento.</footer>

<div class="modal fade" id="tickerModal" tabindex="-1">
  <div class="modal-dialog modal-lg modal-dialog-scrollable modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header py-2">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span id="modalTicker" class="fw-bold" style="font-size:1.4rem;color:#fb923c">—</span>
          <span id="modalSetor" class="badge" style="background:#21262d;color:#8b949e;font-weight:400">—</span>
        </div>
        <button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="d-flex align-items-center gap-3 p-3 mb-3 rounded-2" style="background:#0d1117;border:1px solid #30363d;flex-wrap:wrap">
          <span id="modalRecBadge" class="badge fs-6">—</span>
          <span id="modalScore" class="text-secondary" style="font-size:.85rem">—</span>
          <span id="modalMotivo" class="text-secondary ms-auto" style="font-size:.82rem;max-width:320px;text-align:right">—</span>
        </div>
        <div class="row g-2" id="modalMetrics"></div>
      </div>
      <div class="modal-footer py-2">
        <a id="modalYFBtn" href="#" target="_blank" rel="noopener"
           class="btn w-100 fw-bold" style="background:#f97316;color:#fff">↗ Abrir no Yahoo Finance</a>
      </div>
    </div>
  </div>
</div>

<script>
const TICKER_DATA = {ticker_data_js};
const palette = ['#f97316','#fb923c','#fdba74','#fed7aa','#ea580c',
                 '#c2410c','#9a3412','#7c2d12','#f59e0b','#d97706'];

new Chart(document.getElementById('chartRoic'), {{
  type: 'bar',
  data: {{ labels: {json.dumps(tickers_js)}, datasets: [{{ label: 'ROIC (%)', data: {json.dumps(roics_js)}, backgroundColor: palette, borderRadius: 6 }}] }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => ` ${{c.parsed.y.toFixed(1)}}%` }} }} }},
    scales: {{ x: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }}, y: {{ ticks: {{ color: '#8b949e', callback: v => v + '%' }}, grid: {{ color: '#30363d' }} }} }}
  }}
}});

new Chart(document.getElementById('chartScatter'), {{
  type: 'scatter',
  data: {{ datasets: [{{ data: {json.dumps(all_tickers)}.map((t,i) => ({{ x: {json.dumps(all_evs)}[i], y: {json.dumps(all_roics)}[i], label: t }})), backgroundColor: {json.dumps(all_colors)}, pointRadius: 8, pointHoverRadius: 11 }}] }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => `${{c.raw.label}} · EV/EBIT ${{c.raw.x}} · ROIC ${{c.raw.y}}%` }} }} }},
    scales: {{ x: {{ title: {{ display: true, text: 'EV/EBIT', color: '#6e7681' }}, ticks: {{ color: '#8b949e' }}, grid: {{ color: '#30363d' }} }}, y: {{ title: {{ display: true, text: 'ROIC %', color: '#6e7681' }}, ticks: {{ color: '#8b949e', callback: v => v + '%' }}, grid: {{ color: '#30363d' }} }} }}
  }}
}});

function colorRec(r) {{ return r === 'COMPRAR' ? '#f97316' : r === 'CAUTELA' ? '#f85149' : '#d29922'; }}
function colorROIC(v) {{ return v >= 20 ? '#3fb950' : v >= 10 ? '#d29922' : '#f85149'; }}
function colorEV(v)   {{ return v <= 5  ? '#3fb950' : v <= 12  ? '#d29922' : '#f85149'; }}
function colorDiv(v)  {{ return v < 0   ? '#3fb950' : v < 2    ? '#d29922' : '#f85149'; }}
function fmt(v,d=2)   {{ return (v == null || isNaN(v)) ? '—' : Number(v).toFixed(d); }}
function fmtUSD(v) {{
  if (v == null || isNaN(v)) return '—';
  if (v >= 1e12) return '$' + (v/1e12).toFixed(1) + 'T';
  if (v >= 1e9)  return '$' + (v/1e9).toFixed(1) + 'B';
  if (v >= 1e6)  return '$' + (v/1e6).toFixed(1) + 'M';
  return '$' + v.toLocaleString();
}}

function openModal(ticker) {{
  const d = TICKER_DATA[ticker];
  if (!d) return;
  $('#modalTicker').text(ticker);
  $('#modalSetor').text(d.setor || '—');
  const c = colorRec(d.recomendacao);
  $('#modalRecBadge').text(d.recomendacao || '—').css('background', c);
  $('#modalScore').html(`Score IA: <strong style="color:#fb923c">${{d.score_ia ?? '—'}}/10</strong>`);
  $('#modalMotivo').text(d.motivo || '');
  const metrics = [
    ['EV/EBIT', fmt(d.ev_ebit)+'x', colorEV(d.ev_ebit)],
    ['ROIC', fmt(d.roic)+'%', colorROIC(d.roic)],
    ['Mg EBIT', fmt(d.margem)+'%', ''],
    ['ROE', fmt(d.roe)+'%', ''],
    ['Dív/EBIT', fmt(d.div_ebit)+'x', colorDiv(d.div_ebit)],
    ['CAGR Receita', fmt(d.cagr_r)+'%', ''],
    ['CAGR Lucro', fmt(d.cagr_l)+'%', ''],
    ['Mkt Cap', fmtUSD(d.vm), ''],
    ['Liq Diária', fmtUSD(d.liq), ''],
    ['Preço', d.preco ? '$'+fmt(d.preco) : '—', ''],
  ];
  $('#modalMetrics').html(metrics.map(([l,v,c]) =>
    `<div class="col-6 col-sm-4 col-md-3"><div class="modal-metric"><label>${{l}}</label><span style="color:${{c||'#e6edf3'}}">${{v}}</span></div></div>`
  ).join(''));
  $('#modalYFBtn').attr('href', `https://finance.yahoo.com/quote/${{ticker}}`);
  bootstrap.Modal.getOrCreateInstance(document.getElementById('tickerModal')).show();
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[report_smallcap] HTML gerado: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--analysis", default="")
    parser.add_argument("--analysis-file", default="")
    parser.add_argument("--output", default=None)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    analyses = {}
    if args.analysis_file and Path(args.analysis_file).exists():
        with open(args.analysis_file, encoding="utf-8") as f:
            analyses = json.load(f)
    elif args.analysis:
        try: analyses = json.loads(args.analysis)
        except Exception: analyses = {}

    out = args.output or str(Path(args.json).parent / "relatorio_smallcap.html")
    generate_html_sc(data, analyses, out, top_n=args.top)
