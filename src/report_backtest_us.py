"""
Gera relatorio HTML do backtest Magic Formula US.
Lê benchmark_acumulado / benchmark_* do JSON (gerado por backtester_us.py).
"""

import argparse
import json
from pathlib import Path
from datetime import datetime


def _track_performance(monthly: list) -> tuple:
    entry_tracker = {}
    closed = []

    for r in monthly:
        det_map = {det["ticker"]: det for det in r.get("detalhes", [])}
        precos_saida = r.get("precos_saida", {})
        date = r["data"][:7]

        for t in r.get("entradas", []):
            if t in det_map and det_map[t].get("preco"):
                entry_tracker[t] = {"price": det_map[t]["preco"], "date": date}

        for t in r.get("saidas", []):
            if t in entry_tracker:
                ep = entry_tracker[t]["price"]
                xp = precos_saida.get(t)
                pnl = round((xp / ep - 1) * 100, 1) if ep and xp else None
                closed.append({
                    "ticker": t, "entry": entry_tracker[t]["date"], "exit": date,
                    "entry_price": ep, "exit_price": xp, "pnl_pct": pnl,
                })
                del entry_tracker[t]

    last_month = next((r for r in reversed(monthly) if r.get("top15")), None)
    open_pos = []
    if last_month:
        det_map = {det["ticker"]: det for det in last_month.get("detalhes", [])}
        for t, entry in entry_tracker.items():
            ep = entry["price"]
            det = det_map.get(t, {})
            cp = det.get("preco")
            pnl = round((cp / ep - 1) * 100, 1) if ep and cp else None
            open_pos.append({
                "ticker": t, "entry": entry["date"], "entry_price": ep,
                "current_price": cp, "pnl_pct": pnl,
                "ev_ebit": det.get("ev_ebit"), "roic": det.get("roic"),
                "mf_score": det.get("mf_score"),
            })
        open_pos.sort(key=lambda x: x.get("mf_score") or 9999)

    closed.sort(key=lambda x: x["pnl_pct"] if x["pnl_pct"] is not None else -999, reverse=True)
    return closed, open_pos


