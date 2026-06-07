import argparse
import json
import sys
from pathlib import Path
from datetime import datetime


def _fmt(val, decimals=2, suffix=""):
    if val is None or val != val:
        return "—"
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except Exception:
        return str(val)


def _fmt_brl(val):
    if val is None or val != val:
        return "—"
    try:
        v = float(val)
        if v >= 1_000_000_000:
            return f"R$ {v/1_000_000_000:.1f}B"
        if v >= 1_000_000:
            return f"R$ {v/1_000_000:.1f}M"
        return f"R$ {v:,.0f}"
    except Exception:
        return str(val)


def _color_roic(v):
    try:
        f = float(v)
        if f >= 20: return "#3fb950"
        if f >= 10: return "#d29922"
        return "#f85149"
    except Exception:
        return "#8b949e"


def _color_ev(v):
    try:
        f = float(v)
        if f <= 5:  return "#3fb950"
        if f <= 12: return "#d29922"
        return "#f85149"
    except Exception:
        return "#8b949e"


def _color_div(v):
    try:
        f = float(v)
        if f < 0:  return "#3fb950"
        if f < 2:  return "#d29922"
        return "#f85149"
    except Exception:
        return "#8b949e"


def _motivo(ag, c, group):
    if ag.get("motivo"):
        return ag["motivo"]
    if group == "COMPRAR":
        pontos = ag.get("pontos_fortes", [])
        return pontos[0] if pontos else "Bom balanço qualidade/valuation"
    riscos = ag.get("riscos", [])
    qualidade = ag.get("qualidade_roic", "")
    cagr_l = c.get("CAGR LUCROS 5 ANOS")
    div = c.get("DIVIDA LIQUIDA / EBIT", 0)
    margem = c.get("MARGEM EBIT", 0)
    if isinstance(cagr_l, float) and cagr_l == cagr_l and cagr_l < 0:
        return f"CAGR Lucros 5a negativo ({cagr_l:.1f}%)"
    if isinstance(div, float) and div > 3:
        return f"Dívida/EBIT elevada ({div:.1f}x)"
    if isinstance(margem, float) and margem < 7:
        return f"Margem EBIT baixa ({margem:.1f}%)"
    if qualidade in ("PONTUAL", "INCERTO"):
        return riscos[0] if riscos else "ROIC sem tendência sustentável"
    return riscos[0] if riscos else "Qualidade operacional abaixo do limiar"


def _badge_rec(rec):
    colors = {"COMPRAR": "#3fb950", "NEUTRO": "#d29922", "CAUTELA": "#f85149"}
    c = colors.get(rec, "#8b949e")
    return f'<span class="badge" style="background:{c}22;color:{c};border:1px solid {c}55;font-size:.7rem">{rec}</span>'


