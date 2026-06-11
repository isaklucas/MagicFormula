"""
Pipeline: FII / FIAgro — TOP 10 por DY Limpo

Passo 1 — Fundos via StatusInvest (cache mensal) ou CSV fallback
Passo 2 — P/VP direto dos dados SI (sem yfinance scan)
Passo 3 — Filtra P/VP < 0.90
Passo 4 — Enriquecimento yfinance (dividendos 24M + idade) só dos filtrados
Passo 5 — Filtro de idade > 1 ano
Passo 6 — DY Limpo (IQR) + fallback DY do SI para tickers sem histórico yfinance
Passo 7 — Rankeia TOP 10 por DY Limpo 12M
Passo 8 — Relatório HTML + fii_candidates.json (para skill IA)
"""

import io
import sys
import json
import argparse
import pandas as pd
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from fii_yf_fetcher  import fetch_all_fiis
from fii_si_scraper  import fetch_all_si, fetch_all_fiagro
from fii_loader      import load_fiis_fiagros
from fii_scraper     import fetch_all as scrape_funds_explorer, fetch_fiagros as fe_fetch_fiagros
from fii_enricher    import enrich_fiis
from fii_dy_cleaner  import clean_dy
from fii_ranking     import apply_age_filter, rank_by_dy_limpo, _MIN_LIQUIDEZ_FII, _TOP_N_FII, _TOP_N_FIAGRO
from fii_report      import generate_html

