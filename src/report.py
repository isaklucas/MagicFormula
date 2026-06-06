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
        if f >= 20:
            return "#16a34a"
        if f >= 10:
            return "#ca8a04"
        return "#dc2626"
    except Exception:
        return "#6b7280"


def _color_ev(v):
    try:
        f = float(v)
        if f <= 5:
            return "#16a34a"
        if f <= 12:
            return "#ca8a04"
        return "#dc2626"
    except Exception:
        return "#6b7280"


def _color_div(v):
    try:
        f = float(v)
        if f < 0:
            return "#16a34a"
        if f < 2:
            return "#ca8a04"
        return "#dc2626"
    except Exception:
        return "#6b7280"


def _motivo(ag, c, group):
    """Works with both slim schema (motivo field) and full schema (pontos_fortes/riscos)."""
    # Slim schema: single motivo field
    if ag.get("motivo"):
        return ag["motivo"]
    # Full schema fallback
    if group == "COMPRAR":
        pontos = ag.get("pontos_fortes", [])
        return pontos[0] if pontos else "Bom balanço qualidade/valuation"
    # NEUTRO — derive from data
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
    analise_texto = ag.get("analise", "")  # full schema only
    pontos_fortes = ag.get("pontos_fortes", [])
    riscos = ag.get("riscos", [])
    qualidade_roic = ag.get("qualidade_roic", "")
    valuation_tag = ag.get("valuation", "")
    motivo_text = _motivo(ag, c, group)

    rec_colors = {"COMPRAR": "#16a34a", "NEUTRO": "#ca8a04", "CAUTELA": "#dc2626"}
    rec_color = rec_colors.get(recomendacao, "#64748b")
    border_color = "#16a34a" if group == "COMPRAR" else "#ca8a04"
    motivo_class = "motivo-comprar" if group == "COMPRAR" else "motivo-neutro"
    motivo_icon = "✓" if group == "COMPRAR" else "⚠"
    motivo_label = "Por que COMPRAR" if group == "COMPRAR" else "Por que NEUTRO"

    fortes_html = "".join(f'<li class="forte">✓ {p}</li>' for p in pontos_fortes)
    riscos_html = "".join(f'<li class="risco">⚠ {r}</li>' for r in riscos)
    tags_html = ""
    if qualidade_roic:
        tags_html += f'<span class="tag">{qualidade_roic}</span>'
    if valuation_tag:
        tags_html += f'<span class="tag">{valuation_tag}</span>'

    analysis_html = f"""
    <div class="ai-analysis">
      <div class="ai-header">
        <span class="ai-label">Análise IA</span>
        <span class="rec-badge" style="background:{rec_color}">{recomendacao}</span>
        <span class="score-ia">{score_ia}/10</span>
      </div>
      <div class="{motivo_class}">
        <span class="motivo-icon">{motivo_icon}</span>
        <span class="motivo-label">{motivo_label}:</span>
        <span class="motivo-text">{motivo_text}</span>
      </div>
      {("<p class='analise-text'>" + analise_texto + "</p>") if analise_texto else ""}
      {("<ul class='ai-list'>" + fortes_html + riscos_html + "</ul>") if (fortes_html or riscos_html) else ""}
      {("<div class='tags'>" + tags_html + "</div>") if tags_html else ""}
    </div>"""

    return f"""
    <div class="card" style="border-top: 3px solid {border_color}">
      <div class="card-header">
        <span class="card-rank" style="background:{border_color}22;color:{border_color};border:1px solid {border_color}44">#{rank}</span>
        <span class="card-ticker ticker-clickable" onclick="openModal('{ticker}')" title="Clique para ver detalhes">{ticker}</span>
        <span class="card-score">MF #{pos} · Score {_fmt(score, 0)}</span>
      </div>
      <div class="card-metrics">
        <div class="metric"><label>EV/EBIT</label><span style="color:{_color_ev(ev)}">{_fmt(ev)}x</span></div>
        <div class="metric"><label>ROIC</label><span style="color:{_color_roic(roic)}">{_fmt(roic)}%</span></div>
        <div class="metric"><label>Margem EBIT</label><span>{_fmt(margem)}%</span></div>
        <div class="metric"><label>ROE</label><span>{_fmt(roe)}%</span></div>
        <div class="metric"><label>Dív/EBIT</label><span style="color:{_color_div(div)}">{_fmt(div)}x</span></div>
        <div class="metric"><label>CAGR Receita</label><span>{_fmt(cagr_r)}%</span></div>
        <div class="metric"><label>CAGR Lucro</label><span>{_fmt(cagr_l)}%</span></div>
        <div class="metric"><label>Valor Mercado</label><span>{_fmt_brl(vm)}</span></div>
        <div class="metric"><label>Preço</label><span>R$ {_fmt(preco)}</span></div>
        <div class="metric"><label>Liq. Diária</label><span>{_fmt_brl(liq)}</span></div>
      </div>
      {analysis_html}
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
    rec_colors = {"COMPRAR": "#16a34a", "NEUTRO": "#ca8a04", "CAUTELA": "#dc2626"}
    rec_color = rec_colors.get(recomendacao, "#64748b")
    rec_cell = f"<span style='color:{rec_color};font-weight:700'>{recomendacao or '—'}</span>"

    motivo = _motivo(ag, c, group)
    motivo_class = "c" if group == "COMPRAR" else "n"
    motivo_short = motivo[:70] + "…" if len(motivo) > 70 else motivo

    return f"""
    <tr>
      <td class="center bold">{rank}</td>
      <td class="ticker-cell ticker-clickable" onclick="openModal('{ticker}')" title="Clique para detalhes">{ticker}</td>
      <td class="center" style="color:{_color_ev(ev)};font-weight:600">{_fmt(ev)}x</td>
      <td class="center" style="color:{_color_roic(roic)};font-weight:600">{_fmt(roic)}%</td>
      <td class="center">{_fmt(score, 0)}</td>
      <td class="center">{score_ia}/10</td>
      <td class="center">{rec_cell}</td>
      <td class="center">{_fmt(margem)}%</td>
      <td class="center">{_fmt(roe)}%</td>
      <td class="center" style="color:{_color_div(div)}">{_fmt(div)}x</td>
      <td class="center">{_fmt_brl(liq)}</td>
      <td class="center">{_fmt(cagr_r)}%</td>
      <td class="center">{_fmt(cagr_l)}%</td>
      <td class="center">{_fmt_brl(vm)}</td>
      <td class="motivo-cell {motivo_class}">{motivo_short}</td>
    </tr>"""


def _build_ticker_data(candidates: list, analyses: dict) -> dict:
    """Build JS data object for modal: all metrics + AI analysis per ticker."""
    cand_map = {c["TICKER"]: c for c in candidates}
    result = {}
    for ticker, ag in analyses.items():
        c = cand_map.get(ticker, {})
        hist = c.get("historico", {})
        trend_roic = hist.get("roic_trend", "")
        trend_margin = hist.get("ebit_margin_trend", "")
        trend_revenue = hist.get("revenue_trend", "")
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
            "trend_roic": trend_roic,
            "trend_margin": trend_margin,
            "trend_revenue": trend_revenue,
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
    apos_setor = data.get("apos_setor_limit", apos_rj)

    comprar_list = []
    neutro_list = []
    for ticker, ag in analyses.items():
        if ticker not in cand_lookup:
            continue
        if isinstance(ag, str):
            try:
                ag = json.loads(ag)
            except Exception:
                ag = {"motivo": ag}
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

    # Table rows
    rows_html = ""
    rows_html += f'<tr class="section-row-comprar"><td colspan="15">▼ COMPRAR — {n_comprar} Ações</td></tr>'
    for rank, (ticker, ag, score_ia, mf) in enumerate(comprar_list, 1):
        rows_html += _table_row(cand_lookup[ticker], ag, rank, "COMPRAR")

    rows_html += f'<tr class="section-row-neutro"><td colspan="15">▼ NEUTRO / CAUTELA — {n_neutro} Ações</td></tr>'
    for rank, (ticker, ag, score_ia, mf) in enumerate(neutro_list, 1):
        rows_html += _table_row(cand_lookup[ticker], ag, rank, "NEUTRO")

    # Cards
    comprar_cards = ""
    for rank, (ticker, ag, score_ia, mf) in enumerate(comprar_list, 1):
        comprar_cards += _build_card(cand_lookup[ticker], ag, rank, "COMPRAR")

    neutro_cards = ""
    for rank, (ticker, ag, score_ia, mf) in enumerate(neutro_list, 1):
        neutro_cards += _build_card(cand_lookup[ticker], ag, rank, "NEUTRO")

    # Chart data
    tickers_js = [t for t, *_ in comprar_list]
    roics_js = [round(float(cand_lookup[t].get("ROIC") or 0), 2) for t in tickers_js]
    ev_ebit_js = [round(float(cand_lookup[t].get("EV/EBIT") or 0), 2) for t in tickers_js]
    all_tickers_js = [t for t, *_ in (comprar_list + neutro_list)]
    all_roics_js = [round(float(cand_lookup[t].get("ROIC") or 0), 2) for t in all_tickers_js]
    all_ev_js = [round(float(cand_lookup[t].get("EV/EBIT") or 0), 2) for t in all_tickers_js]
    all_colors_js = ["#16a34a" if t in [x[0] for x in comprar_list] else "#ca8a04" for t in all_tickers_js]

    # Modal data (all per-ticker metrics + analysis)
    ticker_data = _build_ticker_data(data["candidatos"], analyses)
    ticker_data_js = json.dumps(ticker_data, ensure_ascii=False)

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Magic Formula BR — Análise IA</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}

  .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 50%, #2563eb 100%); padding: 40px 32px 32px; }}
  .header h1 {{ font-size: 2rem; font-weight: 700; letter-spacing: -0.5px; }}
  .header h1 span {{ color: #93c5fd; }}
  .header p {{ color: #bfdbfe; margin-top: 6px; font-size: 0.9rem; }}
  .stats-bar {{ display: flex; gap: 24px; margin-top: 24px; flex-wrap: wrap; }}
  .stat {{ background: rgba(255,255,255,0.1); border-radius: 10px; padding: 12px 20px; }}
  .stat .val {{ font-size: 1.5rem; font-weight: 700; color: #fff; }}
  .stat .lbl {{ font-size: 0.75rem; color: #bfdbfe; margin-top: 2px; }}
  .stat.green {{ background: rgba(22,163,74,0.25); }}
  .stat.orange {{ background: rgba(202,138,4,0.2); }}

  .container {{ max-width: 1400px; margin: 0 auto; padding: 32px; }}
  section {{ margin-bottom: 48px; }}
  h2 {{ font-size: 1.2rem; font-weight: 600; color: #93c5fd; margin-bottom: 16px; border-left: 3px solid #3b82f6; padding-left: 12px; }}

  /* Table */
  .table-wrap {{ overflow-x: auto; border-radius: 12px; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b; font-size: 0.85rem; }}
  thead tr {{ background: #1e3a8a; }}
  th {{ padding: 12px 10px; text-align: center; font-weight: 600; color: #93c5fd; white-space: nowrap; font-size: 0.78rem; }}
  td {{ padding: 11px 10px; border-bottom: 1px solid #334155; }}
  tr:hover td {{ background: #263548; }}
  tr:last-child td {{ border-bottom: none; }}
  .center {{ text-align: center; }}
  .bold {{ font-weight: 700; }}

  .ticker-cell {{ font-weight: 700; color: #60a5fa; font-size: 0.95rem; }}
  .ticker-clickable {{ cursor: pointer; transition: color 0.15s; }}
  .ticker-clickable:hover {{ color: #93c5fd !important; text-decoration: underline; }}

  .section-row-comprar td {{ background: #052e16; color: #86efac; font-weight: 700; font-size: 0.8rem; padding: 8px 12px; letter-spacing: 0.5px; }}
  .section-row-neutro td {{ background: #1c1400; color: #fbbf24; font-weight: 700; font-size: 0.8rem; padding: 8px 12px; letter-spacing: 0.5px; }}
  .motivo-cell {{ font-size: 0.72rem; color: #94a3b8; max-width: 180px; line-height: 1.3; }}
  .motivo-cell.c {{ color: #86efac; }}
  .motivo-cell.n {{ color: #fca5a5; }}

  /* Cards */
  .cards-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 20px; transition: border-color 0.2s; }}
  .card:hover {{ border-color: #3b82f6; }}
  .card-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
  .card-rank {{ border-radius: 8px; padding: 4px 10px; font-weight: 700; font-size: 0.85rem; }}
  .card-ticker {{ font-size: 1.25rem; font-weight: 700; color: #60a5fa; flex: 1; }}
  .card-score {{ font-size: 0.75rem; color: #64748b; }}
  .card-metrics {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
  .metric {{ background: #0f172a; border-radius: 8px; padding: 10px 12px; }}
  .metric label {{ display: block; font-size: 0.7rem; color: #64748b; margin-bottom: 4px; }}
  .metric span {{ font-size: 0.95rem; font-weight: 600; }}

  .ai-analysis {{ margin-top: 16px; background: #0f2040; border: 1px solid #1e40af; border-radius: 10px; padding: 14px; }}
  .ai-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
  .ai-label {{ background: #1e40af; color: #bfdbfe; font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; letter-spacing: 0.5px; }}
  .rec-badge {{ color: #fff; font-size: 0.72rem; font-weight: 700; padding: 2px 10px; border-radius: 4px; letter-spacing: 0.5px; }}
  .score-ia {{ margin-left: auto; font-size: 1rem; font-weight: 700; color: #f0abfc; }}
  .analise-text {{ font-size: 0.85rem; color: #cbd5e1; line-height: 1.6; margin-bottom: 10px; }}
  .ai-list {{ list-style: none; display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }}
  .forte {{ font-size: 0.78rem; color: #86efac; }}
  .risco {{ font-size: 0.78rem; color: #fca5a5; }}
  .tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }}
  .tag {{ background: #1e293b; border: 1px solid #334155; color: #94a3b8; font-size: 0.7rem; padding: 2px 8px; border-radius: 20px; }}

  .motivo-comprar {{ display: flex; align-items: flex-start; gap: 8px; background: rgba(22,163,74,0.12); border: 1px solid rgba(22,163,74,0.3); border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; }}
  .motivo-neutro {{ display: flex; align-items: flex-start; gap: 8px; background: rgba(202,138,4,0.12); border: 1px solid rgba(202,138,4,0.3); border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; }}
  .motivo-icon {{ font-size: 1rem; flex-shrink: 0; margin-top: 1px; }}
  .motivo-label {{ font-size: 0.72rem; font-weight: 700; color: #94a3b8; white-space: nowrap; flex-shrink: 0; }}
  .motivo-text {{ font-size: 0.8rem; color: #e2e8f0; line-height: 1.4; }}

  .section-divider {{ display: flex; align-items: center; gap: 16px; margin: 32px 0 20px; }}
  .section-divider-line {{ flex: 1; height: 1px; }}
  .section-divider-badge {{ font-size: 0.85rem; font-weight: 700; padding: 6px 20px; border-radius: 20px; white-space: nowrap; }}
  .comprar-divider .section-divider-line {{ background: #16a34a44; }}
  .comprar-divider .section-divider-badge {{ background: rgba(22,163,74,0.15); color: #86efac; border: 1px solid #16a34a44; }}
  .neutro-divider .section-divider-line {{ background: #ca8a0444; }}
  .neutro-divider .section-divider-badge {{ background: rgba(202,138,4,0.15); color: #fbbf24; border: 1px solid #ca8a0444; }}

  .charts-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr)); gap: 24px; }}
  .chart-box {{ background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 24px; }}
  .chart-box h3 {{ font-size: 0.9rem; color: #94a3b8; margin-bottom: 16px; }}
  .chart-box canvas {{ max-height: 300px; }}

  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-size: 0.78rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}

  .method-box {{ background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 24px; }}
  .method-box p {{ color: #94a3b8; font-size: 0.85rem; line-height: 1.7; margin-bottom: 10px; }}
  .method-box ul {{ color: #94a3b8; font-size: 0.85rem; line-height: 1.7; padding-left: 20px; }}

  footer {{ text-align: center; padding: 24px; color: #475569; font-size: 0.78rem; border-top: 1px solid #1e293b; }}

  /* ── Modal ─────────────────────────────────────────────────────────────── */
  .modal-overlay {{
    display: none;
    position: fixed; inset: 0; z-index: 1000;
    background: rgba(0,0,0,0.75);
    backdrop-filter: blur(4px);
    align-items: center; justify-content: center;
    padding: 16px;
  }}
  .modal-overlay.active {{ display: flex; }}

  .modal {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 16px;
    width: 100%; max-width: 760px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 25px 60px rgba(0,0,0,0.6);
    animation: slideUp 0.18s ease;
  }}
  @keyframes slideUp {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}

  .modal-header {{
    display: flex; align-items: center; gap: 14px;
    padding: 20px 24px 16px;
    border-bottom: 1px solid #334155;
    position: sticky; top: 0; background: #1e293b; z-index: 1;
  }}
  .modal-ticker {{ font-size: 1.6rem; font-weight: 700; color: #60a5fa; }}
  .modal-setor {{ font-size: 0.78rem; color: #64748b; background: #0f172a; border-radius: 6px; padding: 3px 10px; }}
  .modal-mf-badge {{ font-size: 0.78rem; color: #94a3b8; background: #0f172a; border-radius: 6px; padding: 3px 10px; }}
  .modal-close {{
    margin-left: auto; cursor: pointer; font-size: 1.4rem; color: #64748b;
    background: none; border: none; line-height: 1; padding: 4px 8px; border-radius: 6px;
    transition: background 0.15s;
  }}
  .modal-close:hover {{ background: #334155; color: #e2e8f0; }}

  .modal-body {{ padding: 20px 24px 24px; }}

  .modal-rec-row {{
    display: flex; align-items: center; gap: 12px; margin-bottom: 20px;
    padding: 14px 16px;
    border-radius: 10px;
    background: #0f172a;
    border: 1px solid #334155;
  }}
  .modal-rec-badge {{
    font-size: 0.85rem; font-weight: 700; padding: 4px 14px;
    border-radius: 6px; color: #fff; letter-spacing: 0.5px;
  }}
  .modal-score {{ font-size: 0.9rem; color: #94a3b8; }}
  .modal-score strong {{ color: #f0abfc; font-size: 1.1rem; }}
  .modal-motivo {{ font-size: 0.85rem; color: #cbd5e1; line-height: 1.5; margin-left: auto; max-width: 380px; text-align: right; }}

  .modal-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 18px;
  }}
  .modal-metric {{
    background: #0f172a; border-radius: 8px; padding: 10px 12px;
  }}
  .modal-metric label {{ display: block; font-size: 0.68rem; color: #64748b; margin-bottom: 4px; }}
  .modal-metric span {{ font-size: 1rem; font-weight: 600; }}

  .modal-trends {{
    background: #0f172a; border-radius: 10px; padding: 14px 16px; margin-bottom: 18px;
  }}
  .modal-trends h4 {{ font-size: 0.78rem; color: #64748b; font-weight: 600; margin-bottom: 10px; letter-spacing: 0.5px; text-transform: uppercase; }}
  .trend-grid {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .trend-item {{ display: flex; flex-direction: column; gap: 3px; }}
  .trend-label {{ font-size: 0.68rem; color: #64748b; }}
  .trend-val {{ font-size: 0.78rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; }}
  .trend-CRESCENTE {{ color: #86efac; background: rgba(22,163,74,0.15); }}
  .trend-DECRESCENTE {{ color: #fca5a5; background: rgba(220,38,38,0.15); }}
  .trend-ESTAVEL {{ color: #93c5fd; background: rgba(59,130,246,0.15); }}
  .trend-VOLATIL {{ color: #fbbf24; background: rgba(202,138,4,0.15); }}
  .trend-INSUFICIENTE {{ color: #64748b; background: rgba(100,116,139,0.15); }}

  .modal-si-btn {{
    display: flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; padding: 14px;
    background: linear-gradient(135deg, #1d4ed8, #2563eb);
    color: #fff; font-weight: 700; font-size: 0.95rem;
    border: none; border-radius: 10px; cursor: pointer;
    text-decoration: none;
    transition: filter 0.15s;
    letter-spacing: 0.3px;
  }}
  .modal-si-btn:hover {{ filter: brightness(1.15); }}
  .modal-si-btn svg {{ width: 16px; height: 16px; }}
</style>
</head>
<body>

<div class="header">
  <h1>Magic Formula <span>BR</span> — Análise IA</h1>
  <p>Gerado em {now} · Dados: StatusInvest · Metodologia: Joel Greenblatt · Análise: Claude IA</p>
  <div class="stats-bar">
    <div class="stat"><div class="val">{total_csv}</div><div class="lbl">Empresas no CSV</div></div>
    <div class="stat"><div class="val">{apos_filtros}</div><div class="lbl">Após filtros</div></div>
    <div class="stat"><div class="val">{apos_rj}</div><div class="lbl">Após verificação RJ</div></div>
    <div class="stat"><div class="val">{n_total}</div><div class="lbl">Analisadas pela IA</div></div>
    <div class="stat green"><div class="val">{n_comprar}</div><div class="lbl">✓ COMPRAR</div></div>
    <div class="stat orange"><div class="val">{n_neutro}</div><div class="lbl">⚠ NEUTRO/CAUTELA</div></div>
  </div>
</div>

<div class="container">

  <section>
    <h2>Tabela Resumo — {n_total} Ações · clique no ticker para detalhes</h2>
    <div class="legend">
      <span class="legend-item"><span class="legend-dot" style="background:#16a34a"></span>Ótimo</span>
      <span class="legend-item"><span class="legend-dot" style="background:#ca8a04"></span>Moderado</span>
      <span class="legend-item"><span class="legend-dot" style="background:#dc2626"></span>Atenção</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th><th>Ticker ↗</th><th>EV/EBIT</th><th>ROIC</th><th>Score MF</th>
            <th>Score IA</th><th>Recomendação</th>
            <th>Mg EBIT</th><th>ROE</th><th>Dív/EBIT</th><th>Liq Diária</th>
            <th>CAGR Rec.</th><th>CAGR Luc.</th><th>Val Mercado</th>
            <th>Motivo Principal</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Gráficos</h2>
    <div class="charts-grid">
      <div class="chart-box">
        <h3>ROIC — Ações COMPRAR (%)</h3>
        <canvas id="chartRoic"></canvas>
      </div>
      <div class="chart-box">
        <h3>EV/EBIT vs ROIC — Verde=COMPRAR / Laranja=NEUTRO</h3>
        <canvas id="chartScatter"></canvas>
      </div>
    </div>
  </section>

  <section>
    <h2>Análise Detalhada — COMPRAR ({n_comprar})</h2>
    <div class="section-divider comprar-divider">
      <div class="section-divider-line"></div>
      <div class="section-divider-badge">✓ COMPRAR — {n_comprar} Ações</div>
      <div class="section-divider-line"></div>
    </div>
    <div class="cards-grid">
      {comprar_cards}
    </div>

    <div class="section-divider neutro-divider" style="margin-top:40px">
      <div class="section-divider-line"></div>
      <div class="section-divider-badge">⚠ NEUTRO / CAUTELA — {n_neutro} Ações</div>
      <div class="section-divider-line"></div>
    </div>
    <div class="cards-grid">
      {neutro_cards}
    </div>
  </section>

  <section>
    <h2>Metodologia</h2>
    <div class="method-box">
      <p><strong>Magic Formula</strong> foi criada por Joel Greenblatt (livro "The Little Book That Beats the Market", 2005). O objetivo é encontrar <em>boas empresas a preços baratos</em> de forma sistemática.</p>
      <p><strong>Como funciona:</strong></p>
      <ul>
        <li><strong>EV/EBIT</strong> — mede o preço pago pela empresa em relação ao seu lucro operacional. Menor = mais barato.</li>
        <li><strong>ROIC</strong> — Return on Invested Capital. Mede a qualidade da empresa. Maior = melhor retorno sobre capital.</li>
        <li>Cada empresa recebe um rank em cada métrica. A soma dos ranks forma o <strong>Score MF</strong>. Menor score = melhor posição.</li>
        <li><strong>Análise IA:</strong> Claude analisa dados quantitativos (EV/EBIT, ROIC, CAGR, dívida, margens, tendências trimestrais) e aplica regras anti-alucinação para classificar cada ação.</li>
      </ul>
      <p style="margin-top:10px"><strong>Critérios COMPRAR:</strong> ROIC sustentável por margens e crescimento coerentes · CAGR Lucros positivo · Dívida controlada · Valuation justificado pela qualidade.</p>
      <p><strong>Critérios NEUTRO:</strong> CAGR Lucros negativo · Dívida/EBIT &gt; 3x · Margem EBIT &lt; 7% · ROIC com pico pontual distorcendo média · Tendências trimestrais deteriorando.</p>
    </div>
  </section>

</div>

<footer>Magic Formula BR · {now} · Não é recomendação de investimento.</footer>

<!-- ── Modal ──────────────────────────────────────────────────────────────── -->
<div class="modal-overlay" id="modalOverlay" onclick="handleOverlayClick(event)">
  <div class="modal" id="modal">
    <div class="modal-header">
      <span class="modal-ticker" id="modalTicker">—</span>
      <span class="modal-setor" id="modalSetor">—</span>
      <span class="modal-mf-badge" id="modalMF">—</span>
      <button class="modal-close" onclick="closeModal()" title="Fechar (ESC)">✕</button>
    </div>
    <div class="modal-body">
      <div class="modal-rec-row" id="modalRecRow">
        <span class="modal-rec-badge" id="modalRecBadge">—</span>
        <span class="modal-score" id="modalScore">—</span>
        <span class="modal-motivo" id="modalMotivo">—</span>
      </div>

      <div class="modal-grid" id="modalGrid"></div>

      <div class="modal-trends" id="modalTrendsBox" style="display:none">
        <h4>Tendências Históricas (yfinance)</h4>
        <div class="trend-grid" id="modalTrends"></div>
      </div>

      <a class="modal-si-btn" id="modalSIBtn" href="#" target="_blank" rel="noopener">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
        Abrir no StatusInvest
      </a>
    </div>
  </div>
</div>

<script>
const TICKER_DATA = {ticker_data_js};

const tickers = {json.dumps(tickers_js)};
const roics = {json.dumps(roics_js)};
const evEbits = {json.dumps(ev_ebit_js)};
const allTickers = {json.dumps(all_tickers_js)};
const allRoics = {json.dumps(all_roics_js)};
const allEvs = {json.dumps(all_ev_js)};
const allColors = {json.dumps(all_colors_js)};

const palette = [
  '#16a34a','#22c55e','#4ade80','#86efac','#bbf7d0',
  '#15803d','#166534','#14532d','#052e16','#134e4a',
  '#0f766e','#0d9488','#14b8a6','#2dd4bf','#5eead4'
];

new Chart(document.getElementById('chartRoic'), {{
  type: 'bar',
  data: {{
    labels: tickers,
    datasets: [{{ label: 'ROIC (%)', data: roics, backgroundColor: palette, borderRadius: 6 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y.toFixed(1)}}%` }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#94a3b8', font: {{ size: 11 }} }}, grid: {{ color: '#1e293b' }} }},
      y: {{ ticks: {{ color: '#94a3b8', callback: v => v + '%' }}, grid: {{ color: '#334155' }} }}
    }}
  }}
}});

new Chart(document.getElementById('chartScatter'), {{
  type: 'scatter',
  data: {{
    datasets: [{{
      label: 'Empresas',
      data: allTickers.map((t, i) => ({{ x: allEvs[i], y: allRoics[i], label: t }})),
      backgroundColor: allColors,
      pointRadius: 8, pointHoverRadius: 10,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      tooltip: {{ callbacks: {{ label: ctx => `${{ctx.raw.label}} | EV/EBIT: ${{ctx.raw.x}} | ROIC: ${{ctx.raw.y}}%` }} }},
      legend: {{ display: false }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'EV/EBIT (menor = mais barato)', color: '#64748b' }}, ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
      y: {{ title: {{ display: true, text: 'ROIC % (maior = melhor)', color: '#64748b' }}, ticks: {{ color: '#94a3b8', callback: v => v + '%' }}, grid: {{ color: '#334155' }} }}
    }}
  }}
}});

// ── Modal ──────────────────────────────────────────────────────────────────

function fmt(v, dec=2, suf='') {{
  if (v === null || v === undefined || isNaN(v)) return '—';
  return Number(v).toFixed(dec) + suf;
}}
function fmtBRL(v) {{
  if (v === null || v === undefined || isNaN(v)) return '—';
  if (v >= 1e9) return 'R$ ' + (v/1e9).toFixed(1) + 'B';
  if (v >= 1e6) return 'R$ ' + (v/1e6).toFixed(1) + 'M';
  return 'R$ ' + v.toLocaleString('pt-BR', {{maximumFractionDigits: 0}});
}}
function colorROIC(v) {{
  if (v >= 20) return '#16a34a';
  if (v >= 10) return '#ca8a04';
  return '#dc2626';
}}
function colorEV(v) {{
  if (v <= 5) return '#16a34a';
  if (v <= 12) return '#ca8a04';
  return '#dc2626';
}}
function colorDiv(v) {{
  if (v < 0) return '#16a34a';
  if (v < 2) return '#ca8a04';
  return '#dc2626';
}}
function colorRec(r) {{
  return r === 'COMPRAR' ? '#16a34a' : r === 'CAUTELA' ? '#dc2626' : '#ca8a04';
}}

function openModal(ticker) {{
  const d = TICKER_DATA[ticker];
  if (!d) return;

  document.getElementById('modalTicker').textContent = ticker;
  document.getElementById('modalSetor').textContent = d.setor || '—';
  document.getElementById('modalMF').textContent = d.posicao_mf ? `MF #${{d.posicao_mf}} · Score ${{d.mf_score ?? '—'}}` : '—';

  // Rec row
  const rec = d.recomendacao || '—';
  const badge = document.getElementById('modalRecBadge');
  badge.textContent = rec;
  badge.style.background = colorRec(rec);
  const scoreEl = document.getElementById('modalScore');
  scoreEl.innerHTML = `Score IA: <strong>${{d.score_ia ?? '—'}}/10</strong>`;
  document.getElementById('modalMotivo').textContent = d.motivo || '';

  // Metrics grid
  const grid = document.getElementById('modalGrid');
  const metrics = [
    ['EV/EBIT',     fmt(d.ev_ebit) + 'x',   colorEV(d.ev_ebit)],
    ['ROIC',        fmt(d.roic) + '%',        colorROIC(d.roic)],
    ['Margem EBIT', fmt(d.margem) + '%',      ''],
    ['ROE',         fmt(d.roe) + '%',         ''],
    ['Dív/EBIT',    fmt(d.div_ebit) + 'x',   colorDiv(d.div_ebit)],
    ['CAGR Receita',fmt(d.cagr_r) + '%',     ''],
    ['CAGR Lucro',  fmt(d.cagr_l) + '%',     ''],
    ['Val Mercado', fmtBRL(d.vm),            ''],
    ['Liq Diária',  fmtBRL(d.liq),           ''],
    ['Preço',       d.preco ? 'R$ ' + fmt(d.preco) : '—', ''],
  ];
  grid.innerHTML = metrics.map(([lbl, val, clr]) =>
    `<div class="modal-metric">
       <label>${{lbl}}</label>
       <span style="color:${{clr || '#e2e8f0'}}">${{val}}</span>
     </div>`
  ).join('');

  // Trends
  const trends = [
    ['ROIC Trimestral', d.trend_roic],
    ['Margem EBIT',     d.trend_margin],
    ['Receita',         d.trend_revenue],
  ].filter(([, v]) => v);
  const trendsBox = document.getElementById('modalTrendsBox');
  if (trends.length) {{
    document.getElementById('modalTrends').innerHTML = trends.map(([lbl, val]) =>
      `<div class="trend-item">
         <span class="trend-label">${{lbl}}</span>
         <span class="trend-val trend-${{val}}">${{val}}</span>
       </div>`
    ).join('');
    trendsBox.style.display = '';
  }} else {{
    trendsBox.style.display = 'none';
  }}

  // StatusInvest link
  document.getElementById('modalSIBtn').href =
    `https://statusinvest.com.br/acoes/${{ticker.toLowerCase()}}`;

  document.getElementById('modalOverlay').classList.add('active');
  document.body.style.overflow = 'hidden';
}}

function closeModal() {{
  document.getElementById('modalOverlay').classList.remove('active');
  document.body.style.overflow = '';
}}

function handleOverlayClick(e) {{
  if (e.target === document.getElementById('modalOverlay')) closeModal();
}}

document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') closeModal();
}});
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[report] HTML gerado: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Path to candidates.json")
    parser.add_argument("--analysis", default="", help="JSON string with per-ticker analysis")
    parser.add_argument("--analysis-file", default="", help="Path to analyses JSON file")
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
        try:
            analyses = json.loads(args.analysis)
        except Exception:
            analyses = {}

    out = args.output or str(Path(args.json).parent / "relatorio.html")
    generate_html(data, analyses, out, top_n=args.top)
