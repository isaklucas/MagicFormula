# Magic Formula BR — Backtest Histórico

Simula o portfolio Magic Formula mês a mês, calcula retorno acumulado vs IBOV e gera relatório HTML interativo.

## ⚠️ Regra de Isolamento — NUNCA VIOLAR

- Este skill committa **APENAS** `docs/backtest.html`
- **NUNCA** rode pipelines de outras skills (BR, US, FII) para atualizar navbar ou qualquer outra razão
- **Se navbar.py mudou:** rode `python src/patch_navbar.py` para atualizar todos os HTMLs cirurgicamente — sem regenerar dados

**Aviso:** survivorship bias presente — universo fixo no CSV atual. Retornos são otimistas vs realidade.

---

## Passo 1 — Exportar universo de tickers

```bash
python src/export_tickers.py
```

Gera `output/universe_tickers.json` com todas as empresas elegíveis do CSV.

---

## Passo 2 — Rodar backtest

```bash
python src/backtester.py --tickers output/universe_tickers.json --start 2023-01-01 --top 15
```

Parâmetros ajustáveis:
- `--start`: data de início (padrão: 2023-01-01, máx histórico yfinance ~3 anos)
- `--top`: tamanho do portfolio (padrão: 15)

O backtest usa cache em `output/backtest_cache/` — segunda execução é muito mais rápida.

Salva resultado em `output/backtest.json`.

---

## Passo 3 — Gerar relatório HTML

```bash
python src/report_backtest.py --json output/backtest.json
```

---

## Passo 4 — Abrir no browser

```bash
start output\relatorio_backtest.html
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

Relatório: output\relatorio_backtest.html
```

Além do resumo, analise os padrões: quais setores dominaram, qual foi o turnover médio mensal (entradas+saídas), se alpha foi consistente ou concentrado em poucos meses.

---

## Passo 6 — Deploy GitHub Pages

```bash
copy /Y output\relatorio_backtest.html docs\backtest.html
```

**Se navbar.py foi alterado nesta sessão**, atualize todos os outros relatórios sem regenerar dados:
```bash
python src/patch_navbar.py
```

Commit — **apenas os arquivos listados abaixo**, nada mais:
```bash
git add docs/backtest.html && git commit -m "Backtest BR — $(Get-Date -Format 'yyyy-MM-dd')" && git push origin master
```

Se patch_navbar.py foi rodado, inclua também os demais HTMLs modificados:
```bash
git add docs/ src/navbar.py src/patch_navbar.py
```
