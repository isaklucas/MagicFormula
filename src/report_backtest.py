"""
Gera relatorio HTML do backtest Magic Formula BR.
"""

import argparse
import json
import urllib.request
from pathlib import Path
from datetime import datetime


def _fetch_cdi_monthly(start_ym: str, end_ym: str) -> dict:
    """
    Busca CDI mensal acumulado do BCB (serie 4390).
    Retorna dict {"YYYY-MM": taxa_pct, ...}.
    start_ym e end_ym no formato "YYYY-MM".
    """
    try:
        s = start_ym.replace("-", "")
        e = end_ym.replace("-", "")
        d_ini = f"01/{s[4:6]}/{s[:4]}"
        d_fim = f"01/{e[4:6]}/{e[:4]}"
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json&dataInicial={d_ini}&dataFinal={d_fim}"
        with urllib.request.urlopen(url, timeout=8) as r:
            rows = json.loads(r.read())
        result = {}
        for row in rows:
            # data no formato "01/MM/YYYY"
            parts = row["data"].split("/")
            ym = f"{parts[2]}-{parts[1]}"
            result[ym] = float(row["valor"])
        return result
    except Exception:
        return {}


def _build_cdi_series(cdi_monthly: dict, labels: list) -> list:
    """Acumula CDI para cada label (YYYY-MM), base 100."""
    acc = 100.0
    series = []
    for lbl in labels:
        rate = cdi_monthly.get(lbl)
        if rate is not None:
            acc *= (1 + rate / 100)
        series.append(round(acc, 2))
    return series


def _track_performance(monthly: list) -> tuple:
    """
    Rastreia P&L por ticker.
    Retorna (closed_positions, open_positions) ordenados.
    """
    entry_tracker = {}  # ticker -> {"price": float, "date": str}
    closed = []

    for r in monthly:
        det_map = {det["ticker"]: det for det in r.get("detalhes", [])}
        precos_saida = r.get("precos_saida", {})
        date = r["data"][:7]

        # Registrar entradas
        for t in r.get("entradas", []):
            if t in det_map and det_map[t].get("preco"):
                entry_tracker[t] = {"price": det_map[t]["preco"], "date": date}

        # Registrar saidas
        for t in r.get("saidas", []):
            if t in entry_tracker:
                ep = entry_tracker[t]["price"]
                xp = precos_saida.get(t)
                pnl = round((xp / ep - 1) * 100, 1) if ep and xp else None
                closed.append({
                    "ticker": t,
                    "entry": entry_tracker[t]["date"],
                    "exit": date,
                    "entry_price": ep,
                    "exit_price": xp,
                    "pnl_pct": pnl,
                })
                del entry_tracker[t]

    # Posicoes abertas: usar ultimo mes com portfolio
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
                "ticker": t,
                "entry": entry["date"],
                "entry_price": ep,
                "current_price": cp,
                "pnl_pct": pnl,
                "ev_ebit": det.get("ev_ebit"),
                "roic": det.get("roic"),
                "mf_score": det.get("mf_score"),
            })
        open_pos.sort(key=lambda x: x.get("mf_score") or 9999)

    closed.sort(key=lambda x: x["pnl_pct"] if x["pnl_pct"] is not None else -999, reverse=True)
    return closed, open_pos