def generate_backtest_html(data: dict, output_path: str,
                           title: str = "Magic Formula US",
                           accent: str = "#3b82f6",
                           hero_gradient: str = "135deg, #0c1a2e 0%, #1e3a5f 50%, #1a4a7a 100%"):
    stats = data.get("stats", {})
    monthly = data.get("monthly", [])
    bm_acc = data.get("benchmark_acumulado", [])
    tbill_acc = data.get("tbill_acumulado", [])
    bm_name = stats.get("benchmark_name", "Benchmark")

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    active_indices = [i for i, r in enumerate(monthly) if r.get("top15")]
    if active_indices:
        active_monthly = [monthly[i] for i in active_indices]
        active_bm    = [bm_acc[i]    if i < len(bm_acc)    else bm_acc[-1]    for i in active_indices]
        active_tbill = [tbill_acc[i] if i < len(tbill_acc) else tbill_acc[-1] for i in active_indices]
        mf_start   = active_monthly[0]["portfolio_valor"]
        bm_start   = active_bm[0]
        tb_start   = active_tbill[0]
        mf_values  = [round(r["portfolio_valor"] / mf_start * 100, 2) for r in active_monthly]
        bm_values  = [round(v / bm_start * 100, 2) for v in active_bm]
        tb_values  = [round(v / tb_start * 100, 2) for v in active_tbill]
    else:
        active_monthly = monthly
        mf_values  = [r["portfolio_valor"] for r in monthly]
        bm_values  = bm_acc[:len(monthly)]
        tb_values  = tbill_acc[:len(monthly)]

    labels = [r["data"][:7] for r in active_monthly]
    monthly_rets = [r["retorno_mes_pct"] if r["retorno_mes_pct"] is not None else 0 for r in active_monthly]
    bar_colors = ["rgba(16,185,129,.85)" if v >= 0 else "rgba(239,68,68,.85)" for v in monthly_rets]

    closed_positions, open_positions = _track_performance(monthly)
    carteira_data_ref = active_monthly[-1]["data"][:7] if active_monthly else ""

    total_ret  = stats.get("retorno_total_pct", 0)
    bm_total   = stats.get("benchmark_total_pct", 0)
    tbill_total = stats.get("tbill_total_pct", 0)
    alpha      = stats.get("alpha_pct", 0)
    max_dd     = stats.get("max_drawdown_pct", 0)
    ret_medio  = stats.get("retorno_medio_mensal_pct", 0)
    vol        = stats.get("volatilidade_mensal_pct", 0)
    meses_pos  = stats.get("meses_positivos", 0)
    meses_neg  = stats.get("meses_negativos", 0)
    periodo    = stats.get("periodo", "")
    n_meses    = stats.get("meses", 0)
    sharpe     = round(ret_medio / vol, 2) if vol else "—"

    def _sgn(v, d=1): return f"+{v:.{d}f}%" if v >= 0 else f"{v:.{d}f}%"
    def _pnl_color(v): return "#8b949e" if v is None else ("#10b981" if v >= 0 else "#ef4444")
    def _ev_color(v):  return "" if v is None else ("#10b981" if v <= 5 else "#d29922" if v <= 10 else "#ef4444")
    def _roic_color(v): return "" if v is None else ("#10b981" if v >= 25 else "#d29922" if v >= 15 else "#ef4444")

    carteira_rows = ""
    for rank, pos in enumerate(open_positions, 1):
        ev   = pos.get("ev_ebit") or 0
        roic = pos.get("roic") or 0
        pnl  = pos.get("pnl_pct")
        ep   = pos.get("entry_price") or 0
        cp   = pos.get("current_price") or 0
        entry = pos.get("entry", "—")
        mf   = pos.get("mf_score") or 0
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
        carteira_rows += f"""
        <tr>
          <td class="text-center fw-bold" style="color:#10b981">{rank}</td>
          <td class="fw-semibold">{pos['ticker']}</td>
          <td class="text-center text-secondary" style="font-size:.78rem">{entry}</td>
          <td class="text-center">$ {ep:.2f}</td>
          <td class="text-center">$ {cp:.2f}</td>
          <td class="text-center fw-bold" style="color:{_pnl_color(pnl)};font-size:1rem">{pnl_str}</td>
          <td class="text-center" style="color:{_ev_color(ev)}">{ev:.2f}x</td>
          <td class="text-center" style="color:{_roic_color(roic)}">{roic:.1f}%</td>
          <td class="text-center text-secondary">{mf:.0f}</td>
        </tr>"""

    perf_rows = ""
    for p in closed_positions:
        pnl = p.get("pnl_pct")
        ep  = p.get("entry_price") or 0
        xp  = p.get("exit_price") or 0
        icon = "▲" if pnl and pnl >= 0 else "▼"
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
        perf_rows += f"""
        <tr>
          <td class="fw-semibold">{p['ticker']}</td>
          <td class="text-center text-secondary" style="font-size:.78rem">{p['entry']}</td>
          <td class="text-center text-secondary" style="font-size:.78rem">{p['exit']}</td>
          <td class="text-center">$ {ep:.2f}</td>
          <td class="text-center">$ {xp:.2f}</td>
          <td class="text-center fw-bold" style="color:{_pnl_color(pnl)}">{icon} {pnl_str}</td>
        </tr>"""

    monthly_rows = ""
    for r in active_monthly:
        ret  = r.get("retorno_mes_pct")
        bm_r = r.get("benchmark_retorno_mes_pct")
        alpha_m = round(ret - bm_r, 2) if ret is not None and bm_r is not None else None
        entradas = ", ".join(r.get("entradas", [])) or "—"
        saidas   = ", ".join(r.get("saidas", [])) or "—"
        top5 = ", ".join(r.get("top15", [])[:5])
        suffix = "…" if len(r.get("top15", [])) > 5 else ""

        def _fmt_ret(v):
            if v is None: return "—"
            return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"

        monthly_rows += f"""
        <tr>
          <td class="text-center fw-semibold">{r['data'][:7]}</td>
          <td class="text-center fw-bold" style="color:{_pnl_color(ret)}">{_fmt_ret(ret)}</td>
          <td class="text-center" style="color:{_pnl_color(bm_r)}">{_fmt_ret(bm_r)}</td>
          <td class="text-center" style="color:{_pnl_color(alpha_m)}">{_fmt_ret(alpha_m)}</td>
          <td class="text-center text-secondary">{r['portfolio_valor']:.1f}</td>
          <td style="color:#86efac;font-size:.78rem">{entradas}</td>
          <td style="color:#fca5a5;font-size:.78rem">{saidas}</td>
          <td class="text-secondary" style="font-size:.75rem;max-width:180px">{top5}{suffix}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backtest {title}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  [data-bs-theme=dark] {{
    --bs-body-bg: #0d1117; --bs-body-color: #e6edf3;
    --bs-card-bg: #161b22; --bs-border-color: #30363d;
  }}
  body {{ font-family: -apple-system, 'Segoe UI', system-ui, sans-serif; }}
  .hero {{ background: linear-gradient({hero_gradient}); padding: 2rem 0 1.5rem; }}
  .hero h1 {{ font-size: clamp(1.4rem, 4vw, 2rem); font-weight: 700; letter-spacing: -.5px; }}
  .hero h1 em {{ font-style: normal; color: {accent}; }}
  .kpi-pill {{ background: rgba(255,255,255,.08); border-radius: .75rem; padding: .6rem 1.1rem; text-align: center; min-width: 110px; }}
  .kpi-pill .val {{ font-size: 1.4rem; font-weight: 700; color: #fff; line-height: 1.2; }}
  .kpi-pill .lbl {{ font-size: .67rem; color: #bfdbfe; }}
  .section-title {{ font-size: .85rem; font-weight: 600; color: {accent}; border-left: 3px solid {accent}44; padding-left: .6rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: .5px; }}
  .chart-card {{ background: #161b22; border: 1px solid #30363d; border-radius: .75rem; padding: 1.25rem; }}
  .chart-card h3 {{ font-size: .82rem; color: #8b949e; margin-bottom: 1rem; }}
  .kpi-box {{ background: #161b22; border: 1px solid #30363d; border-radius: .75rem; padding: 1.1rem; text-align: center; }}
  .kpi-box .kval {{ font-size: 1.6rem; font-weight: 700; }}
  .kpi-box .klbl {{ font-size: .72rem; color: #6e7681; margin-top: .25rem; }}
  .warn-box {{ background: rgba(245,158,11,.08); border: 1px solid #d2992244; border-radius: .5rem; padding: .7rem 1rem; font-size: .8rem; color: #fcd34d; }}
  .table-dark {{ --bs-table-bg: #161b22; --bs-table-hover-bg: #1f2937; --bs-table-border-color: #30363d; }}
  .table th {{ font-size: .72rem; white-space: nowrap; color: {accent}; }}
  .table td {{ vertical-align: middle; }}
  thead tr {{ background: #0c1a2e !important; }}
  footer {{ font-size: .75rem; color: #6e7681; padding: 1.5rem; text-align: center; border-top: 1px solid #30363d; }}
  @media (max-width: 576px) {{ .hero {{ padding: 1.25rem 0 1rem; }} .kpi-pill .val {{ font-size: 1.1rem; }} .table {{ font-size: .72rem; }} .kpi-box .kval {{ font-size: 1.2rem; }} }}
</style>
</head>
<body>

<nav class="navbar navbar-dark py-2" style="background:#0d1117;border-bottom:1px solid #30363d;position:sticky;top:0;z-index:1030">
  <div class="container-fluid px-3 px-md-4 d-flex align-items-center gap-3">
    <span class="fw-bold me-2" style="color:#58a6ff">&#9998; Magic Formula</span>
    <a href="index.html"         class="nav-link px-2" style="font-size:.85rem">&#127463;&#127479; BR</a>
    <a href="us.html"            class="nav-link px-2" style="font-size:.85rem">&#127482;&#127480; US</a>
    <a href="smallcap.html"      class="nav-link px-2" style="font-size:.85rem">&#128202; Small Cap</a>
    <a href="backtest.html"      class="nav-link px-2" style="font-size:.85rem">&#128200; Backtest BR</a>
    <a href="backtest_us.html"   class="nav-link px-2" style="font-size:.85rem">&#128201; Backtest US</a>
    <a href="backtest_sc.html"   class="nav-link px-2" style="font-size:.85rem">&#127381; Backtest SC</a>
  </div>
</nav>
<script>
document.querySelectorAll('nav a').forEach(a => {{
  if (location.pathname.endsWith(a.getAttribute('href'))) {{
    a.style.color = '#e6edf3'; a.style.fontWeight = '700';
  }}
}});
</script>

<div class="hero">
  <div class="container-fluid px-3 px-md-4">
    <h1>Backtest <em>{title}</em> &#127482;&#127480;</h1>
    <p class="mb-3" style="color:#bfdbfe;font-size:.85rem">Period: {periodo} · {n_meses} months · Generated {now}</p>
    <div class="warn-box mb-3">
      ⚠ <strong>Survivorship bias:</strong> fixed universe from current index.
      Companies delisted before today are not included — real returns would be lower.
    </div>
    <div class="d-flex flex-wrap gap-2">
      <div class="kpi-pill"><div class="val" style="color:{'#10b981' if total_ret >= 0 else '#ef4444'}">{_sgn(total_ret)}</div><div class="lbl">Magic Formula</div></div>
      <div class="kpi-pill"><div class="val">{_sgn(bm_total)}</div><div class="lbl">{bm_name}</div></div>
      <div class="kpi-pill"><div class="val">{_sgn(tbill_total)}</div><div class="lbl">T-Bill</div></div>
      <div class="kpi-pill"><div class="val" style="color:{'#10b981' if alpha >= 0 else '#ef4444'}">{_sgn(alpha)}</div><div class="lbl">Alpha vs {bm_name}</div></div>
      <div class="kpi-pill"><div class="val" style="color:{'#10b981' if total_ret >= tbill_total else '#ef4444'}">{_sgn(total_ret - tbill_total)}</div><div class="lbl">Alpha vs T-Bill</div></div>
      <div class="kpi-pill"><div class="val" style="color:#ef4444">{max_dd:.1f}%</div><div class="lbl">Max Drawdown</div></div>
      <div class="kpi-pill"><div class="val">{meses_pos}W/{meses_neg}L</div><div class="lbl">Win/Loss Months</div></div>
    </div>
  </div>
</div>

<div class="container-fluid px-3 px-md-4 py-4">

  <section class="mb-5">
    <div class="section-title">Equity Curve</div>
    <div class="row g-3">
      <div class="col-12">
        <div class="chart-card">
          <h3>Magic Formula vs {bm_name} vs T-Bill (base 100)</h3>
          <canvas id="chartEquity" style="max-height:320px"></canvas>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="chart-card">
          <h3>Monthly Return Magic Formula (%)</h3>
          <canvas id="chartMonthly" style="max-height:260px"></canvas>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="section-title mt-2">KPIs</div>
        <div class="row g-2">
          <div class="col-6 col-sm-4"><div class="kpi-box"><div class="kval" style="color:{'#10b981' if total_ret >= 0 else '#ef4444'}">{_sgn(total_ret)}</div><div class="klbl">Total Return</div></div></div>
          <div class="col-6 col-sm-4"><div class="kpi-box"><div class="kval">{_sgn(ret_medio, 2)}</div><div class="klbl">Avg Monthly</div></div></div>
          <div class="col-6 col-sm-4"><div class="kpi-box"><div class="kval">{vol:.2f}%</div><div class="klbl">Vol/Month</div></div></div>
          <div class="col-6 col-sm-4"><div class="kpi-box"><div class="kval" style="color:#ef4444">{max_dd:.1f}%</div><div class="klbl">Max Drawdown</div></div></div>
          <div class="col-6 col-sm-4"><div class="kpi-box"><div class="kval" style="color:{'#10b981' if alpha >= 0 else '#ef4444'}">{_sgn(alpha)}</div><div class="klbl">Alpha {bm_name}</div></div></div>
          <div class="col-6 col-sm-4"><div class="kpi-box"><div class="kval">{sharpe}</div><div class="klbl">Simple Sharpe</div></div></div>
        </div>
      </div>
    </div>
  </section>

  <section class="mb-5">
    <div class="section-title">Current Portfolio — {carteira_data_ref} (open positions)</div>
    <p class="text-secondary mb-3" style="font-size:.82rem">P&amp;L from entry date. Reference prices at monthly close.</p>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead><tr><th>#</th><th>Ticker</th><th>Entry</th><th>Entry $</th><th>Current $</th><th>P&amp;L %</th><th>EV/EBIT</th><th>ROIC</th><th>MF Score</th></tr></thead>
        <tbody>{carteira_rows}</tbody>
      </table>
    </div>
  </section>

  <section class="mb-5">
    <div class="section-title">Realized Performance (closed positions)</div>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d;max-width:860px">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead><tr><th>Ticker</th><th>Entry</th><th>Exit</th><th>Entry $</th><th>Exit $</th><th>P&amp;L %</th></tr></thead>
        <tbody>{perf_rows}</tbody>
      </table>
    </div>
  </section>

  <section class="mb-4">
    <div class="section-title">Monthly History</div>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead><tr><th>Month</th><th>MF Return</th><th>{bm_name}</th><th>Alpha</th><th>Portfolio</th><th>Entries</th><th>Exits</th><th>Top 5</th></tr></thead>
        <tbody>{monthly_rows}</tbody>
      </table>
    </div>
  </section>

</div>

<footer>Backtest {title} · {now} · Not investment advice · Survivorship bias present</footer>

<script>
const labels = {json.dumps(labels)};
const mfValues = {json.dumps(mf_values)};
const bmValues = {json.dumps(bm_values)};
const tbillValues = {json.dumps(tb_values)};
const monthlyRets = {json.dumps(monthly_rets)};
const barColors = {json.dumps(bar_colors)};

new Chart(document.getElementById('chartEquity'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{ label: 'Magic Formula', data: mfValues, borderColor: '{accent}', backgroundColor: '{accent}10', borderWidth: 2.5, pointRadius: 2, fill: true, tension: 0.3 }},
      {{ label: '{bm_name}', data: bmValues, borderColor: '#6e7681', borderWidth: 1.5, pointRadius: 0, borderDash: [4,3], tension: 0.3 }},
      {{ label: 'T-Bill', data: tbillValues, borderColor: '#d29922', borderWidth: 1.5, pointRadius: 0, borderDash: [2,4], tension: 0.1 }},
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }}, tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y.toFixed(1)}}` }} }} }},
    scales: {{ x: {{ ticks: {{ color: '#6e7681', maxTicksLimit: 18, font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }}, y: {{ ticks: {{ color: '#8b949e', callback: v => v.toFixed(0) }}, grid: {{ color: '#30363d' }} }} }}
  }}
}});

new Chart(document.getElementById('chartMonthly'), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ label: 'Monthly Return (%)', data: monthlyRets, backgroundColor: barColors, borderRadius: 4 }}] }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y.toFixed(2)}}%` }} }} }},
    scales: {{ x: {{ ticks: {{ color: '#6e7681', maxTicksLimit: 18, font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }}, y: {{ ticks: {{ color: '#8b949e', callback: v => v.toFixed(1) + '%' }}, grid: {{ color: '#30363d' }} }} }}
  }}
}});
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[report_backtest_us] HTML gerado: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--title", default=None, help="Título da página (detectado automaticamente do JSON se omitido)")
    args = parser.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    # Detecta título automaticamente se não passado
    title = args.title or "Magic Formula US"
    accent = "#3b82f6"
    gradient = "135deg, #0c1a2e 0%, #1e3a5f 50%, #1a4a7a 100%"

    out = args.output or str(Path(args.json).parent / "relatorio_backtest_us.html")
    generate_backtest_html(data, out, title=title, accent=accent, hero_gradient=gradient)
