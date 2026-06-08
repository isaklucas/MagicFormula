"""
Gera relatório HTML do backtest FII — DY Limpo vs IFIX.
"""

import argparse
import json
import urllib.request
from pathlib import Path
from datetime import datetime

from navbar import get_navbar


def _fetch_cdi_monthly(start_ym: str, end_ym: str) -> dict:
    try:
        s = start_ym.replace("-", "")
        e = end_ym.replace("-", "")
        d_ini = f"01/{s[4:6]}/{s[:4]}"
        d_fim = f"01/{e[4:6]}/{e[:4]}"
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados"
            f"?formato=json&dataInicial={d_ini}&dataFinal={d_fim}"
        )
        with urllib.request.urlopen(url, timeout=8) as r:
            rows = json.loads(r.read())
        result = {}
        for row in rows:
            parts = row["data"].split("/")
            ym    = f"{parts[2]}-{parts[1]}"
            result[ym] = float(row["valor"])
        return result
    except Exception:
        return {}


def _build_cdi_series(cdi_monthly: dict, labels: list) -> list:
    acc    = 100.0
    series = []
    for lbl in labels:
        rate = cdi_monthly.get(lbl)
        if rate is not None:
            acc *= (1 + rate / 100)
        series.append(round(acc, 2))
    return series


def _track_performance(monthly: list) -> tuple:
    entry_tracker: dict = {}
    closed: list        = []

    for r in monthly:
        det_map      = {det["ticker"]: det for det in r.get("detalhes", [])}
        precos_saida = r.get("precos_saida", {})
        month        = r["data"][:7]

        for t in r.get("entradas", []):
            if t in det_map and det_map[t].get("preco"):
                entry_tracker[t] = {"price": det_map[t]["preco"], "date": month}

        for t in r.get("saidas", []):
            if t in entry_tracker:
                ep  = entry_tracker[t]["price"]
                xp  = precos_saida.get(t)
                pnl = round((xp / ep - 1) * 100, 1) if ep and xp else None
                closed.append({
                    "ticker":       t,
                    "entry":        entry_tracker[t]["date"],
                    "exit":         month,
                    "entry_price":  ep,
                    "exit_price":   xp,
                    "pnl_pct":      pnl,
                })
                del entry_tracker[t]

    last_month = next((r for r in reversed(monthly) if r.get("top15")), None)
    open_pos   = []
    if last_month:
        det_map = {det["ticker"]: det for det in last_month.get("detalhes", [])}
        for t, entry in entry_tracker.items():
            ep  = entry["price"]
            det = det_map.get(t, {})
            cp  = det.get("preco")
            pnl = round((cp / ep - 1) * 100, 1) if ep and cp else None
            open_pos.append({
                "ticker":        t,
                "entry":         entry["date"],
                "entry_price":   ep,
                "current_price": cp,
                "pnl_pct":       pnl,
                "dy_limpo":      det.get("dy_limpo"),
                "pvp":           det.get("pvp"),
            })
        open_pos.sort(key=lambda x: -(x.get("dy_limpo") or 0))

    closed.sort(key=lambda x: x["pnl_pct"] if x["pnl_pct"] is not None else -999, reverse=True)
    return closed, open_pos