def generate_backtest_html(data: dict, output_path: str):
    stats = data.get("stats", {})
    monthly = data.get("monthly", [])
    ibov_acc = data.get("ibov_acumulado", [])

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Filtrar apenas meses com portfolio ativo
    active_indices = [i for i, r in enumerate(monthly) if r.get("top15")]
    if active_indices:
        active_monthly = [monthly[i] for i in active_indices]
        active_ibov = [ibov_acc[i] if i < len(ibov_acc) else ibov_acc[-1] for i in active_indices]
        mf_start = active_monthly[0]["portfolio_valor"]
        ibov_start = active_ibov[0]
        mf_values = [round(r["portfolio_valor"] / mf_start * 100, 2) for r in active_monthly]
        ibov_values = [round(v / ibov_start * 100, 2) for v in active_ibov]
    else:
        active_monthly = monthly
        mf_values = [r["portfolio_valor"] for r in monthly]
        ibov_values = ibov_acc[:len(monthly)]

    labels = [r["data"][:7] for r in active_monthly]
    monthly_rets = [r["retorno_mes_pct"] if r["retorno_mes_pct"] is not None else 0 for r in active_monthly]
    bar_colors = ["#16a34a" if v >= 0 else "#dc2626" for v in monthly_rets]

    # CDI
    cdi_monthly_rates = _fetch_cdi_monthly(labels[0], labels[-1]) if labels else {}
    cdi_values = _build_cdi_series(cdi_monthly_rates, labels)
    cdi_total = round(cdi_values[-1] - 100, 1) if cdi_values else 0

    # Performance por ticker
    closed_positions, open_positions = _track_performance(monthly)

    # Carteira atual com P&L
    carteira_data_ref = active_monthly[-1]["data"][:7] if active_monthly else ""
    carteira_html = ""
    for rank, pos in enumerate(open_positions, 1):
        ev = pos.get("ev_ebit") or 0
        roic = pos.get("roic") or 0
        pnl = pos.get("pnl_pct")
        ep = pos.get("entry_price") or 0
        cp = pos.get("current_price") or 0
        entry = pos.get("entry", "—")
        mf = pos.get("mf_score") or 0
        roic_color = "#16a34a" if roic >= 25 else "#ca8a04" if roic >= 15 else "#dc2626"
        ev_color = "#16a34a" if ev <= 5 else "#ca8a04" if ev <= 10 else "#dc2626"
        pnl_color = "#16a34a" if pnl and pnl >= 0 else "#dc2626"
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
        carteira_html += f"""
        <tr>
          <td class="center" style="font-weight:700;color:#6ee7b7">{rank}</td>
          <td style="font-weight:600">{pos['ticker']}</td>
          <td class="center" style="color:#64748b;font-size:0.78rem">{entry}</td>
          <td class="center">R$ {ep:.2f}</td>
          <td class="center">R$ {cp:.2f}</td>
          <td class="center" style="color:{pnl_color};font-weight:700;font-size:1rem">{pnl_str}</td>
          <td class="center" style="color:{ev_color}">{ev:.2f}x</td>
          <td class="center" style="color:{roic_color}">{roic:.1f}%</td>
          <td class="center;color:#94a3b8">{mf:.0f}</td>
        </tr>"""

    # Performance realizadas
    perf_html = ""
    for p in closed_positions:
        pnl = p.get("pnl_pct")
        ep = p.get("entry_price") or 0
        xp = p.get("exit_price") or 0
        pnl_color = "#16a34a" if pnl and pnl >= 0 else "#dc2626"
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
        icon = "▲" if pnl and pnl >= 0 else "▼"
        perf_html += f"""
        <tr>
          <td style="font-weight:600">{p['ticker']}</td>
          <td class="center" style="color:#64748b;font-size:0.78rem">{p['entry']}</td>
          <td class="center" style="color:#64748b;font-size:0.78rem">{p['exit']}</td>
          <td class="center">R$ {ep:.2f}</td>
          <td class="center">R$ {xp:.2f}</td>
          <td class="center" style="color:{pnl_color};font-weight:700;font-size:1rem">{icon} {pnl_str}</td>
        </tr>"""

    # Tabela mensal
    rows_html = ""
    for r in active_monthly:
        ret = r.get("retorno_mes_pct")
        ibov_r = r.get("ibov_retorno_mes_pct")
        ret_color = "#16a34a" if ret and ret >= 0 else "#dc2626"
        ibov_color = "#16a34a" if ibov_r and ibov_r >= 0 else "#dc2626"
        alpha = round(ret - ibov_r, 2) if ret is not None and ibov_r is not None else None
        alpha_color = "#16a34a" if alpha and alpha >= 0 else "#dc2626"
        entradas = ", ".join(r.get("entradas", [])) or "—"
        saidas = ", ".join(r.get("saidas", [])) or "—"
        top15 = ", ".join(r.get("top15", []))
        rows_html += f"""
        <tr>
          <td class="center">{r['data'][:7]}</td>
          <td class="center" style="color:{ret_color};font-weight:600">{f'+{ret:.1f}%' if ret and ret >= 0 else f'{ret:.1f}%' if ret else '—'}</td>
          <td class="center" style="color:{ibov_color}">{f'+{ibov_r:.1f}%' if ibov_r and ibov_r >= 0 else f'{ibov_r:.1f}%' if ibov_r else '—'}</td>
          <td class="center" style="color:{alpha_color}">{f'+{alpha:.1f}%' if alpha and alpha >= 0 else f'{alpha:.1f}%' if alpha else '—'}</td>
          <td class="center">{r['portfolio_valor']:.1f}</td>
          <td class="entradas">{entradas}</td>
          <td class="saidas">{saidas}</td>
          <td class="portfolio-cell" title="{top15}">{', '.join(r.get('top15', [])[:5])}{'...' if len(r.get('top15',[])) > 5 else ''}</td>
        </tr>"""

    total_ret = stats.get("retorno_total_pct", 0)
    ibov_total = stats.get("ibov_total_pct", 0)
    alpha = stats.get("alpha_pct", 0)
    max_dd = stats.get("max_drawdown_pct", 0)
    ret_medio = stats.get("retorno_medio_mensal_pct", 0)
    vol = stats.get("volatilidade_mensal_pct", 0)
    meses_pos = stats.get("meses_positivos", 0)
    meses_neg = stats.get("meses_negativos", 0)
    periodo = stats.get("periodo", "")
    n_meses = stats.get("meses", 0)

    ret_color = "#16a34a" if total_ret >= 0 else "#dc2626"
    alpha_color = "#16a34a" if alpha >= 0 else "#dc2626"
    cdi_alpha_color = "#16a34a" if total_ret >= cdi_total else "#dc2626"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backtest Magic Formula BR</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }}

  .header {{ background: linear-gradient(135deg, #064e3b 0%, #065f46 50%, #047857 100%); padding: 40px 32px 32px; }}
  .header h1 {{ font-size: 2rem; font-weight: 700; }}
  .header h1 span {{ color: #6ee7b7; }}
  .header p {{ color: #a7f3d0; margin-top: 6px; font-size: 0.9rem; }}
  .warning {{ background: rgba(251,191,36,0.15); border: 1px solid #f59e0b; border-radius: 8px; padding: 10px 16px; margin-top: 16px; font-size: 0.8rem; color: #fcd34d; }}

  .stats-bar {{ display: flex; gap: 20px; margin-top: 24px; flex-wrap: wrap; }}
  .stat {{ background: rgba(255,255,255,0.1); border-radius: 10px; padding: 14px 20px; min-width: 120px; }}
  .stat .val {{ font-size: 1.6rem; font-weight: 700; }}
  .stat .lbl {{ font-size: 0.72rem; color: #a7f3d0; margin-top: 3px; }}

  .container {{ max-width: 1400px; margin: 0 auto; padding: 32px; }}
  section {{ margin-bottom: 48px; }}
  h2 {{ font-size: 1.15rem; font-weight: 600; color: #6ee7b7; margin-bottom: 16px; border-left: 3px solid #10b981; padding-left: 12px; }}

  .charts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  @media (max-width: 900px) {{ .charts-grid {{ grid-template-columns: 1fr; }} }}
  .chart-box {{ background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 24px; }}
  .chart-box h3 {{ font-size: 0.88rem; color: #94a3b8; margin-bottom: 16px; }}
  .chart-box canvas {{ max-height: 300px; }}

  .kpis {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .kpi {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 18px; text-align: center; }}
  .kpi .kval {{ font-size: 1.8rem; font-weight: 700; }}
  .kpi .klbl {{ font-size: 0.75rem; color: #64748b; margin-top: 4px; }}

  .table-wrap {{ overflow-x: auto; border-radius: 12px; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b; font-size: 0.82rem; }}
  thead tr {{ background: #064e3b; }}
  th {{ padding: 11px 8px; text-align: center; font-weight: 600; color: #6ee7b7; white-space: nowrap; font-size: 0.75rem; }}
  td {{ padding: 10px 8px; border-bottom: 1px solid #1e293b; }}
  tr:hover td {{ background: #263548; }}
  tr:last-child td {{ border-bottom: none; }}
  .center {{ text-align: center; }}
  .entradas {{ color: #86efac; font-size: 0.78rem; }}
  .saidas {{ color: #fca5a5; font-size: 0.78rem; }}
  .portfolio-cell {{ font-size: 0.75rem; color: #94a3b8; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

  footer {{ text-align: center; padding: 24px; color: #475569; font-size: 0.78rem; border-top: 1px solid #1e293b; }}
</style>
</head>
<body>

<div class="header">
  <h1>Backtest Magic Formula <span>BR</span></h1>
  <p>Período: {periodo} · {n_meses} meses simulados · Gerado em {now}</p>
  <div class="warning">
    ⚠ Survivorship bias: universo fixo no CSV atual. Empresas que faliram ou saíram da B3 no período não estão incluídas. Retorno real seria menor.
  </div>
  <div class="stats-bar">
    <div class="stat"><div class="val" style="color:{ret_color}">{f'+{total_ret:.1f}%' if total_ret >= 0 else f'{total_ret:.1f}%'}</div><div class="lbl">Retorno Magic Formula</div></div>
    <div class="stat"><div class="val">{ibov_total:+.1f}%</div><div class="lbl">Retorno IBOV</div></div>
    <div class="stat"><div class="val">{cdi_total:+.1f}%</div><div class="lbl">CDI acumulado</div></div>
    <div class="stat"><div class="val" style="color:{alpha_color}">{alpha:+.1f}%</div><div class="lbl">Alpha vs IBOV</div></div>
    <div class="stat"><div class="val" style="color:{cdi_alpha_color}">{total_ret - cdi_total:+.1f}%</div><div class="lbl">Alpha vs CDI</div></div>
    <div class="stat"><div class="val" style="color:#dc2626">{max_dd:.1f}%</div><div class="lbl">Max Drawdown</div></div>
    <div class="stat"><div class="val">{meses_pos}W / {meses_neg}L</div><div class="lbl">Meses Pos / Neg</div></div>
  </div>
</div>

<div class="container">

  <section>
    <h2>Curva de Capital</h2>
    <div class="charts-grid">
      <div class="chart-box" style="grid-column: 1 / -1">
        <h3>Portfolio Magic Formula vs IBOV vs CDI (base 100)</h3>
        <canvas id="chartEquity"></canvas>
      </div>
      <div class="chart-box">
        <h3>Retorno Mensal Magic Formula (%)</h3>
        <canvas id="chartMonthly"></canvas>
      </div>
      <div class="chart-box">
        <h3>KPIs do Backtest</h3>
        <div class="kpis" style="margin-top:8px">
          <div class="kpi"><div class="kval" style="color:{ret_color}">{f'+{total_ret:.1f}%' if total_ret >= 0 else f'{total_ret:.1f}%'}</div><div class="klbl">Retorno Total</div></div>
          <div class="kpi"><div class="kval">{ret_medio:+.2f}%</div><div class="klbl">Retorno Médio/Mês</div></div>
          <div class="kpi"><div class="kval">{vol:.2f}%</div><div class="klbl">Volatilidade Mensal</div></div>
          <div class="kpi"><div class="kval" style="color:#dc2626">{max_dd:.1f}%</div><div class="klbl">Max Drawdown</div></div>
          <div class="kpi"><div class="kval">{alpha:+.1f}%</div><div class="klbl">Alpha IBOV</div></div>
          <div class="kpi"><div class="kval">{round(ret_medio / vol, 2) if vol else '—'}</div><div class="klbl">Sharpe Simples</div></div>
        </div>
      </div>
    </div>
  </section>

  <section>
    <h2>Carteira Atual — {carteira_data_ref} (posições abertas)</h2>
    <p style="color:#64748b;font-size:0.82rem;margin-bottom:14px">P&L calculado desde a data de entrada no portfolio. Preços de referência no fechamento mensal.</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th><th>Ticker</th><th>Entrada</th><th>Preço Entrada</th><th>Preço Atual</th><th>P&L %</th><th>EV/EBIT</th><th>ROIC</th><th>MF Score</th>
          </tr>
        </thead>
        <tbody>{carteira_html}</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Performance Realizadas (posições fechadas)</h2>
    <p style="color:#64748b;font-size:0.82rem;margin-bottom:14px">P&L por ticker desde entrada até saída do portfolio. Ordenado por retorno.</p>
    <div class="table-wrap" style="max-width:900px">
      <table>
        <thead>
          <tr>
            <th>Ticker</th><th>Entrada</th><th>Saída</th><th>Preço Entrada</th><th>Preço Saída</th><th>P&L %</th>
          </tr>
        </thead>
        <tbody>{perf_html}</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Histórico Mensal</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Mês</th><th>Retorno MF</th><th>IBOV</th><th>Alpha</th>
            <th>Portfólio</th><th>Entradas</th><th>Saídas</th><th>Top 5 Posições</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </section>

</div>

<footer>Magic Formula BR Backtest · {now} · Não é recomendação de investimento · Survivorship bias presente</footer>

<script>
const labels = {json.dumps(labels)};
const mfValues = {json.dumps(mf_values)};
const ibovValues = {json.dumps(ibov_values)};
const cdiValues = {json.dumps(cdi_values)};
const monthlyRets = {json.dumps(monthly_rets)};
const barColors = {json.dumps(bar_colors)};

new Chart(document.getElementById('chartEquity'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{
        label: 'Magic Formula',
        data: mfValues,
        borderColor: '#10b981',
        backgroundColor: 'rgba(16,185,129,0.08)',
        borderWidth: 2.5,
        pointRadius: 2,
        fill: true,
        tension: 0.3,
      }},
      {{
        label: 'IBOV',
        data: ibovValues,
        borderColor: '#64748b',
        borderWidth: 1.5,
        pointRadius: 0,
        borderDash: [4, 3],
        tension: 0.3,
      }},
      {{
        label: 'CDI',
        data: cdiValues,
        borderColor: '#f59e0b',
        borderWidth: 1.5,
        pointRadius: 0,
        borderDash: [2, 4],
        tension: 0.1,
      }}
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ labels: {{ color: '#94a3b8' }} }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y.toFixed(1)}}` }} }}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 18, font: {{ size: 10 }} }}, grid: {{ color: '#1e293b' }} }},
      y: {{ ticks: {{ color: '#94a3b8', callback: v => v.toFixed(0) }}, grid: {{ color: '#334155' }} }}
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
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y.toFixed(2)}}%` }} }}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 18, font: {{ size: 10 }} }}, grid: {{ color: '#1e293b' }} }},
      y: {{ ticks: {{ color: '#94a3b8', callback: v => v.toFixed(1) + '%' }}, grid: {{ color: '#334155' }} }}
    }}
  }}
}});
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[report_backtest] HTML gerado: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    out = args.output or str(Path(args.json).parent / "relatorio_backtest.html")
    generate_backtest_html(data, out)
