"""
Gera relatório HTML com TOP 10 FIIs/FIAgros por DY Limpo.
Suporta análise IA opcional via argumento 'analyses'.

CLI: python src/fii_report.py [--analysis-file output/fii_analyses.json]
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent))
from navbar import get_navbar


def _fmt(val, decimals: int = 2, suffix: str = "") -> str:
    if val is None or val != val:
        return "—"
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except Exception:
        return str(val)


def _fmt_brl(val) -> str:
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


def _color_pvp(v) -> str:
    try:
        f = float(v)
        if f <= 0.75: return "#3fb950"
        if f <= 0.89: return "#d29922"
        return "#f85149"
    except Exception:
        return "#8b949e"


def _color_dy(v) -> str:
    try:
        f = float(v)
        if f >= 12: return "#3fb950"
        if f >= 9:  return "#d29922"
        return "#8b949e"
    except Exception:
        return "#8b949e"


def _age_str(idade_dias: int) -> str:
    if idade_dias <= 0:
        return "—"
    anos  = idade_dias // 365
    meses = (idade_dias % 365) // 30
    if anos >= 1:
        return f"{anos}a {meses}m" if meses else f"{anos} anos"
    return f"{meses} meses"


def _badge_tipo(tipo: str) -> str:
    color = "#58a6ff" if tipo == "FII" else "#bc8cff"
    return (
        f'<span class="badge" '
        f'style="background:{color}22;color:{color};border:1px solid {color}55;font-size:.65rem">'
        f'{tipo}</span>'
    )


def _badge_removidos(n: int) -> str:
    if n == 0:
        return '<span style="color:#3fb950;font-size:.8rem">✓ limpo</span>'
    color = "#d29922" if n == 1 else "#f85149"
    label = f"{n} {'mês' if n == 1 else 'meses'} removido{'s' if n > 1 else ''}"
    return (
        f'<span class="badge" '
        f'style="background:{color}22;color:{color};border:1px solid {color}55;font-size:.65rem">'
        f'⚠ {label}</span>'
    )


# ── Seção IA nos cards ────────────────────────────────────────────────────────

_REC_COLORS = {
    "COMPRAR": ("#3fb950", "#3fb95022", "#3fb95044"),
    "NEUTRO":  ("#8b949e", "#8b949e22", "#8b949e44"),
    "CAUTELA": ("#f85149", "#f8514922", "#f8514944"),
}
_RISCO_COLORS = {
    "BAIXO": "#3fb950",
    "MEDIO": "#d29922",
    "ALTO":  "#f85149",
}


def _ia_section(analysis: dict | None) -> str:
    if not analysis:
        return ""

    rec     = analysis.get("recomendacao", "—")
    score   = analysis.get("score_compra", "—")
    risco   = analysis.get("nivel_risco", "—")
    hip     = analysis.get("hipotese_desconto", "")
    motivo  = analysis.get("motivo", "")
    alertas = analysis.get("alertas") or []
    pontos  = analysis.get("pontos_fortes") or []

    rc, rc_bg, rc_bd = _REC_COLORS.get(rec, ("#8b949e", "#8b949e22", "#8b949e44"))
    rk = _RISCO_COLORS.get(risco, "#8b949e")

    alertas_html = ""
    if alertas:
        items = "".join(
            f'<li style="margin-bottom:1px">{a}</li>' for a in alertas[:3]
        )
        alertas_html = (
            f'<ul style="font-size:.68rem;color:#d29922;margin:4px 0 2px 14px;'
            f'padding:0;line-height:1.5">{items}</ul>'
        )

    pontos_html = ""
    if pontos:
        items = "".join(
            f'<li style="margin-bottom:1px">{p}</li>' for p in pontos[:2]
        )
        pontos_html = (
            f'<ul style="font-size:.68rem;color:#3fb950;margin:2px 0 0 14px;'
            f'padding:0;line-height:1.5">{items}</ul>'
        )

    return f"""
    <div class="mt-2 pt-2" style="border-top:1px solid #21262d">
      <div class="d-flex align-items-center gap-2 mb-1 flex-wrap">
        <span style="font-size:.58rem;color:#8b949e;text-transform:uppercase;letter-spacing:.6px">Análise IA</span>
        <span class="badge" style="background:{rc_bg};color:{rc};border:1px solid {rc_bd};font-size:.65rem">{rec}</span>
        <span class="badge" style="background:{rk}22;color:{rk};border:1px solid {rk}44;font-size:.65rem">Risco {risco}</span>
        <span style="font-size:.9rem;margin-left:auto;color:#e6edf3;font-weight:600">{score}/10</span>
      </div>
      <div style="font-size:.76rem;color:#c9d1d9;line-height:1.45;margin-bottom:3px">{hip}</div>
      <div style="font-size:.72rem;color:#8b949e;line-height:1.4">{motivo}</div>
      {alertas_html}{pontos_html}
    </div>"""


# ── Card + linha de tabela ────────────────────────────────────────────────────

def _build_card(r: dict, analysis: dict | None = None) -> str:
    ticker  = r["TICKER"]
    tipo    = r.get("TIPO", "FII")
    seg     = r.get("SEGMENTO", "—") or "—"
    pvp     = r.get("PVP")
    preco   = r.get("preco_display")
    liq     = r.get("LIQUIDEZ")
    vpa     = r.get("VPA")
    posicao = r.get("posicao", "—")

    dy_info   = r.get("dy_info", {})
    dy_bruto  = dy_info.get("dy_bruto_12m")
    dy_limpo  = dy_info.get("dy_limpo_12m")
    n_remov   = dy_info.get("meses_removidos", 0)
    meses_ok  = dy_info.get("meses_com_dados", 0)
    fonte_dy  = dy_info.get("fonte", "")

    idade_dias = r.get("idade_dias", -1)
    ult_div    = r.get("ultimo_div")
    data_div   = r.get("data_ultimo_div", "")

    border_color = "#58a6ff" if tipo == "FII" else "#bc8cff"

    fonte_label = "CSV" if fonte_dy == "CSV" else (f"{meses_ok} meses" if meses_ok else "—")
    metrics = [
        ("P/VP",       f"{_fmt(pvp, 3)}",         _color_pvp(pvp)),
        ("DY Bruto",   f"{_fmt(dy_bruto)}%",      _color_dy(dy_bruto)),
        ("DY Limpo",   f"{_fmt(dy_limpo)}%",      _color_dy(dy_limpo)),
        ("Preço",      f"R$ {_fmt(preco)}",        ""),
        ("VPA",        f"R$ {_fmt(vpa)}",          ""),
        ("Liq. Diária",_fmt_brl(liq),              ""),
        ("Dados",      fonte_label,                ""),
        ("Idade",      _age_str(idade_dias),        ""),
        ("Últ. Div.",  f"R$ {_fmt(ult_div, 4)}" if ult_div else "—", ""),
        ("Data Div.",  data_div or "—",             ""),
    ]
    metrics_html = "".join(
        '<div class="col-6 col-sm-4">'
        '<div class="p-2 rounded-2" style="background:#0d1117">'
        f'<div class="text-muted" style="font-size:.65rem">{lbl}</div>'
        f'<div class="fw-semibold" style="font-size:.9rem;color:{clr if clr else "#e6edf3"}">{val}</div>'
        '</div></div>'
        for lbl, val, clr in metrics
    )

    ia_html = _ia_section(analysis)

    return f"""
    <div class="col">
      <div class="card h-100" style="background:#161b22;border:1px solid #30363d;border-top:3px solid {border_color}">
        <div class="card-header d-flex align-items-center gap-2 py-2" style="background:#0d1117;border-bottom:1px solid #30363d">
          <span class="badge rounded-pill" style="background:{border_color}22;color:{border_color};border:1px solid {border_color}44">#{posicao}</span>
          <span class="fw-bold" style="font-size:1.1rem;color:{border_color}">{ticker}</span>
          {_badge_tipo(tipo)}
          <span class="text-muted ms-auto" style="font-size:.7rem">{seg}</span>
        </div>
        <div class="card-body pb-2">
          <div class="row g-2 mb-3">{metrics_html}</div>
          <div class="d-flex align-items-center gap-2 flex-wrap">
            {_badge_removidos(n_remov)}
            <a href="{"https://statusinvest.com.br/fundos-imobiliarios/" + ticker.lower() if tipo == "FII" else "https://statusinvest.com.br/fundos-agro/" + ticker.lower()}"
               target="_blank" rel="noopener"
               class="btn btn-sm ms-auto" style="font-size:.72rem;background:#21262d;color:#58a6ff;border:1px solid #30363d">
              ↗ StatusInvest
            </a>
          </div>
          {ia_html}
        </div>
      </div>
    </div>"""


def _table_row(r: dict) -> str:
    ticker    = r["TICKER"]
    tipo      = r.get("TIPO", "FII")
    seg       = r.get("SEGMENTO", "—") or "—"
    pvp       = r.get("PVP")
    preco     = r.get("preco_display")
    liq       = r.get("LIQUIDEZ")
    posicao   = r.get("posicao", "—")

    dy_info   = r.get("dy_info", {})
    dy_bruto  = dy_info.get("dy_bruto_12m")
    dy_limpo  = dy_info.get("dy_limpo_12m")
    n_remov   = dy_info.get("meses_removidos", 0)

    idade_dias = r.get("idade_dias", -1)
    ult_div    = r.get("ultimo_div")

    border_color = "#58a6ff" if tipo == "FII" else "#bc8cff"

    remov_html = (
        '<span style="color:#3fb950;font-size:.75rem">✓</span>'
        if n_remov == 0
        else f'<span style="color:#d29922;font-size:.75rem">⚠ {n_remov}</span>'
    )

    return f"""
    <tr>
      <td class="text-center fw-bold text-secondary">{posicao}</td>
      <td class="fw-bold" style="color:{border_color}">{ticker}</td>
      <td class="text-center"><span style="font-size:.75rem;color:{border_color}">{tipo}</span></td>
      <td class="text-secondary" style="font-size:.8rem">{seg}</td>
      <td class="text-center fw-semibold" style="color:{_color_pvp(pvp)}">{_fmt(pvp, 3)}</td>
      <td class="text-center" style="color:{_color_dy(dy_bruto)}">{_fmt(dy_bruto)}%</td>
      <td class="text-center fw-bold" style="color:{_color_dy(dy_limpo)}">{_fmt(dy_limpo)}%</td>
      <td class="text-center">{remov_html}</td>
      <td class="text-center text-secondary" style="font-size:.8rem">{_age_str(idade_dias)}</td>
      <td class="text-center text-secondary" style="font-size:.8rem">R$ {_fmt(ult_div, 4) if ult_div else "—"}</td>
      <td class="text-center text-secondary" style="font-size:.8rem">R$ {_fmt(preco)}</td>
      <td class="text-center text-secondary" style="font-size:.8rem">{_fmt_brl(liq)}</td>
    </tr>"""


def _build_removidos_section_fii(removidos: list[dict]) -> str:
    if not removidos:
        return ""

    from collections import Counter
    counts = Counter(r["etapa"] for r in removidos)
    etapas_order = ["Filtro P/VP", "Sem dados P/VP", "Filtro de Idade", "DY Insuficiente"]
    badge_colors = {
        "Filtro P/VP":      "#58a6ff",
        "Sem dados P/VP":   "#8b949e",
        "Filtro de Idade":  "#d29922",
        "DY Insuficiente":  "#f85149",
    }

    badges_html = "".join(
        f'<span class="badge me-1" style="background:{badge_colors.get(e,"#444")}22;'
        f'color:{badge_colors.get(e,"#aaa")};border:1px solid {badge_colors.get(e,"#444")}55;'
        f'font-size:.68rem">{e}: {counts[e]}</span>'
        for e in etapas_order if e in counts
    )

    rows_html = "".join(
        f'<tr data-etapa="{r["etapa"]}">'
        f'<td class="fw-bold" style="color:#e6edf3;font-size:.82rem">{r["ticker"]}</td>'
        f'<td><span class="badge" style="background:{badge_colors.get(r["etapa"],"#444")}22;'
        f'color:{badge_colors.get(r["etapa"],"#aaa")};border:1px solid {badge_colors.get(r["etapa"],"#444")}55;'
        f'font-size:.65rem">{r["etapa"]}</span></td>'
        f'<td class="text-secondary" style="font-size:.78rem">{r["motivo"]}</td>'
        f'</tr>'
        for r in removidos
    )

    return f"""
  <section class="mb-4">
    <div class="section-title">Fundos removidos — transparência do filtro</div>
    <div class="card">
      <div class="card-header d-flex align-items-center gap-2 py-2 flex-wrap"
           style="background:#0d1117;cursor:pointer"
           onclick="toggleRemovidos()">
        <span style="color:#d29922;font-size:1rem">⚠</span>
        <span class="fw-semibold" style="font-size:.85rem">{len(removidos)} fundos removidos em {len(counts)} etapas</span>
        <div class="ms-2 d-flex gap-1 flex-wrap">{badges_html}</div>
        <span id="removidos-chevron" class="ms-auto text-muted" style="font-size:.8rem">▼ expandir</span>
      </div>
      <div id="removidos-body" style="display:none">
        <div class="p-3 border-bottom" style="border-color:#30363d!important">
          <div class="d-flex gap-2 align-items-center flex-wrap">
            <input type="text" id="removidos-search" class="form-control form-control-sm"
                   style="max-width:200px;background:#0d1117;border-color:#30363d;color:#e6edf3"
                   placeholder="Buscar ticker..."
                   oninput="filterRemovidos()">
            <select id="removidos-filter" class="form-select form-select-sm"
                    style="max-width:220px;background:#0d1117;border-color:#30363d;color:#e6edf3"
                    onchange="filterRemovidos()">
              <option value="">Todas as etapas</option>
              {"".join(f'<option value="{e}">{e} ({counts[e]})</option>' for e in etapas_order if e in counts)}
            </select>
            <span id="removidos-count" class="text-muted" style="font-size:.75rem">{len(removidos)} itens</span>
          </div>
        </div>
        <div class="table-responsive" style="max-height:420px;overflow-y:auto">
          <table class="table table-dark table-sm mb-0" id="removidos-table">
            <thead style="position:sticky;top:0;background:#161b22">
              <tr>
                <th style="font-size:.72rem;color:#58a6ff">Ticker</th>
                <th style="font-size:.72rem;color:#58a6ff">Etapa</th>
                <th style="font-size:.72rem;color:#58a6ff">Motivo</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
      </div>
    </div>
  </section>
