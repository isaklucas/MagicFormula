# Magic Formula BR — Backtest Histórico

Simula o portfolio Magic Formula mês a mês, calcula retorno acumulado vs IBOV e gera relatório HTML interativo.

**Aviso:** survivorship bias presente — universo fixo no CSV atual. Retornos são otimistas vs realidade.

---

## Passo 1 — Exportar universo de tickers

```bash
cd D:\Diana\MagicFormula && python src/export_tickers.py
```

Gera `output/universe_tickers.json` com todas as empresas elegíveis do CSV.

---

## Passo 2 — Rodar backtest

```bash
cd D:\Diana\MagicFormula && python src/backtester.py --tickers output/universe_tickers.json --start 2023-01-01 --top 15
```

Parâmetros ajustáveis:
- `--start`: data de início (padrão: 2023-01-01, máx histórico yfinance ~3 anos)
- `--top`: tamanho do portfolio (padrão: 15)

O backtest usa cache em `output/backtest_cache/` — segunda execução é muito mais rápida.

Salva resultado em `output/backtest.json`.

---

## Passo 3 — Gerar relatório HTML

```bash
cd D:\Diana\MagicFormula && python src/report_backtest.py --json output/backtest.json
```

---

## Passo 4 — Abrir no browser

```bash
start D:\Diana\MagicFormula\output\relatorio_backtest.html
```

---

## Passo 5 — Resumo no terminal

Após gerar o HTML, apresente:

```
BACKTEST MAGIC FORMULA BR
Período: [start] → [hoje] | [N] meses

Retorno Magic Formula:  +XX.X%
Retorno IBOV:           +XX.X%
Alpha:                  +XX.X%
Max Drawdown:           -XX.X%
Meses positivos/negativos: X / X
Sharpe simples:         X.XX

Top 3 meses:
  [YYYY-MM]: +X.X% (entrou: X, saiu: X)
  ...

Piores 3 meses:
  [YYYY-MM]: -X.X%
  ...

Empresas que mais apareceram no top 15:
  1. TICKER — X meses (XX%)
  2. ...

Relatório: D:\Diana\MagicFormula\output\relatorio_backtest.html
```

Além do resumo, analise os padrões: quais setores dominaram, qual foi o turnover médio mensal (entradas+saídas), se alpha foi consistente ou concentrado em poucos meses.
