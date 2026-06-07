# Magic Formula BR

Sistema automatizado de seleção de ações brasileiras baseado na **Magic Formula de Joel Greenblatt**, com análise qualitativa por IA (Claude), backtest histórico e publicação automática via GitHub Pages.

---

## O que é

A Magic Formula ranqueia empresas combinando dois critérios:

- **EV/EBIT** — quão barata está a empresa (menor = melhor)
- **ROIC** — qualidade do negócio, retorno sobre capital investido (maior = melhor)

A soma dos dois rankings gera o **Magic Formula Score**. O sistema seleciona as **Top 15** empresas brasileiras elegíveis, analisa cada uma com IA e gera um relatório HTML interativo.

---

## Como funciona

```
CSV do StatusInvest
      ↓
Filtros de elegibilidade (liquidez, ROIC > 0, EV/EBIT > 0, dívida < 5x, sem RJ)
      ↓
Ranking Magic Formula (EV/EBIT + ROIC)
      ↓
Verificação de Recuperação Judicial (scraping StatusInvest)
      ↓
Limite de concentração setorial (máx 3 por setor)
      ↓
Enriquecimento histórico (yfinance: ROIC trimestral, margens, receita)
      ↓
Análise paralela por IA (30 agentes simultâneos, schema slim 4 campos)
      ↓
EVAL anti-alucinação (validação determinística: IA não pode inventar dados)
      ↓
Relatório HTML interativo (Top 15 com modal por ticker + link StatusInvest)
      ↓
Deploy GitHub Pages (docs/index.html)
```

---

## Como usar

### Pré-requisitos

- [Claude Code](https://claude.ai/code) instalado e autenticado
- Python 3.11+
- `pip install -r requirements.txt`

### Passo 1 — Exportar CSV do StatusInvest

1. Acesse [statusinvest.com.br/acoes](https://statusinvest.com.br/acoes) → Busca Avançada
2. Clique em **Exportar** (sem filtros — o sistema filtra internamente)
3. Salve como `statusinvest-busca-avancada.csv` na pasta `data/`

### Passo 2 — Rodar análise

Abra o Claude Code no diretório do projeto e execute:

```
/magic-formula
```

O sistema processa ~2-3 minutos e abre o relatório no browser.

### Backtest histórico

```
/magic-formula-backtest
```

Simula o portfólio mês a mês desde 2023 e gera relatório com retorno vs IBOV, alpha, drawdown e turnover.

---

## Estrutura do projeto

```
MagicFormula/
├── data/
│   └── statusinvest-busca-avancada.csv   # INPUT — exportar do StatusInvest
├── src/
│   ├── loader.py          # Leitura CSV + normalização BR
│   ├── filters.py         # Filtros de elegibilidade + dedup + setor
│   ├── ranking.py         # Algoritmo Magic Formula
│   ├── scraper.py         # Scraping StatusInvest (RJ + setor)
│   ├── enricher.py        # Dados históricos yfinance
│   ├── eval.py            # Validação anti-alucinação (determinística)
│   ├── main.py            # Pipeline principal → candidates.json
│   ├── report.py          # Gerador HTML relatório principal
│   ├── backtester.py      # Backtest histórico mensal
│   ├── report_backtest.py # Gerador HTML backtest
│   └── export_tickers.py  # Exporta universo para backtest
├── output/                # Gerado automaticamente (não commitar)
├── docs/
│   ├── index.html         # Relatório Magic Formula (GitHub Pages)
│   ├── backtest.html      # Relatório backtest (atualizado toda segunda via Actions)
│   ├── NEGOCIO.md         # Guia de uso e interpretação
│   └── TECNICO.md         # Documentação técnica da arquitetura
├── .claude/commands/
│   ├── magic-formula.md         # Skill Claude Code: pipeline completo
│   └── magic-formula-backtest.md # Skill Claude Code: backtest
├── .github/workflows/
│   └── backtest.yml       # GitHub Actions: backtest semanal automático (sem IA)
├── deploy.ps1             # Script de deploy manual para GitHub Pages
└── requirements.txt
```

---

## Proteções do sistema

| Proteção | O que faz |
|---------|----------|
| **Guardrail RJ** | 3 sinais independentes detectam Recuperação Judicial no StatusInvest |
| **EVAL anti-alucinação** | Validação determinística: IA não pode afirmar "dívida baixa" se Dív/EBIT > 1x, "margem alta" se Margem < 10%, etc. |
| **Limite de setor** | Máximo 3 empresas por setor B3 antes de rodar a IA (economiza tokens) |
| **Schema slim** | Agentes retornam apenas 4 campos JSON — ~80% menos tokens vs schema completo |

---

## Automação

| Tarefa | Como | Frequência |
|--------|------|-----------|
| Backtest | GitHub Actions (`backtest.yml`) | Toda segunda-feira 8h BRT |
| Magic Formula | Manual via `/magic-formula` | Quando quiser atualizar |
| Deploy | `deploy.ps1` ou Passo 8 da skill | Após cada análise |

---

## Aviso importante

> Este sistema é uma ferramenta de **suporte à decisão**, não uma recomendação de investimento. A Magic Formula tem survivorship bias no backtest (usa apenas empresas existentes hoje). Resultados passados não garantem retornos futuros. Faça sua própria análise antes de investir.

---

## Documentação completa

- [Guia de uso e interpretação](docs/NEGOCIO.md)
- [Documentação técnica](docs/TECNICO.md)
