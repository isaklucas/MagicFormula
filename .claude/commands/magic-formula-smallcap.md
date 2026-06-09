# Magic Formula Small Cap US — S&P 600 Multi-Agent Analysis

Pipeline: yfinance S&P 600 → agentes paralelos por ticker → EVAL → HTML → GitHub Pages.

## ⚠️ Regra de Isolamento — NUNCA VIOLAR

- Este skill committa **APENAS** `docs/smallcap.html`
- **NUNCA** rode pipelines de outras skills (BR, US, FII, Backtest) para atualizar navbar ou qualquer outra razão
- **Se navbar.py mudou:** rode `python src/patch_navbar.py` para atualizar todos os HTMLs cirurgicamente — sem regenerar dados
- **Antes de commitar:** verifique que `docs/smallcap.html` contém `Analisadas: N` com N > 0. Se N = 0, o relatório está vazio — **NÃO commite**

---

## Passo 1 — Executar pipeline Python

```bash
python src/main_smallcap.py
```

Busca dados do S&P 600 via yfinance (cache diário em `output/`).
Primeira execução: ~10-15 min. Execuções seguintes do mesmo dia: ~30 seg.
Salva `output/candidates_smallcap.json`.

---

## Passo 2 — Ler candidatos

Leia `output/candidates_smallcap.json`. Extraia os primeiros 30 da lista `candidatos`.

---

## Passo 3 — Disparar agentes de análise em paralelo (um por ticker)

Para cada ticker nos 30 candidatos, dispare **um Agent em paralelo** (subagent_type: "claude").
Todos disparados **em uma única mensagem** (bloco simultâneo de tool calls).

**PROMPT DO AGENTE** (substitua os valores reais):

```
You are a senior equity analyst specializing in US small-cap stocks and value investing.
Analyze {TICKER} ({setor}) based EXCLUSIVELY on the data below. Do NOT invent anything. Do NOT use external knowledge.

MANDATORY RULES:
1. Negative Earnings CAGR → mention only earnings stability or contraction (do NOT mention growth)
2. Net Debt/EBIT > 1 → do NOT say "low debt" or "net cash"
3. Net Debt/EBIT < 0 → MAY mention net cash
4. EBIT Margin < 8% → do NOT classify as "high margin"
5. ROIC < 10% → score_compra maximum 7
6. EV/EBIT > 25x with ROIC < 20% → do NOT recommend COMPRAR
7. Small cap liquidity < $1M/day is acceptable — do NOT penalize for it

Score calibration:
- 9-10: EV/EBIT < 8x AND ROIC > 20% AND Net Debt/EBIT < 0.5x
- 7-8:  solid fundamentals, controlled risk
- 5-6:  mixed data or material uncertainty
- 1-4:  expensive multiple OR high debt (>3x) OR ROIC < 10%

DATA:
- EV/EBIT: {ev_ebit}x
- ROIC: {roic}%
- MF Score: {mf_score}
- EBIT Margin: {margem_ebit}%
- ROE: {roe}%
- Net Debt / EBIT: {div_ebit}x  (negative = net cash)
- Revenue CAGR 5y: {cagr_receitas}%
- Earnings CAGR 5y: {cagr_lucros}%
- Market Cap: ${valor_mercado}
- Avg Daily Liquidity: ${liquidez}
- Price: ${preco}
- Sector: {setor}
- Index: S&P 600 Small Cap

WEB SEARCH (required — max 2 searches):
To validate the points you identified, do targeted searches:
- If bull_case mentions "margin expansion" → search "{TICKER} margin latest earnings"
- If bear_case mentions "rising leverage" → search "{TICKER} debt latest filing"
- Use terms like "latest earnings", "recent results", "last quarter" — NO hardcoded year
Use findings to confirm/correct points and fill web_resumo.
If no useful results: web_resumo = "No relevant web data found."
Do NOT invent facts not present in the search.

Before generating the JSON: identify the single strongest bullish point and the single biggest risk. They should be bull_case[0] and bear_case[0].

Return EXACTLY this JSON (no markdown, no text outside):
{
  "ticker": "{TICKER}",
  "recomendacao": "COMPRAR" | "NEUTRO" | "CAUTELA",
  "score_compra": <1-10>,
  "motivo": "<executive summary, max 160 chars>",
  "bull_case": ["<strong point 1>", "<strong point 2>", "<strong point 3 — between 2 and 3 items, minimum 2>"],
  "bear_case": ["<weak point 1>", "<weak point 2>", "<weak point 3 — between 2 and 3 items, minimum 2>"],
  "web_resumo": "<1-2 sentences from web search findings. If no result: 'No relevant web data found.'>"
}
```

---

## Passo 4 — EVAL anti-alucinação (após todos os agentes retornarem)

Colete todos os JSONs dos agentes em um dict `analyses` com formato `{"TICKER": {json do agente}, ...}`.

Salve em arquivo:
```bash
python -c "
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
analyses = <COLE_AQUI_O_DICT_PYTHON_DE_ANALISES>
with open('output/analyses_smallcap.json', 'w', encoding='utf-8') as f:
    json.dump(analyses, f, ensure_ascii=False)
print('Salvo output/analyses_smallcap.json')
"
```

Rode o validador:
```bash
python -c "
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'src')
from eval import validate_all, print_eval_report

with open('output/candidates_smallcap.json', encoding='utf-8') as f:
    data = json.load(f)
with open('output/analyses_smallcap.json', encoding='utf-8') as f:
    analyses = json.load(f)

results = validate_all(analyses, data['candidatos'])
invalidas = print_eval_report(results)
sys.exit(invalidas)
"
```

**Se exit code > 0:** ajuste scores/recomendações inconsistentes e rode novamente (máx 2 iterações).

---

## Passo 5 — Selecionar top 20

Com análises validadas:
1. Ordene os 30 candidatos por `score_compra` (desc)
2. Máximo 3 empresas por setor (`setor` do candidates_smallcap.json)
3. Selecione os 20 com maior score respeitando diversificação

---

## Passo 6 — Gerar relatório HTML

```bash
python src/report_smallcap.py --json output/candidates_smallcap.json --analysis-file output/analyses_smallcap.json --top 20
```

Abra no browser:
```bash
start output\relatorio_smallcap.html
```

---

## Passo 7 — Resumo final no terminal

```
TOP 20 MAGIC FORMULA SMALL CAP US — [data]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 #  | Ticker | Setor        | EV/EBIT | ROIC  | Score IA | Rec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1  | SMPL   | Industrials  |  6.10x  | 31.2% |   9/10   | COMPRAR
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Relatório: output\relatorio_smallcap.html
```

2-3 linhas: setores dominantes, diferenças vs S&P 500 large caps, destaques small cap.

---

## Passo 8 — Deploy GitHub Pages

```bash
copy /Y output\relatorio_smallcap.html docs\smallcap.html
```

**Se navbar.py foi alterado nesta sessão**, atualize todos os outros relatórios sem regenerar dados:
```bash
python src/patch_navbar.py
```

Commit — **apenas os arquivos listados abaixo**, nada mais:
```bash
git add docs/smallcap.html && git commit -m "Magic Formula Small Cap US — $(Get-Date -Format 'yyyy-MM-dd')" && git push origin master
```

Se patch_navbar.py foi rodado, inclua também os demais HTMLs modificados:
```bash
git add docs/ src/navbar.py src/patch_navbar.py
```

Após o push, `docs/smallcap.html` fica disponível no GitHub Pages.