_PVP_LIMIT   = 0.90
_CSV_FIIS    = ROOT / "data" / "fiis.csv"
_CSV_FIAGROS = ROOT / "data" / "fiagros.csv"
OUTPUT_DIR   = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def _step(n: int, label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Passo {n} — {label}")
    print(f"{'='*60}")


def _nan_safe(v) -> bool:
    if v is None:
        return True
    try:
        import math
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _float_or_none(v):
    if _nan_safe(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _build_contexto_agente(r: dict) -> str:
    ticker   = r["TICKER"]
    nome     = r.get("NOME") or ticker
    seg      = r.get("SEGMENTO") or "—"
    tipo     = r.get("TIPO") or "FII"
    pvp      = r.get("PVP") or 0
    preco    = r.get("PRECO")
    vpa      = r.get("VPA")
    liq      = r.get("LIQUIDEZ")
    idade    = r.get("idade_dias", -1)
    ult_div  = r.get("ultimo_div")
    data_div = r.get("data_ultimo_div") or "—"
    dy_info  = r.get("dy_info") or {}
    dy_limpo = dy_info.get("dy_limpo_12m") or 0
    dy_bruto = dy_info.get("dy_bruto_12m") or 0
    n_remov  = dy_info.get("meses_removidos", 0)
    fonte_dy = dy_info.get("fonte", "yfinance 24M")

    desconto = (1 - pvp) * 100
    if idade > 0:
        idade_s = f"{idade // 365}a {(idade % 365) // 30}m"
    else:
        idade_s = "desconhecida"

    lines = [
        f"FUNDO: {ticker} — {nome}",
        f"SEGMENTO: {seg} | TIPO: {tipo}",
        "",
        "DADOS QUANTITATIVOS:",
        f"- P/VP: {pvp:.3f} ({desconto:.1f}% abaixo do valor patrimonial)",
        f"- DY Limpo 12M: {dy_limpo:.2f}%",
        f"- DY Bruto 12M: {dy_bruto:.2f}%",
    ]
    if n_remov > 0:
        lines.append(f"- Meses extraordinários removidos (IQR): {n_remov}")
    if ult_div:
        lines.append(f"- Último dividendo: R$ {ult_div:.4f} em {data_div}")
    lines.append(f"- Idade do fundo: {idade_s}")
    if preco:
        lines.append(f"- Preço atual: R$ {preco:.2f}")
    if vpa:
        lines.append(f"- VPA: R$ {vpa:.2f}")
    if liq:
        liq_s = f"R$ {liq/1e6:.1f}M" if liq >= 1e6 else f"R$ {liq/1e3:.0f}k"
        lines.append(f"- Liquidez diária: {liq_s}")
    lines.append(f"- Fonte DY: {fonte_dy}")
    return "\n".join(lines)


class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        import numpy as np
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, pd.Series):
            return obj.tolist()
        return super().default(obj)


def main() -> None:
    parser = argparse.ArgumentParser(description="FII/FIAgro screener — TOP 10 DY Limpo")
    parser.add_argument("--sem-ia",    action="store_true", help="Pula fii_candidates.json")
    parser.add_argument("--force-refresh", action="store_true", help="Ignora cache SI e re-scrapa")
    args   = parser.parse_args()
    com_ia = not args.sem_ia

    # ── Passo 1: Lista de fundos ───────────────────────────────────
    _step(1, "Buscando FIIs via yfinance (cache 7 dias) + SI fallback por ticker")
    fonte      = "yfinance"
    df_fiagros = pd.DataFrame()

    try:
        df_tickers = fetch_all_fiis(force=args.force_refresh)
    except Exception as e:
        print(f"[fii_main] fii_yf_fetcher falhou: {e} — tentando Fundamentus")
        fonte      = "Fundamentus"
        df_tickers = pd.DataFrame()
        try:
            df_fiis    = fetch_all_si(force=args.force_refresh)
            df_fiagros = fetch_all_fiagro(force=args.force_refresh)
            parts = [d for d in [df_fiis, df_fiagros] if not d.empty]
            df_tickers = pd.concat(parts, ignore_index=True).drop_duplicates("TICKER") if parts else pd.DataFrame()
        except Exception as e2:
            print(f"[fii_main] Fundamentus também falhou: {e2}")

    # Fallback: CSV manual
    if df_tickers.empty:
        if _CSV_FIIS.exists() or _CSV_FIAGROS.exists():
            print("[fii_main] Fallback → CSV StatusInvest (exportação manual)")
            fonte      = "CSV"
            df_tickers = load_fiis_fiagros(str(_CSV_FIIS), str(_CSV_FIAGROS))
        else:
            print("[fii_main] Fallback → Funds Explorer")
            fonte      = "FundsExplorer"
            df_tickers = scrape_funds_explorer()

    if df_tickers.empty:
        print("[fii_main] Sem dados de fundos. Abortando.")
        sys.exit(1)

    total_fundos = len(df_tickers)
    tickers_all  = df_tickers["TICKER"].tolist()
    ticker_meta  = df_tickers.set_index("TICKER").to_dict("index")
    print(f"[fii_main] {total_fundos} fundos carregados [{fonte}]")

    # ── Passo 2: P/VP dos dados SI (sem scan yfinance) ────────────
    _step(2, "P/VP direto da fonte (sem yfinance scan)")
    pvp_data: dict[str, dict] = {}
    for t, meta in ticker_meta.items():
        pvp_data[t] = {
            "pvp":   _float_or_none(meta.get("PVP")),
            "preco": _float_or_none(meta.get("PRECO")),
        }
    sem_pvp = sum(1 for v in pvp_data.values() if v["pvp"] is None)
    print(f"[fii_main] P/VP disponível: {total_fundos - sem_pvp}/{total_fundos}  |  sem dados: {sem_pvp}")

    # ── Passo 3: Filtro P/VP < 0.90 ───────────────────────────────
    _step(3, f"Filtrando P/VP < {_PVP_LIMIT}")
    tickers_pvp = [
        t for t in tickers_all
        if pvp_data.get(t, {}).get("pvp") is not None
        and pvp_data[t]["pvp"] < _PVP_LIMIT
    ]
    after_pvp = len(tickers_pvp)
    print(f"[fii_main] P/VP < {_PVP_LIMIT}: {total_fundos} → {after_pvp}  (sem P/VP: {sem_pvp})")

    removidos: list[dict] = []
    for t in tickers_all:
        pvp = pvp_data.get(t, {}).get("pvp")
        if pvp is None:
            removidos.append({"ticker": t, "etapa": "Sem dados P/VP", "motivo": "P/VP indisponível"})
        elif pvp >= _PVP_LIMIT:
            removidos.append({"ticker": t, "etapa": "Filtro P/VP", "motivo": f"P/VP {pvp:.3f} ≥ {_PVP_LIMIT}"})

    if not tickers_pvp:
        print("[fii_main] Nenhum fundo passou o filtro P/VP. Verifique conexão/dados.")
        sys.exit(1)

    # Filtro de liquidez: 1M para FIIs; FIAgros passam sem restrição
    before_liq = len(tickers_pvp)
    tickers_pvp = [
        t for t in tickers_pvp
        if ticker_meta.get(t, {}).get("TIPO") == "FIAgro"
        or ticker_meta.get(t, {}).get("LIQUIDEZ") is None
        or (ticker_meta.get(t, {}).get("LIQUIDEZ") or 0) >= _MIN_LIQUIDEZ_FII
    ]
    print(f"[fii_main] Liquidez ≥ R${_MIN_LIQUIDEZ_FII:,.0f} (FIIs): {before_liq} → {len(tickers_pvp)}")

    # ── Passo 4: Enriquecimento yfinance (dividendos + idade) ─────
    _step(4, f"Coletando dividendos de {after_pvp} fundos (yfinance)")
    enriched = enrich_fiis(tickers_pvp, delay=1.0)

    # Fundos sem histórico yfinance → assumir 1 ano (estão listados, portanto ativos)
    assumed = 0
    for t in tickers_pvp:
        if enriched.get(t, {}).get("idade_dias", -1) < 0:
            enriched.setdefault(t, {})["idade_dias"]  = 365
            enriched[t]["_age_assumed"] = True
            assumed += 1
    if assumed:
        print(f"[fii_main] {assumed} fundos sem histórico yfinance: idade assumida = 1 ano")

    # Monta records
    records = []
    for t in tickers_pvp:
        meta     = ticker_meta.get(t, {})
        pvp_info = pvp_data.get(t, {})
        yf_data  = enriched.get(t, {})
        preco    = yf_data.get("preco_yf") or pvp_info.get("preco")

        records.append({
            "TICKER":          t,
            "SEGMENTO":        meta.get("SEGMENTO", ""),
            "NOME":            meta.get("NOME", ""),
            "TIPO":            meta.get("TIPO", "FII"),
            "PVP":             pvp_info.get("pvp"),
            "PRECO":           preco,
            "preco_display":   preco,
            "VPA":             _float_or_none(meta.get("VPA")),
            "LIQUIDEZ":        _float_or_none(meta.get("LIQUIDEZ")),
            "idade_dias":      yf_data.get("idade_dias", -1),
            "ultimo_div":      yf_data.get("ultimo_div"),
            "data_ultimo_div": yf_data.get("data_ultimo_div"),
        })

    # ── Passo 5: Filtro de idade ───────────────────────────────────
    _step(5, "Filtrando fundos com < 1 ano de histórico")
    tickers_antes_idade = {r["TICKER"] for r in records}
    records = apply_age_filter(records, enriched)
    after_age = len(records)
    for t in tickers_antes_idade - {r["TICKER"] for r in records}:
        age    = enriched.get(t, {}).get("idade_dias", -1)
        motivo = f"{age} dias de histórico < 365 dias" if age > 0 else "Sem histórico de preços"
        removidos.append({"ticker": t, "etapa": "Filtro de Idade", "motivo": motivo})

    # ── Passo 6: DY Limpo (IQR) + fallback DY do SI ───────────────
    _step(6, "Calculando DY Limpo (IQR) + fallback DY StatusInvest")
    for r in records:
        price = r.get("PRECO")
        divs  = enriched.get(r["TICKER"], {}).get("dividendos_24m")
        r["dy_info"] = clean_dy(divs, price)

    # Mapa DY da fonte primária (yfinance info ou Fundamentus) para cross-validação e fallback
    si_dy_map: dict[str, float] = {}
    for t, meta in ticker_meta.items():
        for col in ("DY_12M_MED", "DY"):
            v = _float_or_none(meta.get(col))
            if v is not None and v > 0:
                si_dy_map[t] = v
                break

    # DY máximo plausível para FIIs (≈ 2× SELIC). Acima disso é quase certamente
    # amortização/venda de imóvel contaminando os dados — ambas as fontes.
    _MAX_DY_PLAUSIVEL = 30.0

    # Cross-validação: yfinance inclui amortizações/vendas de imóveis como
    # "dividendos", inflando DY artificialmente. Se yfinance DY limpo >
    # Fundamentus DY × 1.5 → substituir pelo Fundamentus (mais confiável).
    _CROSS_VAL_THRESHOLD = 1.5
    overridden = 0
    for r in records:
        dy_info = r.get("dy_info", {})
        if not dy_info.get("valido"):
            continue
        t = r["TICKER"]
        si_dy = si_dy_map.get(t)
        if si_dy is None or si_dy <= 0:
            continue
        yf_limpo = dy_info.get("dy_limpo_12m") or 0
        if yf_limpo > si_dy * _CROSS_VAL_THRESHOLD:
            print(f"[fii_main] {t}: DY yfinance {yf_limpo:.1f}% > {_CROSS_VAL_THRESHOLD}× Fundamentus {si_dy:.1f}% → amortização/venda de imóvel detectada, usando Fundamentus")
            r["dy_info"] = {
                "dy_bruto_12m":      round(si_dy, 2),
                "dy_limpo_12m":      round(si_dy, 2),
                "meses_com_dados":   0,
                "meses_removidos":   0,
                "valores_removidos": [],
                "valido":            True,
                "motivo_invalido":   "",
                "fonte":             "SI/yfinance info (yfinance history inflado por amortização)",
            }
            overridden += 1
    if overridden:
        print(f"[fii_main] {overridden} fundos com DY corrigido (amortização/venda detectada via cross-validação)")

    # Sanidade final: se DY Limpo ainda > MAX_DY_PLAUSIVEL E Fundamentus DY
    # também > MAX_DY_PLAUSIVEL → ambas as fontes contaminadas por amortização
    # → invalidar (fundo sai do ranking).
    contaminados = 0
    for r in records:
        dy_info = r.get("dy_info", {})
        if not dy_info.get("valido"):
            continue
        t = r["TICKER"]
        dy_limpo = dy_info.get("dy_limpo_12m") or 0
        si_dy    = si_dy_map.get(t) or 0
        if dy_limpo > _MAX_DY_PLAUSIVEL and si_dy > _MAX_DY_PLAUSIVEL:
            print(f"[fii_main] {t}: DY Limpo {dy_limpo:.1f}% e Fundamentus {si_dy:.1f}% ambos > {_MAX_DY_PLAUSIVEL}% → amortização contaminou todas as fontes → excluído")
            r["dy_info"] = {
                **dy_info,
                "valido":               False,
                "_amort_contaminado":   True,
                "motivo_invalido":      f"DY {dy_limpo:.1f}% implausível (amortização/venda de imóvel em ambas as fontes)",
            }
            contaminados += 1
    if contaminados:
        print(f"[fii_main] {contaminados} fundos excluídos por DY contaminado por amortização")

    # Fallback: fundos sem histórico yfinance → usa DY Fundamentus
    recovered = 0
    for r in records:
        if r.get("dy_info", {}).get("_amort_contaminado"):
            continue  # ambas as fontes contaminadas — não recuperar
        si_dy_fallback = si_dy_map.get(r["TICKER"], 0) or 0
        if si_dy_fallback > _MAX_DY_PLAUSIVEL:
            continue  # Fundamentus também inflado por amortização — não recuperar
        if not r.get("dy_info", {}).get("valido") and r["TICKER"] in si_dy_map:
            dy_val = si_dy_map[r["TICKER"]]
            r["dy_info"] = {
                "dy_bruto_12m":      round(dy_val, 2),
                "dy_limpo_12m":      round(dy_val, 2),
                "meses_com_dados":   0,
                "meses_removidos":   0,
                "valores_removidos": [],
                "valido":            True,
                "motivo_invalido":   "",
                "fonte":             "yfinance info",
            }
            recovered += 1
    if recovered:
        print(f"[fii_main] {recovered} fundos recuperados via DY da fonte primária (yfinance sem histórico)")

    validos   = [r for r in records if r.get("dy_info", {}).get("valido")]
    invalidos = [r for r in records if not r.get("dy_info", {}).get("valido")]
    for r in invalidos:
        motivo = r.get("dy_info", {}).get("motivo_invalido", "DY insuficiente")
        removidos.append({"ticker": r["TICKER"], "etapa": "DY Insuficiente", "motivo": motivo})
    print(f"[fii_main] Fundos com DY válido: {len(validos)}/{len(records)}")

    # ── Passo 7: TOP 20 FIIs + TOP 10 FIAgros ────────────────────
    _step(7, f"Rankeando TOP {_TOP_N_FII} FIIs + TOP {_TOP_N_FIAGRO} FIAgros por DY Limpo")
    fii_records    = [r for r in records if r.get("TIPO", "FII") != "FIAgro"]
    fiagro_records = [r for r in records if r.get("TIPO", "FII") == "FIAgro"]
    print(f"[fii_main] FIIs válidos: {len(fii_records)} | FIAgros válidos: {len(fiagro_records)}")
    top_fiis    = rank_by_dy_limpo(fii_records,    top_n=_TOP_N_FII)
    top_fiagros = rank_by_dy_limpo(fiagro_records, top_n=_TOP_N_FIAGRO)
    top10 = top_fiis + top_fiagros
    for i, r in enumerate(top10):
        r["posicao"] = i + 1

    # ── Passo 8: Relatório HTML ────────────────────────────────────
    _step(8, "Gerando relatório HTML + fii_candidates.json")
    meta_out = {
        "total_csv":   total_fundos,
        "apos_pvp":    after_pvp,
        "apos_idade":  after_age,
        "validos":     len(validos),
        "removidos":   removidos,
        "fonte_dados": fonte,
    }
    output_html = OUTPUT_DIR / "fii_relatorio.html"
    generate_html(top10, meta_out, str(output_html))

    if com_ia:
        for r in top10:
            r["contexto_agente"] = _build_contexto_agente(r)

        candidates_json = OUTPUT_DIR / "fii_candidates.json"
        data_out = {
            "data_execucao": str(date.today()),
            "total_fundos":  total_fundos,
            "fonte_dados":   fonte,
            "top10":         top10,
            "meta":          meta_out,
        }
        with open(candidates_json, "w", encoding="utf-8") as f:
            json.dump(data_out, f, ensure_ascii=False, indent=2, cls=_SafeEncoder)
        print(f"[fii_main] Candidatos IA: {candidates_json}")

    # ── Resumo terminal ────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  TOP {_TOP_N_FII} FIIs + TOP {_TOP_N_FIAGRO} FIAgros — DY Limpo — {date.today()}")
    print(f"{'='*70}")
    header = (
        f"{'#':>3}  {'Ticker':<8}  {'Tipo':<6}  {'Segmento':<18}  "
        f"{'P/VP':>5}  {'DY Bruto':>9}  {'DY Limpo':>9}  Fonte"
    )
    print(header)
    print("-" * len(header))
    for r in top10:
        dy_info = r.get("dy_info", {})
        pvp     = r.get("PVP") or 0
        seg     = (r.get("SEGMENTO") or "—")[:18]
        fonte_r = dy_info.get("fonte", "yfinance")
        remov   = dy_info.get("meses_removidos", 0)
        fonte_s = fonte_r + (f" (-{remov}m)" if remov > 0 else "")
        print(
            f"{r['posicao']:>3}  {r['TICKER']:<8}  {r.get('TIPO','FII'):<6}  "
            f"{seg:<18}  {pvp:>5.3f}  "
            f"{dy_info.get('dy_bruto_12m') or 0:>8.2f}%  "
            f"{dy_info.get('dy_limpo_12m') or 0:>8.2f}%  "
            f"{fonte_s}"
        )

    print(f"\n[fii_main] Relatório: {output_html}")
    if com_ia:
        print(f"[fii_main] Candidatos IA: {OUTPUT_DIR / 'fii_candidates.json'}")
    print("[fii_main] Abra o arquivo no navegador.\n")


if __name__ == "__main__":
    main()