def _build_card(c, ag, rank, group):
    ticker = c["TICKER"]
    pos = c.get("posicao_mf", "—")
    ev = c.get("EV/EBIT")
    roic = c.get("ROIC")
    score = c.get("mf_score")
    margem = c.get("MARGEM EBIT")
    roe = c.get("ROE")
    div = c.get("DIVIDA LIQUIDA / EBIT")
    liq = c.get("LIQUIDEZ MEDIA DIARIA")
    cagr_r = c.get("CAGR RECEITAS 5 ANOS")
    cagr_l = c.get("CAGR LUCROS 5 ANOS")
    vm = c.get("VALOR DE MERCADO")
    preco = c.get("PRECO")

    score_ia = ag.get("score_compra", "—")
    recomendacao = ag.get("recomendacao", "")
    motivo_text = _motivo(ag, c, group)

    border_color = "#3fb950" if group == "COMPRAR" else "#d29922"
    motivo_bg = "rgba(63,185,80,.1)" if group == "COMPRAR" else "rgba(210,153,34,.1)"
    motivo_border = "#3fb95033" if group == "COMPRAR" else "#d2992233"
    motivo_icon = "✓" if group == "COMPRAR" else "⚠"
    motivo_label = "Por que COMPRAR" if group == "COMPRAR" else "Por que NEUTRO"

    metrics = [
        ("EV/EBIT",      f"{_fmt(ev)}x",      _color_ev(ev)),
        ("ROIC",         f"{_fmt(roic)}%",     _color_roic(roic)),
        ("Mg EBIT",      f"{_fmt(margem)}%",   ""),
        ("ROE",          f"{_fmt(roe)}%",      ""),
        ("Dív/EBIT",     f"{_fmt(div)}x",      _color_div(div)),
        ("CAGR Rec.",    f"{_fmt(cagr_r)}%",   ""),
        ("CAGR Luc.",    f"{_fmt(cagr_l)}%",   ""),
        ("Val. Mercado", _fmt_brl(vm),         ""),
        ("Preço",        f"R$ {_fmt(preco)}",  ""),
        ("Liq. Diária",  _fmt_brl(liq),        ""),
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
          <span class="fw-bold ticker-clickable" style="font-size:1.1rem;color:#58a6ff;cursor:pointer"
                onclick="openModal('{ticker}')" title="Clique para detalhes">{ticker}</span>
          <span class="text-muted ms-auto" style="font-size:.7rem">MF #{pos} · {_fmt(score,0)}</span>
        </div>
        <div class="card-body pb-2">
          <div class="row g-2 mb-3">{metrics_html}</div>
          <div class="d-flex align-items-center gap-2 mb-2 flex-wrap">
            {_badge_rec(recomendacao)}
            <span class="text-muted" style="font-size:.75rem">Score IA:</span>
            <span class="fw-bold" style="color:#bc8cff">{score_ia}/10</span>
          </div>
          <div class="rounded-2 p-2" style="background:{motivo_bg};border:1px solid {motivo_border};font-size:.78rem">
            <span style="color:{border_color}">{motivo_icon}</span>
            <span class="text-muted fw-semibold"> {motivo_label}: </span>
            <span style="color:#e6edf3">{motivo_text}</span>
          </div>
        </div>
      </div>
    </div>"""


def _table_row(c, ag, rank, group):
    ticker = c["TICKER"]
    pos = c.get("posicao_mf", "—")
    ev = c.get("EV/EBIT")
    roic = c.get("ROIC")
    score = c.get("mf_score")
    margem = c.get("MARGEM EBIT")
    roe = c.get("ROE")
    div = c.get("DIVIDA LIQUIDA / EBIT")
    liq = c.get("LIQUIDEZ MEDIA DIARIA")
    cagr_r = c.get("CAGR RECEITAS 5 ANOS")
    cagr_l = c.get("CAGR LUCROS 5 ANOS")
    vm = c.get("VALOR DE MERCADO")

    score_ia = ag.get("score_compra", "—")
    recomendacao = ag.get("recomendacao", "")
    motivo = _motivo(ag, c, group)
    motivo_short = motivo[:65] + "…" if len(motivo) > 65 else motivo

    return f"""
    <tr>
      <td class="text-center fw-bold text-secondary">{rank}</td>
      <td><span class="fw-bold ticker-clickable" style="color:#58a6ff;cursor:pointer;font-size:.95rem"
               onclick="openModal('{ticker}')" title="Clique para detalhes">{ticker}</span></td>
      <td class="text-center fw-semibold" style="color:{_color_ev(ev)}">{_fmt(ev)}x</td>
      <td class="text-center fw-semibold" style="color:{_color_roic(roic)}">{_fmt(roic)}%</td>
      <td class="text-center text-secondary">{_fmt(score,0)}</td>
      <td class="text-center fw-bold" style="color:#bc8cff">{score_ia}/10</td>
      <td class="text-center">{_badge_rec(recomendacao)}</td>
      <td class="text-center text-secondary">{_fmt(margem)}%</td>
      <td class="text-center text-secondary">{_fmt(roe)}%</td>
      <td class="text-center fw-semibold" style="color:{_color_div(div)}">{_fmt(div)}x</td>
      <td class="text-center text-secondary" style="font-size:.8rem">{_fmt_brl(liq)}</td>
      <td class="text-center text-secondary">{_fmt(cagr_r)}%</td>
      <td class="text-center text-secondary">{_fmt(cagr_l)}%</td>
      <td class="text-center text-secondary" style="font-size:.8rem">{_fmt_brl(vm)}</td>
      <td style="font-size:.72rem;color:#8b949e;max-width:160px">{motivo_short}</td>
    </tr>"""


def _build_ticker_data(candidates: list, analyses: dict) -> dict:
    cand_map = {c["TICKER"]: c for c in candidates}
    result = {}
    for ticker, ag in analyses.items():
        c = cand_map.get(ticker, {})
        hist = c.get("historico", {})
        result[ticker] = {
            "ticker": ticker,
            "setor": c.get("setor", "—"),
            "posicao_mf": c.get("posicao_mf", "—"),
            "mf_score": c.get("mf_score"),
            "ev_ebit": c.get("EV/EBIT"),
            "roic": c.get("ROIC"),
            "margem": c.get("MARGEM EBIT"),
            "roe": c.get("ROE"),
            "div_ebit": c.get("DIVIDA LIQUIDA / EBIT"),
            "cagr_r": c.get("CAGR RECEITAS 5 ANOS"),
            "cagr_l": c.get("CAGR LUCROS 5 ANOS"),
            "vm": c.get("VALOR DE MERCADO"),
            "liq": c.get("LIQUIDEZ MEDIA DIARIA"),
            "preco": c.get("PRECO"),
            "trend_roic": hist.get("roic_tendencia", ""),
            "trend_margin": hist.get("margem_tendencia", ""),
            "trend_revenue": hist.get("receita_tendencia", ""),
            "recomendacao": ag.get("recomendacao", ""),
            "score_ia": ag.get("score_compra", ""),
            "motivo": ag.get("motivo") or (ag.get("pontos_fortes", [""])[0] if ag.get("pontos_fortes") else ""),
        }
    return result


def generate_html(data: dict, analyses: dict, output_path: str, top_n: int = 15):
    cand_lookup = {c["TICKER"]: c for c in data["candidatos"]}
    data_exec = data.get("data_execucao", "")
    total_csv = data.get("total_empresas_csv", "—")
    apos_filtros = data.get("apos_filtros", "—")
    apos_rj = data.get("apos_rj_check", "—")

    comprar_list, neutro_list = [], []
    for ticker, ag in analyses.items():
        if ticker not in cand_lookup:
            continue
        if isinstance(ag, str):
            try: ag = json.loads(ag)
            except Exception: ag = {"motivo": ag}
        rec = ag.get("recomendacao", "NEUTRO")
        score_ia = ag.get("score_compra", 0) or 0
        mf = cand_lookup[ticker].get("mf_score", 999)
        if rec == "COMPRAR":
            comprar_list.append((ticker, ag, score_ia, mf))
        else:
            neutro_list.append((ticker, ag, score_ia, mf))

    comprar_list.sort(key=lambda x: (-x[2], x[3]))
    neutro_list.sort(key=lambda x: (-x[2], x[3]))

    n_comprar = len(comprar_list)
    n_neutro = len(neutro_list)
    n_total = n_comprar + n_neutro

    rows_html = (
        f'<tr style="background:#0a2218"><td colspan="15" class="py-2 px-3 fw-bold" style="color:#3fb950;font-size:.75rem;letter-spacing:.5px">▼ COMPRAR — {n_comprar} ações</td></tr>'
        + "".join(_table_row(cand_lookup[t], ag, r+1, "COMPRAR") for r,(t,ag,*_) in enumerate(comprar_list))
        + f'<tr style="background:#1a1000"><td colspan="15" class="py-2 px-3 fw-bold" style="color:#d29922;font-size:.75rem;letter-spacing:.5px">▼ NEUTRO / CAUTELA — {n_neutro} ações</td></tr>'
        + "".join(_table_row(cand_lookup[t], ag, r+1, "NEUTRO") for r,(t,ag,*_) in enumerate(neutro_list))
    )

    comprar_cards = "".join(_build_card(cand_lookup[t], ag, r+1, "COMPRAR") for r,(t,ag,*_) in enumerate(comprar_list))
    neutro_cards  = "".join(_build_card(cand_lookup[t], ag, r+1, "NEUTRO")  for r,(t,ag,*_) in enumerate(neutro_list))

    tickers_js    = [t for t,*_ in comprar_list]
    roics_js      = [round(float(cand_lookup[t].get("ROIC") or 0), 2) for t in tickers_js]
    all_tickers   = [t for t,*_ in comprar_list + neutro_list]
    all_roics     = [round(float(cand_lookup[t].get("ROIC") or 0), 2) for t in all_tickers]
    all_evs       = [round(float(cand_lookup[t].get("EV/EBIT") or 0), 2) for t in all_tickers]
    all_colors    = ["#3fb950" if t in {x[0] for x in comprar_list} else "#d29922" for t in all_tickers]

    ticker_data    = _build_ticker_data(data["candidatos"], analyses)
    ticker_data_js = json.dumps(ticker_data, ensure_ascii=False)
    now            = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Magic Formula BR</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  [data-bs-theme=dark] {{
    --bs-body-bg: #0d1117;
    --bs-body-color: #e6edf3;
    --bs-card-bg: #161b22;
    --bs-border-color: #30363d;
  }}
  body {{ font-family: -apple-system, 'Segoe UI', system-ui, sans-serif; }}
  .hero {{
    background: linear-gradient(135deg, #0d1b3e 0%, #1a2f6b 50%, #1d4ed8 100%);
    padding: 2rem 0 1.5rem;
  }}
  .hero h1 {{ font-size: clamp(1.4rem, 4vw, 2rem); font-weight: 700; letter-spacing: -.5px; }}
  .hero h1 em {{ font-style: normal; color: #93c5fd; }}
  .stat-pill {{
    background: rgba(255,255,255,.1); border-radius: .75rem;
    padding: .6rem 1.1rem; text-align: center;
  }}
  .stat-pill .val {{ font-size: 1.4rem; font-weight: 700; color: #fff; line-height: 1.2; }}
  .stat-pill .lbl {{ font-size: .68rem; color: #bfdbfe; }}
  .stat-pill.green {{ background: rgba(63,185,80,.2); }}
  .stat-pill.amber {{ background: rgba(210,153,34,.2); }}

  .section-title {{
    font-size: .85rem; font-weight: 600; color: #58a6ff;
    border-left: 3px solid #1d4ed8; padding-left: .6rem; margin-bottom: 1rem;
    text-transform: uppercase; letter-spacing: .5px;
  }}
  .section-sep {{
    display: flex; align-items: center; gap: 1rem; margin: 1.5rem 0 1rem;
  }}
  .section-sep::before, .section-sep::after {{
    content: ""; flex: 1; height: 1px; background: var(--bs-border-color);
  }}
  .sep-badge {{
    font-size: .78rem; font-weight: 700; padding: .3rem 1rem;
    border-radius: 20px; white-space: nowrap;
  }}
  .sep-green {{ background: rgba(63,185,80,.12); color: #3fb950; border: 1px solid #3fb95044; }}
  .sep-amber {{ background: rgba(210,153,34,.12); color: #d29922; border: 1px solid #d2992244; }}

  .ticker-clickable {{ cursor: pointer; transition: color .15s; }}
  .ticker-clickable:hover {{ color: #93c5fd !important; text-decoration: underline; }}

  .table-dark {{ --bs-table-bg: #161b22; --bs-table-hover-bg: #1f2937; --bs-table-border-color: #30363d; }}
  .table th {{ font-size: .72rem; white-space: nowrap; color: #58a6ff; }}
  .table td {{ vertical-align: middle; }}

  .chart-card {{ background: #161b22; border: 1px solid #30363d; border-radius: .75rem; padding: 1.25rem; }}
  .chart-card h3 {{ font-size: .82rem; color: #8b949e; margin-bottom: 1rem; }}

  .card {{ --bs-card-border-color: #30363d; }}
  .card-header {{ font-size: .82rem; }}

  footer {{ font-size: .75rem; color: #6e7681; padding: 1.5rem; text-align: center; border-top: 1px solid #30363d; }}

  /* Modal overrides */
  .modal-content {{ background: #161b22; border: 1px solid #30363d; }}
  .modal-header {{ border-bottom: 1px solid #30363d; background: #0d1117; }}
  .modal-footer {{ border-top: 1px solid #30363d; background: #0d1117; }}
  .modal-metric {{ background: #0d1117; border-radius: .5rem; padding: .6rem .9rem; }}
  .modal-metric label {{ display: block; font-size: .65rem; color: #6e7681; margin-bottom: .2rem; }}
  .modal-metric span {{ font-size: .95rem; font-weight: 600; }}
  .trend-pill {{ font-size: .7rem; font-weight: 600; padding: .2rem .7rem; border-radius: 4px; }}
  .trend-CRESCENTE   {{ color: #3fb950; background: rgba(63,185,80,.12); }}
  .trend-DECRESCENTE {{ color: #f85149; background: rgba(248,81,73,.12); }}
  .trend-ESTAVEL     {{ color: #58a6ff; background: rgba(88,166,255,.12); }}
  .trend-VOLATIL     {{ color: #d29922; background: rgba(210,153,34,.12); }}
  .trend-INSUFICIENTE {{ color: #6e7681; background: rgba(110,118,129,.12); }}

  @media (max-width: 576px) {{
    .hero {{ padding: 1.25rem 0 1rem; }}
    .stat-pill .val {{ font-size: 1.1rem; }}
    .table {{ font-size: .75rem; }}
  }}
</style>
</head>
<body>

<!-- ── Hero ──────────────────────────────────────────────────────────────── -->
<div class="hero">
  <div class="container-fluid px-3 px-md-4">
    <h1>Magic Formula <em>BR</em> — Análise IA</h1>
    <p class="text-light opacity-75 mb-3" style="font-size:.85rem">
      {now} · StatusInvest · Metodologia Greenblatt · Análise Claude AI
    </p>
    <div class="d-flex flex-wrap gap-2">
      <div class="stat-pill"><div class="val">{total_csv}</div><div class="lbl">CSV</div></div>
      <div class="stat-pill"><div class="val">{apos_filtros}</div><div class="lbl">Após filtros</div></div>
      <div class="stat-pill"><div class="val">{apos_rj}</div><div class="lbl">Após RJ check</div></div>
      <div class="stat-pill"><div class="val">{n_total}</div><div class="lbl">Analisadas</div></div>
      <div class="stat-pill green"><div class="val">{n_comprar}</div><div class="lbl">✓ Comprar</div></div>
      <div class="stat-pill amber"><div class="val">{n_neutro}</div><div class="lbl">⚠ Neutro</div></div>
    </div>
  </div>
</div>

<div class="container-fluid px-3 px-md-4 py-4">

  <!-- ── Tabela ──────────────────────────────────────────────────────────── -->
  <section class="mb-5">
    <div class="section-title">Tabela resumo — clique no ticker para detalhes</div>
    <div class="d-flex gap-3 mb-2 flex-wrap" style="font-size:.75rem">
      <span><span style="color:#3fb950">●</span> Ótimo</span>
      <span><span style="color:#d29922">●</span> Moderado</span>
      <span><span style="color:#f85149">●</span> Atenção</span>
    </div>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead>
          <tr>
            <th>#</th><th>Ticker</th><th>EV/EBIT</th><th>ROIC</th>
            <th>Score MF</th><th>Score IA</th><th>Rec.</th>
            <th>Mg EBIT</th><th>ROE</th><th>Dív/EBIT</th>
            <th>Liq Diária</th><th>CAGR Rec.</th><th>CAGR Luc.</th>
            <th>Val. Mercado</th><th>Motivo</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </section>

  <!-- ── Gráficos ────────────────────────────────────────────────────────── -->
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
          <h3>EV/EBIT vs ROIC · <span style="color:#3fb950">●</span> COMPRAR <span style="color:#d29922">●</span> NEUTRO</h3>
          <canvas id="chartScatter" style="max-height:280px"></canvas>
        </div>
      </div>
    </div>
  </section>

  <!-- ── Cards COMPRAR ───────────────────────────────────────────────────── -->
  <section class="mb-5">
    <div class="section-title">Análise detalhada</div>
    <div class="section-sep">
      <span class="sep-badge sep-green">✓ COMPRAR — {n_comprar} ações</span>
    </div>
    <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3">
      {comprar_cards}
    </div>

    <div class="section-sep mt-5">
      <span class="sep-badge sep-amber">⚠ NEUTRO / CAUTELA — {n_neutro} ações</span>
    </div>
    <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3">
      {neutro_cards}
    </div>
  </section>

  <!-- ── Metodologia ─────────────────────────────────────────────────────── -->
  <section class="mb-4">
    <div class="section-title">Metodologia</div>
    <div class="card">
      <div class="card-body text-secondary" style="font-size:.85rem;line-height:1.7">
        <p><strong class="text-light">Magic Formula</strong> — Joel Greenblatt ("The Little Book That Beats the Market", 2005).
        Objetivo: encontrar <em>boas empresas a preços baratos</em> de forma sistemática.</p>
        <div class="row g-3 mt-1">
          <div class="col-md-6">
            <strong class="text-light">EV/EBIT</strong> — múltiplo de valuation. Menor = mais barato.<br>
            <strong class="text-light">ROIC</strong> — retorno sobre capital investido. Maior = melhor qualidade.<br>
            Menor <strong>Score MF</strong> (soma dos rankings) = empresa barata E boa.
          </div>
          <div class="col-md-6">
            <strong class="text-light">COMPRAR:</strong> ROIC sustentável · CAGR Lucros positivo · dívida controlada.<br>
            <strong class="text-light">NEUTRO:</strong> CAGR Lucros negativo · Dív/EBIT &gt; 3x · margem &lt; 7%.<br>
            <strong class="text-light">EVAL:</strong> validação automática — IA não pode contradizer os números.
          </div>
        </div>
      </div>
    </div>
  </section>

</div>

<footer>Magic Formula BR · {now} · Não é recomendação de investimento.</footer>

<!-- ── Modal Bootstrap ─────────────────────────────────────────────────────── -->
<div class="modal fade" id="tickerModal" tabindex="-1">
  <div class="modal-dialog modal-lg modal-dialog-scrollable modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header py-2">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span id="modalTicker" class="fw-bold" style="font-size:1.4rem;color:#58a6ff">—</span>
          <span id="modalSetor" class="badge" style="background:#21262d;color:#8b949e;font-weight:400">—</span>
          <span id="modalMF" class="badge" style="background:#21262d;color:#8b949e;font-weight:400">—</span>
        </div>
        <button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <!-- Rec row -->
        <div class="d-flex align-items-center gap-3 p-3 mb-3 rounded-2" style="background:#0d1117;border:1px solid #30363d;flex-wrap:wrap">
          <span id="modalRecBadge" class="badge fs-6">—</span>
          <span id="modalScore" class="text-secondary" style="font-size:.85rem">—</span>
          <span id="modalMotivo" class="text-secondary ms-auto" style="font-size:.82rem;max-width:320px;text-align:right">—</span>
        </div>
        <!-- Metrics grid -->
        <div class="row g-2 mb-3" id="modalMetrics"></div>
        <!-- Trends -->
        <div id="modalTrendsBox" style="display:none">
          <div class="p-3 rounded-2 mb-3" style="background:#0d1117;border:1px solid #30363d">
            <div class="text-uppercase text-muted mb-2" style="font-size:.65rem;font-weight:700;letter-spacing:.5px">Tendências Históricas</div>
            <div class="d-flex gap-3 flex-wrap" id="modalTrends"></div>
          </div>
        </div>
      </div>
      <div class="modal-footer py-2">
        <a id="modalSIBtn" href="#" target="_blank" rel="noopener"
           class="btn btn-primary w-100 fw-bold" style="letter-spacing:.3px">
          ↗ Abrir no StatusInvest
        </a>
      </div>
    </div>
  </div>
</div>

<script>
const TICKER_DATA = {ticker_data_js};

// ── Charts ────────────────────────────────────────────────────────────────
const palette = ['#3fb950','#58a6ff','#d29922','#f85149','#bc8cff',
                 '#39d353','#79c0ff','#e3b341','#ffa198','#d2a8ff',
                 '#56d364','#a5d6ff','#f0883e','#ff7b72','#c9d1d9'];

new Chart(document.getElementById('chartRoic'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(tickers_js)},
    datasets: [{{ label: 'ROIC (%)', data: {json.dumps(roics_js)}, backgroundColor: palette, borderRadius: 6 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => ` ${{c.parsed.y.toFixed(1)}}%` }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }},
      y: {{ ticks: {{ color: '#8b949e', callback: v => v + '%' }}, grid: {{ color: '#30363d' }} }}
    }}
  }}
}});

new Chart(document.getElementById('chartScatter'), {{
  type: 'scatter',
  data: {{
    datasets: [{{
      data: {json.dumps(all_tickers)}.map((t,i) => ({{ x: {json.dumps(all_evs)}[i], y: {json.dumps(all_roics)}[i], label: t }})),
      backgroundColor: {json.dumps(all_colors)},
      pointRadius: 8, pointHoverRadius: 11,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: c => `${{c.raw.label}} · EV/EBIT ${{c.raw.x}} · ROIC ${{c.raw.y}}%` }} }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'EV/EBIT (menor = mais barato)', color: '#6e7681' }}, ticks: {{ color: '#8b949e' }}, grid: {{ color: '#30363d' }} }},
      y: {{ title: {{ display: true, text: 'ROIC % (maior = melhor)', color: '#6e7681' }}, ticks: {{ color: '#8b949e', callback: v => v + '%' }}, grid: {{ color: '#30363d' }} }}
    }}
  }}
}});

// ── Modal ─────────────────────────────────────────────────────────────────
function fmt(v, d=2, s='') {{
  if (v == null || isNaN(v)) return '—';
  return Number(v).toFixed(d) + s;
}}
function fmtBRL(v) {{
  if (v == null || isNaN(v)) return '—';
  if (v >= 1e9) return 'R$ ' + (v/1e9).toFixed(1) + 'B';
  if (v >= 1e6) return 'R$ ' + (v/1e6).toFixed(1) + 'M';
  return 'R$ ' + v.toLocaleString('pt-BR', {{maximumFractionDigits:0}});
}}
function colorROIC(v) {{ return v >= 20 ? '#3fb950' : v >= 10 ? '#d29922' : '#f85149'; }}
function colorEV(v)   {{ return v <= 5  ? '#3fb950' : v <= 12  ? '#d29922' : '#f85149'; }}
function colorDiv(v)  {{ return v < 0   ? '#3fb950' : v < 2    ? '#d29922' : '#f85149'; }}
function colorRec(r)  {{ return r === 'COMPRAR' ? '#3fb950' : r === 'CAUTELA' ? '#f85149' : '#d29922'; }}

function openModal(ticker) {{
  const d = TICKER_DATA[ticker];
  if (!d) return;

  $('#modalTicker').text(ticker);
  $('#modalSetor').text(d.setor || '—');
  $('#modalMF').text(d.posicao_mf ? `MF #${{d.posicao_mf}} · Score ${{d.mf_score ?? '—'}}` : '—');

  const rec = d.recomendacao || '—';
  const c = colorRec(rec);
  $('#modalRecBadge').text(rec).css('background', c);
  $('#modalScore').html(`Score IA: <strong style="color:#bc8cff;font-size:1rem">${{d.score_ia ?? '—'}}/10</strong>`);
  $('#modalMotivo').text(d.motivo || '');

  const metrics = [
    ['EV/EBIT',     fmt(d.ev_ebit)+'x',   colorEV(d.ev_ebit)],
    ['ROIC',        fmt(d.roic)+'%',       colorROIC(d.roic)],
    ['Mg EBIT',     fmt(d.margem)+'%',     ''],
    ['ROE',         fmt(d.roe)+'%',        ''],
    ['Dív/EBIT',    fmt(d.div_ebit)+'x',   colorDiv(d.div_ebit)],
    ['CAGR Receita',fmt(d.cagr_r)+'%',    ''],
    ['CAGR Lucro',  fmt(d.cagr_l)+'%',    ''],
    ['Val. Mercado',fmtBRL(d.vm),          ''],
    ['Liq Diária',  fmtBRL(d.liq),         ''],
    ['Preço',       d.preco ? 'R$ '+fmt(d.preco) : '—', ''],
  ];
  $('#modalMetrics').html(metrics.map(([l,v,c]) =>
    `<div class="col-6 col-sm-4 col-md-3">
       <div class="modal-metric">
         <label>${{l}}</label>
         <span style="color:${{c||'#e6edf3'}}">${{v}}</span>
       </div>
     </div>`
  ).join(''));

  const trends = [
    ['ROIC Trimestral', d.trend_roic],
    ['Margem EBIT',     d.trend_margin],
    ['Receita',         d.trend_revenue],
  ].filter(([,v]) => v);

  if (trends.length) {{
    $('#modalTrends').html(trends.map(([l,v]) =>
      `<div><div style="font-size:.65rem;color:#6e7681;margin-bottom:2px">${{l}}</div>
       <span class="trend-pill trend-${{v}}">${{v}}</span></div>`
    ).join(''));
    $('#modalTrendsBox').show();
  }} else {{
    $('#modalTrendsBox').hide();
  }}

  $('#modalSIBtn').attr('href', `https://statusinvest.com.br/acoes/${{ticker.toLowerCase()}}`);
  bootstrap.Modal.getOrCreateInstance(document.getElementById('tickerModal')).show();
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[report] HTML gerado: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--analysis", default="")
    parser.add_argument("--analysis-file", default="")
    parser.add_argument("--output", default=None)
    parser.add_argument("--top", type=int, default=15)
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

    out = args.output or str(Path(args.json).parent / "relatorio.html")
    generate_html(data, analyses, out, top_n=args.top)