def generate_backtest_fii_html(data: dict, output_path: str):
    stats    = data.get("stats", {})
    monthly  = data.get("monthly", [])
    ifix_acc = data.get("ifix_acumulado", [])

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    active_indices = [i for i, r in enumerate(monthly) if r.get("top15")]
    if active_indices:
        active_monthly = [monthly[i] for i in active_indices]
        active_ifix    = [ifix_acc[i] if i < len(ifix_acc) else ifix_acc[-1] for i in active_indices]
        fii_start      = active_monthly[0]["portfolio_valor"]
        ifix_start     = active_ifix[0]
        fii_values     = [round(r["portfolio_valor"] / fii_start * 100, 2) for r in active_monthly]
        ifix_values    = [round(v / ifix_start * 100, 2) for v in active_ifix]
    else:
        active_monthly = monthly
        fii_values     = [r["portfolio_valor"] for r in monthly]
        ifix_values    = ifix_acc[:len(monthly)]

    labels       = [r["data"][:7] for r in active_monthly]
    monthly_rets = [r["retorno_mes_pct"] if r["retorno_mes_pct"] is not None else 0 for r in active_monthly]
    bar_colors   = ["rgba(56,189,248,.85)" if v >= 0 else "rgba(239,68,68,.85)" for v in monthly_rets]
    dy_medio_vals = [r.get("dy_medio_pct") for r in active_monthly]
    ifix_dy_vals  = [r.get("ifix_dy_pct")  for r in active_monthly]
    has_dy_chart  = any(v is not None for v in dy_medio_vals)

    cdi_monthly_rates = _fetch_cdi_monthly(labels[0], labels[-1]) if labels else {}
    cdi_values        = _build_cdi_series(cdi_monthly_rates, labels)
    cdi_total         = round(cdi_values[-1] - 100, 1) if cdi_values else 0

    closed_positions, open_positions = _track_performance(monthly)
    carteira_ref = active_monthly[-1]["data"][:7] if active_monthly else ""

    total_ret  = stats.get("retorno_total_pct", 0)
    ifix_total = stats.get("ifix_total_pct", 0)
    alpha      = stats.get("alpha_pct", 0)
    max_dd     = stats.get("max_drawdown_pct", 0)
    ret_medio  = stats.get("retorno_medio_mensal_pct") or 0
    vol        = stats.get("volatilidade_mensal_pct") or 0
    meses_pos  = stats.get("meses_positivos", 0)
    meses_neg  = stats.get("meses_negativos", 0)
    periodo    = stats.get("periodo", "")
    n_meses    = stats.get("meses", 0)
    top_n      = stats.get("top_n", 10)
    sharpe     = round(ret_medio / vol, 2) if vol else "—"

    def _sgn(v, d=1):
        return f"+{v:.{d}f}%" if v >= 0 else f"{v:.{d}f}%"

    def _pnl_color(v):
        if v is None: return "#8b949e"
        return "#38bdf8" if v >= 0 else "#ef4444"

    def _dy_color(v):
        if v is None: return ""
        return "#38bdf8" if v >= 10 else "#d29922" if v >= 6 else "#ef4444"

    def _pvp_color(v):
        if v is None: return ""
        return "#38bdf8" if v <= 0.70 else "#d29922" if v <= 0.90 else "#ef4444"

    # ── Carteira atual ────────────────────────────────────────────────────────
    carteira_rows = ""
    for rank, pos in enumerate(open_positions, 1):
        dy   = pos.get("dy_limpo")
        pvp  = pos.get("pvp")
        pnl  = pos.get("pnl_pct")
        ep   = pos.get("entry_price") or 0
        cp   = pos.get("current_price") or 0
        entry = pos.get("entry", "—")
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
        dy_str  = f"{dy:.1f}%" if dy is not None else "—"
        pvp_str = f"{pvp:.2f}" if pvp is not None else "—"
        carteira_rows += f"""
        <tr>
          <td class="text-center fw-bold" style="color:#38bdf8">{rank}</td>
          <td class="fw-semibold">{pos['ticker']}</td>
          <td class="text-center text-secondary" style="font-size:.78rem">{entry}</td>
          <td class="text-center">R$ {ep:.2f}</td>
          <td class="text-center">R$ {cp:.2f}</td>
          <td class="text-center fw-bold" style="color:{_pnl_color(pnl)};font-size:1rem">{pnl_str}</td>
          <td class="text-center" style="color:{_dy_color(dy)}">{dy_str}</td>
          <td class="text-center" style="color:{_pvp_color(pvp)}">{pvp_str}</td>
        </tr>"""

    # ── Posições fechadas ─────────────────────────────────────────────────────
    perf_rows = ""
    for p in closed_positions:
        pnl     = p.get("pnl_pct")
        ep      = p.get("entry_price") or 0
        xp      = p.get("exit_price") or 0
        icon    = "▲" if pnl and pnl >= 0 else "▼"
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
        perf_rows += f"""
        <tr>
          <td class="fw-semibold">{p['ticker']}</td>
          <td class="text-center text-secondary" style="font-size:.78rem">{p['entry']}</td>
          <td class="text-center text-secondary" style="font-size:.78rem">{p['exit']}</td>
          <td class="text-center">R$ {ep:.2f}</td>
          <td class="text-center">R$ {xp:.2f}</td>
          <td class="text-center fw-bold" style="color:{_pnl_color(pnl)}">{icon} {pnl_str}</td>
        </tr>"""

    # ── Histórico mensal ──────────────────────────────────────────────────────
    monthly_rows = ""
    for r in active_monthly:
        ret    = r.get("retorno_mes_pct")
        ifix_r = r.get("ifix_retorno_mes_pct")
        alp_m  = round(ret - ifix_r, 2) if ret is not None and ifix_r is not None else None
        entradas = ", ".join(r.get("entradas", [])) or "—"
        saidas   = ", ".join(r.get("saidas",   [])) or "—"
        top5     = ", ".join(r.get("top15",    [])[:5])
        suffix   = "…" if len(r.get("top15", [])) > 5 else ""

        def _fr(v):
            if v is None: return "—"
            return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"

        monthly_rows += f"""
        <tr>
          <td class="text-center fw-semibold">{r['data'][:7]}</td>
          <td class="text-center fw-bold" style="color:{_pnl_color(ret)}">{_fr(ret)}</td>
          <td class="text-center" style="color:{_pnl_color(ifix_r)}">{_fr(ifix_r)}</td>
          <td class="text-center" style="color:{_pnl_color(alp_m)}">{_fr(alp_m)}</td>
          <td class="text-center text-secondary">{r['portfolio_valor']:.1f}</td>
          <td style="color:#7dd3fc;font-size:.78rem">{entradas}</td>
          <td style="color:#fca5a5;font-size:.78rem">{saidas}</td>
          <td class="text-secondary" style="font-size:.75rem;max-width:180px">{top5}{suffix}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backtest FII — DY Limpo vs IFIX</title>
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
    background: linear-gradient(135deg, #0c1a2e 0%, #0e2a4a 50%, #0a3357 100%);
    padding: 2rem 0 1.5rem;
  }}
  .hero h1 {{ font-size: clamp(1.4rem, 4vw, 2rem); font-weight: 700; letter-spacing: -.5px; }}
  .hero h1 em {{ font-style: normal; color: #7dd3fc; }}

  .kpi-pill {{
    background: rgba(255,255,255,.08); border-radius: .75rem;
    padding: .6rem 1.1rem; text-align: center; min-width: 110px;
  }}
  .kpi-pill .val {{ font-size: 1.4rem; font-weight: 700; color: #fff; line-height: 1.2; }}
  .kpi-pill .lbl {{ font-size: .67rem; color: #bae6fd; }}

  .section-title {{
    font-size: .85rem; font-weight: 600; color: #38bdf8;
    border-left: 3px solid #0369a1; padding-left: .6rem; margin-bottom: 1rem;
    text-transform: uppercase; letter-spacing: .5px;
  }}
  .chart-card {{ background: #161b22; border: 1px solid #30363d; border-radius: .75rem; padding: 1.25rem; }}
  .chart-card h3 {{ font-size: .82rem; color: #8b949e; margin-bottom: 1rem; }}

  .kpi-box {{
    background: #161b22; border: 1px solid #30363d; border-radius: .75rem;
    padding: 1.1rem; text-align: center;
  }}
  .kpi-box .kval {{ font-size: 1.6rem; font-weight: 700; }}
  .kpi-box .klbl {{ font-size: .72rem; color: #6e7681; margin-top: .25rem; }}

  .warn-box {{
    background: rgba(245,158,11,.08); border: 1px solid #d2992244;
    border-radius: .5rem; padding: .7rem 1rem; font-size: .8rem; color: #fcd34d;
  }}

  .table-dark {{ --bs-table-bg: #161b22; --bs-table-hover-bg: #1f2937; --bs-table-border-color: #30363d; }}
  .table th {{ font-size: .72rem; white-space: nowrap; color: #38bdf8; }}
  .table td {{ vertical-align: middle; }}
  thead tr {{ background: #0c1a2e !important; }}

  footer {{ font-size: .75rem; color: #6e7681; padding: 1.5rem; text-align: center; border-top: 1px solid #30363d; }}

  @media (max-width: 576px) {{
    .hero {{ padding: 1.25rem 0 1rem; }}
    .kpi-pill .val {{ font-size: 1.1rem; }}
    .table {{ font-size: .72rem; }}
    .kpi-box .kval {{ font-size: 1.2rem; }}
  }}
</style>
</head>
<body>

{get_navbar("backtest_fii")}
<script>
document.querySelectorAll('nav a').forEach(a => {{
  if (location.pathname.endsWith(a.getAttribute('href'))) {{
    a.style.color = '#e6edf3'; a.style.fontWeight = '700';
  }}
}});
</script>

<!-- ── Hero ──────────────────────────────────────────────────────────────── -->
<div class="hero">
  <div class="container-fluid px-3 px-md-4">
    <h1>Backtest <em>FII</em> — DY Limpo vs IFIX</h1>
    <p class="mb-3" style="color:#bae6fd;font-size:.85rem">
      TOP {top_n} por DY Limpo · Período: {periodo} · {n_meses} meses · Gerado em {now}
    </p>

    <div class="warn-box mb-3">
      ⚠ <strong>Survivorship bias:</strong> universo fixo no cache atual.
      FIIs liquidados ou incorporados não estão incluídos — retorno real pode ser menor.
      P/VP histórico não disponível — filtro P/VP aplicado apenas no screener atual.
    </div>

    <div class="d-flex flex-wrap gap-2">
      <div class="kpi-pill">
        <div class="val" style="color:{'#38bdf8' if total_ret >= 0 else '#ef4444'}">{_sgn(total_ret)}</div>
        <div class="lbl">FII DY Limpo</div>
      </div>
      <div class="kpi-pill">
        <div class="val">{_sgn(ifix_total)}</div>
        <div class="lbl">IFIX</div>
      </div>
      <div class="kpi-pill">
        <div class="val">{_sgn(cdi_total)}</div>
        <div class="lbl">CDI</div>
      </div>
      <div class="kpi-pill">
        <div class="val" style="color:{'#38bdf8' if alpha >= 0 else '#ef4444'}">{_sgn(alpha)}</div>
        <div class="lbl">Alpha vs IFIX</div>
      </div>
      <div class="kpi-pill">
        <div class="val" style="color:{'#38bdf8' if total_ret >= cdi_total else '#ef4444'}">{_sgn(total_ret - cdi_total)}</div>
        <div class="lbl">Alpha vs CDI</div>
      </div>
      <div class="kpi-pill">
        <div class="val" style="color:#ef4444">{max_dd:.1f}%</div>
        <div class="lbl">Max Drawdown</div>
      </div>
      <div class="kpi-pill">
        <div class="val">{meses_pos}W/{meses_neg}L</div>
        <div class="lbl">Positivo/Negativo</div>
      </div>
    </div>
  </div>
</div>

<div class="container-fluid px-3 px-md-4 py-4">

  <!-- ── Curva de Capital ────────────────────────────────────────────────── -->
  <section class="mb-5">
    <div class="section-title">Curva de Capital</div>
    <div class="row g-3">
      <div class="col-12">
        <div class="chart-card">
          <h3>FII DY Limpo vs IFIX vs CDI (base 100)</h3>
          <canvas id="chartEquity" style="max-height:320px"></canvas>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="chart-card">
          <h3>Retorno Mensal FII DY Limpo (%)</h3>
          <canvas id="chartMonthly" style="max-height:260px"></canvas>
        </div>
      </div>
      {'<div class="col-12"><div class="chart-card"><h3>DY Médio Trailing 12M — Estratégia vs IFIX (XFIX11)</h3><canvas id="chartDY" style="max-height:220px"></canvas></div></div>' if has_dy_chart else ''}
      <div class="col-12 col-lg-6">
        <div class="section-title mt-2">KPIs</div>
        <div class="row g-2">
          <div class="col-6 col-sm-4">
            <div class="kpi-box">
              <div class="kval" style="color:{'#38bdf8' if total_ret >= 0 else '#ef4444'}">{_sgn(total_ret)}</div>
              <div class="klbl">Retorno Total</div>
            </div>
          </div>
          <div class="col-6 col-sm-4">
            <div class="kpi-box">
              <div class="kval">{_sgn(ret_medio, 2)}</div>
              <div class="klbl">Média Mensal</div>
            </div>
          </div>
          <div class="col-6 col-sm-4">
            <div class="kpi-box">
              <div class="kval">{vol:.2f}%</div>
              <div class="klbl">Volatilidade/Mês</div>
            </div>
          </div>
          <div class="col-6 col-sm-4">
            <div class="kpi-box">
              <div class="kval" style="color:#ef4444">{max_dd:.1f}%</div>
              <div class="klbl">Max Drawdown</div>
            </div>
          </div>
          <div class="col-6 col-sm-4">
            <div class="kpi-box">
              <div class="kval" style="color:{'#38bdf8' if alpha >= 0 else '#ef4444'}">{_sgn(alpha)}</div>
              <div class="klbl">Alpha IFIX</div>
            </div>
          </div>
          <div class="col-6 col-sm-4">
            <div class="kpi-box">
              <div class="kval">{sharpe}</div>
              <div class="klbl">Sharpe Simples</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ── Carteira atual ──────────────────────────────────────────────────── -->
  <section class="mb-5">
    <div class="section-title">Carteira Atual — {carteira_ref} (posições abertas)</div>
    <p class="text-secondary mb-3" style="font-size:.82rem">
      P&amp;L calculado desde a data de entrada. DY Limpo calculado com preço histórico de entrada.
    </p>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead>
          <tr>
            <th>#</th><th>Ticker</th><th>Entrada</th>
            <th>Preço Entrada</th><th>Preço Atual</th>
            <th>P&amp;L %</th><th>DY Limpo 12M</th><th>P/VP atual</th>
          </tr>
        </thead>
        <tbody>{carteira_rows}</tbody>
      </table>
    </div>
  </section>

  <!-- ── Posições Fechadas ───────────────────────────────────────────────── -->
  <section class="mb-5">
    <div class="section-title">Performance Realizadas (posições fechadas)</div>
    <p class="text-secondary mb-3" style="font-size:.82rem">
      P&amp;L por ticker desde entrada até saída. Ordenado por retorno.
    </p>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d;max-width:860px">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead>
          <tr>
            <th>Ticker</th><th>Entrada</th><th>Saída</th>
            <th>Preço Entrada</th><th>Preço Saída</th><th>P&amp;L %</th>
          </tr>
        </thead>
        <tbody>{perf_rows}</tbody>
      </table>
    </div>
  </section>

  <!-- ── Histórico Mensal ────────────────────────────────────────────────── -->
  <section class="mb-4">
    <div class="section-title">Histórico Mensal</div>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead>
          <tr>
            <th>Mês</th><th>Retorno FII</th><th>IFIX</th><th>Alpha</th>
            <th>Portfólio</th><th>Entradas</th><th>Saídas</th><th>Top 5 Posições</th>
          </tr>
        </thead>
        <tbody>{monthly_rows}</tbody>
      </table>
    </div>
  </section>

</div>

<footer>Backtest FII DY Limpo · {now} · Não é recomendação de investimento · Survivorship bias presente</footer>

<script>
const labels = {json.dumps(labels)};
const fiiValues = {json.dumps(fii_values)};
const ifixValues = {json.dumps(ifix_values)};
const cdiValues = {json.dumps(cdi_values)};
const monthlyRets = {json.dumps(monthly_rets)};
const barColors = {json.dumps(bar_colors)};

new Chart(document.getElementById('chartEquity'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{
        label: 'FII DY Limpo',
        data: fiiValues,
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56,189,248,.06)',
        borderWidth: 2.5, pointRadius: 2, fill: true, tension: 0.3,
      }},
      {{
        label: 'IFIX',
        data: ifixValues,
        borderColor: '#6e7681',
        borderWidth: 1.5, pointRadius: 0, borderDash: [4,3], tension: 0.3,
      }},
      {{
        label: 'CDI',
        data: cdiValues,
        borderColor: '#d29922',
        borderWidth: 1.5, pointRadius: 0, borderDash: [2,4], tension: 0.1,
      }},
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y.toFixed(1)}}` }} }},
    }},
    scales: {{
      x: {{ ticks: {{ color: '#6e7681', maxTicksLimit: 18, font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }},
      y: {{ ticks: {{ color: '#8b949e', callback: v => v.toFixed(0) }}, grid: {{ color: '#30363d' }} }},
    }}
  }}
}});

new Chart(document.getElementById('chartMonthly'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [{{
      label: 'Retorno Mensal (%)',
      data: monthlyRets,
      backgroundColor: barColors,
      borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y.toFixed(2)}}%` }} }},
    }},
    scales: {{
      x: {{ ticks: {{ color: '#6e7681', maxTicksLimit: 18, font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }},
      y: {{ ticks: {{ color: '#8b949e', callback: v => v.toFixed(1) + '%' }}, grid: {{ color: '#30363d' }} }},
    }}
  }}
}});

const dyMedioVals = {json.dumps(dy_medio_vals)};
const ifixDyVals  = {json.dumps(ifix_dy_vals)};
if (document.getElementById('chartDY')) {{
  new Chart(document.getElementById('chartDY'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [
        {{
          label: 'DY Médio Estratégia',
          data: dyMedioVals,
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,.08)',
          borderWidth: 2, pointRadius: 2, fill: true, tension: 0.3,
          spanGaps: true,
        }},
        {{
          label: 'DY IFIX (XFIX11)',
          data: ifixDyVals,
          borderColor: '#6e7681',
          borderWidth: 1.5, pointRadius: 0, borderDash: [4,3], tension: 0.3,
          spanGaps: true,
        }},
      ]
    }},
    options: {{
      responsive: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }},
        tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y != null ? ctx.parsed.y.toFixed(1) + '%' : 'N/A'}}` }} }},
      }},
      scales: {{
        x: {{ ticks: {{ color: '#6e7681', maxTicksLimit: 18, font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }},
        y: {{ ticks: {{ color: '#8b949e', callback: v => v.toFixed(0) + '%' }}, grid: {{ color: '#30363d' }} }},
      }}
    }}
  }});
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[report_backtest_fii] HTML gerado: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json",   required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    out = args.output or str(Path(args.json).parent / "backtest_fii.html")
    generate_backtest_fii_html(data, out)
