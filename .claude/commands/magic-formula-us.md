# Magic Formula US — S&P 500 Multi-Agent Analysis

Pipeline: yfinance S&P 500 → agentes paralelos por ticker → EVAL → HTML → GitHub Pages.

## ⚠️ Regra de Isolamento — NUNCA VIOLAR

- Este skill committa **APENAS** `docs/us.html`
- **NUNCA** rode pipelines de outras skills (BR, FII, Backtest) para atualizar navbar ou qualquer outra razão
- **Se navbar.py mudou:** rode `python src/patch_navbar.py` para atualizar todos os HTMLs cirurgicamente — sem regenerar dados
- **Antes de commitar:** verifique que `docs/us.html` contém `Analisadas: N` com N > 0. Se N = 0, o relatório está vazio — **NÃO commite**

---

## Passo 1 — Executar pipeline Python

```bash
python src/main_sp500.py
```

Busca dados do S&P 500 via yfinance (cache diário em `output/sp500_cache/`).
Primeira execução: ~10-15 min. Execuções seguintes do mesmo dia: ~30 seg.
Salva `output/candidates_sp500.json`.

---

## Passo 2 — Ler candidatos

Leia `output/candidates_sp500.json`. Extraia os primeiros 30 da lista `candidatos`.

---

## Passo 3 — Disparar agentes de análise em paralelo (um por ticker)

Para cada ticker nos 30 candidatos, dispare **um Agent em paralelo** (subagent_type: "claude").
Todos disparados **em uma única mensagem** (bloco simultâneo de tool calls).

**PROMPT DO AGENTE** (substitua os valores reais):

```
You are a senior equity analyst. Analyze {TICKER} ({setor}) based EXCLUSIVELY on the data below. Do NOT invent anything. Do NOT use external knowledge.

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

RULES:
1. Negative Earnings CAGR → do NOT mention earnings growth in the reason
2. Net Debt/EBIT > 1 → do NOT say "low debt" or "net cash"
3. Net Debt/EBIT < 0 → MAY mention net cash
4. EBIT Margin < 10% → do NOT classify as "high margin"
5. ROIC < 10% → score_compra maximum 7
6. EV/EBIT > 20x with ROIC < 30% → do NOT recommend COMPRAR

WEB SEARCH (required — max 2 searches):
To validate the points you identified, do targeted searches:
- If bull_case mentions "margin expansion" → search "{TICKER} margin latest earnings"
- If bear_case mentions "rising leverage" → search "{TICKER} debt latest filing"
- Use terms like "latest earnings", "recent results", "last quarter" — NO hardcoded year
Use findings to confirm/correct points and fill web_resumo.
If no useful results: web_resumo = "No relevant web data found."
Do NOT invent facts not present in the search.

Return EXACTLY this JSON (no markdown, no text outside):
{
  "ticker": "{TICKER}",
  "recomendacao": "COMPRAR" | "NEUTRO" | "CAUTELA",
  "score_compra": <1-10>,
  "motivo": "<executive summary, max 160 chars>",
  "bull_case": ["<strong point 1>", "<strong point 2>", "<strong point 3 optional>"],
  "bear_case": ["<weak point 1>", "<weak point 2>", "<weak point 3 optional>"],
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
with open('output/analyses_us.json', 'w', encoding='utf-8') as f:
    json.dump(analyses, f, ensure_ascii=False)
print('Salvo output/analyses_us.json')
"
```

Rode o validador:
```bash
python -c "
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'src')
from eval import validate_all, print_eval_report

with open('output/candidates_sp500.json', encoding='utf-8') as f:
    data = json.load(f)
with open('output/analyses_us.json', encoding='utf-8') as f:
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
2. Máximo 3 empresas por setor (`setor` do candidates_sp500.json)
3. Selecione os 20 com maior score respeitando diversificação

---

## Passo 6 — Gerar relatório HTML

```bash
python src/report_us.py --json output/candidates_sp500.json --analysis-file output/analyses_us.json --top 20
```

Abra no browser:
```bash
start output\relatorio_us.html
```

---

## Passo 7 — Resumo final no terminal

```
TOP 20 MAGIC FORMULA US — [data]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 #  | Ticker | Setor        | EV/EBIT | ROIC  | Score IA | Rec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1  | AAPL   | Technology   |  8.20x  | 45.2% |   9/10   | COMPRAR
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Relatório: output\relatorio_us.html
```

2-3 linhas de observação geral: setores dominantes, comparação com BR, destaques.

---

## Passo 8 — Deploy GitHub Pages

```bash
copy /Y output\relatorio_us.html docs\us.html
```

**Se navbar.py foi alterado nesta sessão** (novo link, renome), atualize todos os outros relatórios sem regenerar dados:
```bash
cd D:\Diana\MagicFormula && python src/patch_navbar.py
```

Commit — **apenas os arquivos listados abaixo**, nada mais:
```bash
git add docs/us.html && git commit -m "Magic Formula US — $(Get-Date -Format 'yyyy-MM-dd')" && git push origin master
```

Se patch_navbar.py foi rodado, inclua também os demais HTMLs de docs/ que foram modificados (apenas navbar, sem regenerar):
```bash
git add docs/ src/navbar.py src/patch_navbar.py
```

Após o push, `docs/us.html` fica disponível no GitHub Pages junto com BR e Backtest.