<script>
function toggleRemovidos() {{
  const body = document.getElementById('removidos-body');
  const chev = document.getElementById('removidos-chevron');
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  chev.textContent = open ? '▼ expandir' : '▲ recolher';
}}
function filterRemovidos() {{
  const q     = document.getElementById('removidos-search').value.toUpperCase();
  const etapa = document.getElementById('removidos-filter').value;
  const rows  = document.querySelectorAll('#removidos-table tbody tr');
  let visible = 0;
  rows.forEach(tr => {{
    const ticker    = tr.cells[0].textContent.toUpperCase();
    const rowEtapa  = tr.dataset.etapa || '';
    const show = ticker.includes(q) && (!etapa || rowEtapa === etapa);
    tr.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('removidos-count').textContent = visible + ' itens';
}}
</script>"""


def generate_html(
    top10: list[dict],
    meta: dict,
    output_path: str,
    analyses: dict | None = None,
) -> None:
    now         = datetime.now().strftime("%d/%m/%Y %H:%M")
    n_total_csv = meta.get("total_csv", "—")
    n_pos_pvp   = meta.get("apos_pvp", "—")
    n_pos_idade = meta.get("apos_idade", "—")
    n_validos   = meta.get("validos", "—")
    use_csv     = meta.get("use_csv", False)
    fonte_label = "CSV StatusInvest" if use_csv else "Funds Explorer + yfinance"

    has_ia = bool(analyses)

    cards_html    = "".join(
        _build_card(r, analyses.get(r["TICKER"]) if analyses else None)
        for r in top10
    )
    rows_html     = "".join(_table_row(r) for r in top10)
    removidos_html = _build_removidos_section_fii(meta.get("removidos", []))

    # IA summary badge
    ia_badge = ""
    if has_ia:
        comprars = sum(1 for a in analyses.values() if a.get("recomendacao") == "COMPRAR")
        cautelar = sum(1 for a in analyses.values() if a.get("recomendacao") == "CAUTELA")
        neutros  = sum(1 for a in analyses.values() if a.get("recomendacao") == "NEUTRO")
        ia_badge = (
            f'<span class="stat-pill" style="background:rgba(88,166,255,.15)">'
            f'<div class="val" style="font-size:1rem">🤖 IA</div>'
            f'<div class="lbl">{comprars}✓ {neutros}~ {cautelar}⚠</div></span>'
        )

    # JS data
    tickers_js  = json.dumps([r["TICKER"] for r in top10])
    dy_limpo_js = json.dumps([r.get("dy_info", {}).get("dy_limpo_12m", 0) for r in top10])
    dy_bruto_js = json.dumps([r.get("dy_info", {}).get("dy_bruto_12m", 0) for r in top10])
    pvp_js      = json.dumps([round(float(r.get("PVP") or 0), 3) for r in top10])
    tipo_colors_js = json.dumps([
        "#58a6ff" if r.get("TIPO") == "FII" else "#bc8cff"
        for r in top10
    ])

    html = f"""<!DOCTYPE html>
<html lang="pt-BR" data-bs-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FII / FIAgro — Screener DY Limpo</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
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
  .section-title {{
    font-size: .85rem; font-weight: 600; color: #58a6ff;
    border-left: 3px solid #1d4ed8; padding-left: .6rem; margin-bottom: 1rem;
    text-transform: uppercase; letter-spacing: .5px;
  }}
  .table-dark {{ --bs-table-bg: #161b22; --bs-table-hover-bg: #1f2937; --bs-table-border-color: #30363d; }}
  .table th {{ font-size: .72rem; white-space: nowrap; color: #58a6ff; }}
  .table td {{ vertical-align: middle; }}
  .chart-card {{ background: #161b22; border: 1px solid #30363d; border-radius: .75rem; padding: 1.25rem; }}
  .chart-card h3 {{ font-size: .82rem; color: #8b949e; margin-bottom: 1rem; }}
  .card {{ --bs-card-border-color: #30363d; }}
  footer {{ font-size: .75rem; color: #6e7681; padding: 1.5rem; text-align: center; border-top: 1px solid #30363d; }}
</style>
</head>
<body>

{get_navbar("fii")}

<!-- Hero -->
<div class="hero">
  <div class="container-fluid px-3 px-md-4">
    <h1>FII / FIAgro — <em>TOP 10 DY Limpo</em></h1>
    <p class="text-light opacity-75 mb-3" style="font-size:.85rem">
      {now} · {fonte_label} · P/VP &lt; 0.90 · Anomalias removidas via IQR
      {"· Análise IA incluída" if has_ia else ""}
    </p>
    <div class="d-flex flex-wrap gap-2">
      <div class="stat-pill"><div class="val">{n_total_csv}</div><div class="lbl">Total fundos</div></div>
      <div class="stat-pill"><div class="val">{n_pos_pvp}</div><div class="lbl">P/VP &lt; 0.90</div></div>
      <div class="stat-pill"><div class="val">{n_pos_idade}</div><div class="lbl">&gt; 1 ano</div></div>
      <div class="stat-pill"><div class="val">{n_validos}</div><div class="lbl">DY válido</div></div>
      <div class="stat-pill green"><div class="val">{len(top10)}</div><div class="lbl">TOP 10</div></div>
      {ia_badge}
    </div>
    <div class="mt-3 d-flex gap-3" style="font-size:.75rem;color:#bfdbfe">
      <span><span style="color:#58a6ff">●</span> FII</span>
      <span><span style="color:#bc8cff">●</span> FIAgro</span>
      <span><span style="color:#3fb950">●</span> DY ≥ 12%</span>
      <span><span style="color:#d29922">●</span> DY 9–12%</span>
      {"<span>🤖 Análise IA por fundo</span>" if has_ia else ""}
    </div>
  </div>
</div>

<div class="container-fluid px-3 px-md-4 py-4">

  <!-- Tabela -->
  <section class="mb-5">
    <div class="section-title">Tabela resumo — TOP 10</div>
    <div class="table-responsive rounded-3" style="border:1px solid #30363d">
      <table class="table table-dark table-hover table-sm mb-0">
        <thead>
          <tr>
            <th>#</th><th>Ticker</th><th>Tipo</th><th>Segmento</th>
            <th>P/VP</th><th>DY Bruto</th><th>DY Limpo</th><th>Removidos</th>
            <th>Idade</th><th>Últ. Div.</th><th>Preço</th><th>Liq. Diária</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </section>

  <!-- Gráficos -->
  <section class="mb-5">
    <div class="section-title">Gráficos</div>
    <div class="row g-3">
      <div class="col-12 col-lg-6">
        <div class="chart-card">
          <h3>DY Limpo vs DY Bruto 12M (%)</h3>
          <canvas id="chartDY" style="max-height:280px"></canvas>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="chart-card">
          <h3>P/VP por fundo <span style="color:#58a6ff">●</span> FII <span style="color:#bc8cff">●</span> FIAgro</h3>
          <canvas id="chartPVP" style="max-height:280px"></canvas>
        </div>
      </div>
    </div>
  </section>

  <!-- Cards -->
  <section class="mb-5">
    <div class="section-title">Análise detalhada — TOP 10{"  · 🤖 IA" if has_ia else ""}</div>
    <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3">
      {cards_html}
    </div>
  </section>

  {removidos_html}

  <!-- Metodologia -->
  <section class="mb-4">
    <div class="section-title">Metodologia</div>
    <div class="card">
      <div class="card-body text-secondary" style="font-size:.85rem;line-height:1.7">
        <div class="row g-3">
          <div class="col-md-6">
            <strong class="text-light">Filtros aplicados:</strong><br>
            P/VP &lt; 0.90 — cota negociada abaixo do valor patrimonial.<br>
            Fundo com &gt; 1 ano de histórico de preços na B3.<br>
            Liquidez diária ≥ R$ 100 mil.
          </div>
          <div class="col-md-6">
            <strong class="text-light">Remoção de anomalias (IQR):</strong><br>
            Dividendos mensais com valor acima de Q3 + 1,5×IQR são removidos.
            Esse método detecta pagamentos extraordinários (venda de ativo, amortização pontual, JCP especial).<br>
            <strong class="text-light">DY Limpo</strong> = média mensal sem outliers × 12 / preço.
            {"<br><strong class='text-light'>Fonte P/VP e DY:</strong> CSV StatusInvest (dados mais confiáveis para FIIs com pouca cobertura no yfinance)." if use_csv else ""}
          </div>
        </div>
      </div>
    </div>
  </section>

</div>

<footer>FII / FIAgro Screener · {now} · Não é recomendação de investimento.</footer>

<script>
const tickers  = {tickers_js};
const dyLimpo  = {dy_limpo_js};
const dyBruto  = {dy_bruto_js};
const pvpVals  = {pvp_js};
const tipoCols = {tipo_colors_js};

const palette = ['#3fb950','#58a6ff','#d29922','#f85149','#bc8cff',
                 '#39d353','#79c0ff','#e3b341','#ffa198','#d2a8ff'];

new Chart(document.getElementById('chartDY'), {{
  type: 'bar',
  data: {{
    labels: tickers,
    datasets: [
      {{ label: 'DY Limpo (%)',  data: dyLimpo, backgroundColor: palette, borderRadius: 4 }},
      {{ label: 'DY Bruto (%)',  data: dyBruto, backgroundColor: palette.map(c => c + '55'), borderRadius: 4 }}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }},
      tooltip: {{ callbacks: {{ label: c => ` ${{c.dataset.label}}: ${{c.parsed.y.toFixed(2)}}%` }} }}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }},
      y: {{ ticks: {{ color: '#8b949e', callback: v => v + '%' }}, grid: {{ color: '#30363d' }} }}
    }}
  }}
}});

new Chart(document.getElementById('chartPVP'), {{
  type: 'bar',
  data: {{
    labels: tickers,
    datasets: [{{ label: 'P/VP', data: pvpVals, backgroundColor: tipoCols, borderRadius: 4 }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: c => ` P/VP: ${{c.parsed.y.toFixed(3)}}` }} }},
      annotation: {{}}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }},
      y: {{
        min: 0, max: 1,
        ticks: {{ color: '#8b949e' }},
        grid: {{ color: '#30363d' }}
      }}
    }}
  }}
}});
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[fii_report] HTML gerado: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gera relatório HTML FII com análise IA opcional")
    parser.add_argument("--analysis-file", type=str, help="JSON de análises IA (output/fii_analyses.json)")
    args = parser.parse_args()

    ROOT         = Path(__file__).parent.parent
    candidates_p = ROOT / "output" / "fii_candidates.json"

    if not candidates_p.exists():
        print(f"[fii_report] Erro: {candidates_p} não encontrado. Execute fii_main.py primeiro.")
        sys.exit(1)

    with open(candidates_p, encoding="utf-8") as f:
        data = json.load(f)

    analyses: dict = {}
    if args.analysis_file:
        ap = Path(args.analysis_file)
        if ap.exists():
            with open(ap, encoding="utf-8") as f:
                analyses = json.load(f)
            print(f"[fii_report] Análises IA carregadas: {len(analyses)} fundos")
        else:
            print(f"[fii_report] Aviso: {args.analysis_file} não encontrado — gerando sem IA")

    output_html = ROOT / "output" / "fii_relatorio.html"
    generate_html(data["top10"], data["meta"], str(output_html), analyses=analyses or None)
