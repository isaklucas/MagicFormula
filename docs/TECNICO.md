# Documentação Técnica — Magic Formula BR

> Sistema de seleção quantitativa de ações brasileiras com análise qualitativa por IA.  
> Versão: 1.0 | Plataforma: Claude Code (Windows 10)

---

## Sumário

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Dependências](#2-dependências)
3. [Estrutura de Arquivos](#3-estrutura-de-arquivos)
4. [Módulos Python](#4-módulos-python)
5. [Skills Claude Code](#5-skills-claude-code)
6. [Pipeline de Execução](#6-pipeline-de-execução)
7. [Sistema de Cache](#7-sistema-de-cache)
8. [Guardrail de Recuperação Judicial](#8-guardrail-de-recuperação-judicial)
9. [EVAL Anti-Alucinação](#9-eval-anti-alucinação)
10. [Backtester](#10-backtester)
11. [Configurações e Parâmetros](#11-configurações-e-parâmetros)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Visão Geral da Arquitetura

```
INPUT: CSV StatusInvest (busca avançada)
       ↓
[loader.py]       Leitura e normalização de dados BR
       ↓
[filters.py]      Filtros quantitativos + deduplicação de tickers
       ↓
[ranking.py]      Algoritmo Magic Formula (rank EV/EBIT + rank ROIC)
       ↓
[scraper.py]      Scraping StatusInvest: RJ check + setor B3
  + [guardrail.py]  Dupla verificação de Recuperação Judicial
       ↓
[filters.py]      Limite de concentração setorial (max 3/setor)
       ↓
[enricher.py]     Dados históricos trimestrais via yfinance
       ↓
[main.py]         JSON intermediário → output/candidates.json
       ↓
SKILL /magic-formula (Claude Code)
  → Agentes paralelos (1 por ticker) — análise qualitativa
  → [eval.py] Validação determinística anti-alucinação
  → [report.py] Geração HTML
OUTPUT: output/relatorio.html
```

**Princípio central:** Python faz todo o trabalho pesado (dados, filtros, scraping, cache). Claude Code atua como IA de análise qualitativa — sem APIs externas, sem custos adicionais.

---

## 2. Dependências

### Python 3.13+

```
pandas>=2.0          # Processamento de dados tabulares
httpx>=0.27          # HTTP cliente async para scraping
beautifulsoup4>=4.12 # Parsing HTML do StatusInvest
rich>=13.0           # Output formatado no terminal
yfinance>=0.2.40     # Dados históricos de mercado (Yahoo Finance)
python-dateutil      # Manipulação de datas (backtest)
numpy                # Cálculos numéricos (backtest)
```

### Instalação

```powershell
cd D:\Diana\MagicFormula
pip install -r requirements.txt
```

### Ambiente

- **Claude Code**: CLI instalado e autenticado
- **Python**: disponível no PATH como `python`
- **Internet**: necessária para StatusInvest scraping e yfinance
- **Encoding**: `PYTHONIOENCODING=utf-8` (configurado em main.py via `sys.stdout`)

---

## 3. Estrutura de Arquivos

```
D:\Diana\MagicFormula\
│
├── data/
│   └── statusinvest-busca-avancada.csv   # INPUT — exportado do StatusInvest
│
├── src/
│   ├── loader.py          # Leitura CSV + normalização números BR
│   ├── filters.py         # Filtros quantitativos + dedup + limite setor
│   ├── ranking.py         # Algoritmo Magic Formula
│   ├── scraper.py         # StatusInvest scraping (RJ + setor)
│   ├── guardrail.py       # Dupla verificação RJ (3 sinais independentes)
│   ├── enricher.py        # Dados históricos yfinance
│   ├── eval.py            # Validação anti-alucinação (determinística)
│   ├── main.py            # Orquestrador principal → candidates.json
│   ├── report.py          # Gerador HTML do relatório principal
│   ├── backtester.py      # Backtest histórico Magic Formula
│   ├── report_backtest.py # Gerador HTML do relatório de backtest
│   └── export_tickers.py  # Utilitário: exporta universo para backtest
│
├── output/
│   ├── candidates.json        # Candidatos após pipeline
│   ├── relatorio.html         # Relatório principal (gerado pela skill)
│   ├── backtest.json          # Resultado do backtest
│   ├── relatorio_backtest.html # Relatório de backtest
│   └── backtest_cache/        # Cache de fundamentals yfinance (48h TTL)
│       └── {TICKER}.json
│
├── .claude/
│   └── commands/
│       ├── magic-formula.md         # Skill principal
│       └── magic-formula-backtest.md # Skill de backtest
│
├── docs/
│   ├── TECNICO.md    # Este arquivo
│   └── NEGOCIO.md    # Documentação para mesa de investimento
│
└── requirements.txt
```

---

## 4. Módulos Python

### `loader.py`

Lê o CSV do StatusInvest e normaliza para tipos Python.

**Entrada:** path do CSV  
**Saída:** `pd.DataFrame`

**Comportamento:**
- Separador: `;`
- Números BR: `1.234,56` → `1234.56` (remove ponto de milhar, troca vírgula por ponto)
- Colunas numéricas: todas exceto `TICKER`
- Valores vazios/inválidos: `NaN`

---

### `filters.py`

Aplica filtros de elegibilidade e deduplicação.

**Funções principais:**

`apply_filters(df)` — Filtros sequenciais:
1. Remove financeiros (bancos, seguradoras) — métricas incompatíveis com Magic Formula
2. Liquidez diária ≥ R$ 500.000 — mínimo para entrada/saída sem impacto
3. EV/EBIT > 0 — negativo indica prejuízo ou passivo > ativo
4. ROIC > 0 — empresa precisa ter retorno positivo sobre capital
5. Dívida Líquida / EBIT < 5 — endividamento extremo descartado

`deduplicate_by_company(df)` — Uma ação por empresa:
- Prioridade de sufixo: `11 (Units) > 4 (PN) > 3 (ON) > outros`
- Desempate: maior DY
- Base da empresa: 4 primeiros caracteres do ticker

`apply_sector_limit(records, setor_map, max_per_sector=3)` — Concentração setorial:
- Máximo 3 empresas por setor B3
- Preserva as de menor `mf_score` (melhores)
- Executa **antes** do yfinance para economizar requisições

---

### `ranking.py`

Implementa o algoritmo Magic Formula de Greenblatt.

```python
rank_ev_ebit = EV/EBIT.rank(ascending=True)   # menor = mais barato = melhor
rank_roic    = ROIC.rank(ascending=False)       # maior = melhor empresa
mf_score     = rank_ev_ebit + rank_roic         # menor score = melhor posição
```

**Saída:** `top_n` empresas ordenadas por `mf_score`, com colunas `rank_ev_ebit`, `rank_roic`, `mf_score`.

---

### `scraper.py` + `guardrail.py`

Scraping do StatusInvest para cada ticker.

**URL:** `https://statusinvest.com.br/acoes/{ticker_lower}`  
**Rate limit:** 1.2s entre requisições  
**Timeout:** 10s por request  
**Erro de rede:** assume `em_rj=False` (benefício da dúvida)

**Guardrail — 3 sinais independentes para RJ:**

| Sinal | Método | Peso |
|-------|--------|------|
| `BADGE_OFICIAL` | `<strong title="A empresa está em processo judicial">` | Sozinho basta |
| `TEXTO_RJ` | Padrões textuais na página | Precisa de 2+ sinais |
| `SEM_COTACAO` | Preço ausente ou zero | Precisa de 2+ sinais |

**Regra:** `em_rj = badge_oficial OR (n_sinais >= 2)`

**Extração de setor:** `<div class="fw-700">SETOR</div>` → `<small>` seguinte.  
Feita na **mesma requisição** do RJ check — zero custo extra.

---

### `enricher.py`

Enriquece candidatos com dados históricos do Yahoo Finance.

**Dados por ticker:**
- Setor e indústria (`info.sector`, `info.industry`)
- Beta
- Preço vs 52 semanas (máx, mín, posição percentual)
- ROIC trimestral (últimos 6 trimestres) — `EBIT × 4 / Invested Capital`
- Margem EBIT trimestral (últimos 6 trimestres)
- Receita trimestral em R$ milhões (últimos 6 trimestres)
- Tendência de cada série: `CRESCENTE | DECRESCENTE | VOLATIL | ESTAVEL | INSUFICIENTE`

**Output `format_for_agent()`:** texto formatado para incluir no prompt do agente.

```
DADOS HISTÓRICOS (WIZC3):
- Setor: Financial Services | Indústria: Insurance Brokers
- Beta: 0.52 (baixa volatilidade)
- Preço 52 semanas: Mín R$7.07 | Máx R$10.37 | Atual -26.7% vs máx / +7.5% vs mín
- ROIC trimestral (antigo→recente): 59.4% → 61.0% → 62.7% → 55.0% → 49.2% [VOLATIL]
- Margem EBIT trimestral: 42.0% → 37.9% → 40.7% → 37.5% → 40.7% [VOLATIL]
- Receita trimestral: R$351.7M → R$420.1M → R$416.1M → R$398.4M → R$318.4M [DECRESCENTE]
```

---

### `eval.py`

Validação determinística das análises dos agentes. Não usa IA — regras numéricas puras.

**12 regras de validação:**

| Regra | Inconsistência detectada |
|-------|--------------------------|
| Schema | `score_compra` fora de 1-10, `recomendacao` inválida |
| ROIC baixo + score alto | ROIC < 10% com score ≥ 9 |
| EV/EBIT alto + COMPRAR | EV/EBIT > 15x + ROIC < 25% + recomendação COMPRAR |
| Dívida alta sem ressalva | Dívida/EBIT > 4 com score > 7 sem risco de dívida mencionado |
| CAGR lucros negativo + score alto | CAGR < -10% com score ≥ 9 |
| Ponto forte vs dívida | Menciona "dívida baixa" com Dívida/EBIT > 1 |
| Ponto forte vs crescimento | Menciona "crescimento" com CAGR receitas negativo (aviso) |
| Ponto forte vs margem | Menciona "margem alta" com Margem EBIT < 10% |
| Valuation inconsistente | `MUITO_BARATO` com EV/EBIT > 8 (aviso) / `CARO` com EV/EBIT < 10 |
| ROIC qualidade inconsistente | `SUSTENTAVEL` com ROIC < 8% |

**Retorno:** `EvalResult(valido, inconsistencias, avisos)`  
**Inconsistências:** bloqueiam a análise (agente deve reanalisar)  
**Avisos:** registram no HTML mas não bloqueiam

---

### `main.py`

Orquestrador do pipeline. Aceita `--top N` (padrão: 30).

**Fluxo:**
1. `load_csv()` → DataFrame bruto
2. `apply_filters()` → filtros + dedup
3. `compute_magic_formula(top_n=30)` → ranking
4. `check_recuperacao_judicial()` → scraping + guardrail
5. Remove `em_rj=True`
6. `apply_sector_limit(max_per_sector=3)` → concentração setorial
7. `enrich_candidates()` → dados históricos yfinance
8. Salva `output/candidates.json`
9. Imprime JSON no stdout

---

### `report.py`

Gera `output/relatorio.html` a partir do JSON de candidatos + análises dos agentes.

**Parâmetros CLI:**
```
--json     path do candidates.json
--analysis JSON string com análises por ticker {"TICKER": {json_agente}}
--output   path do HTML de saída (default: output/relatorio.html)
--top      número de empresas a exibir (default: 15)
```

**Seções do HTML:**
- Header com estatísticas do pipeline
- Tabela resumo (EV/EBIT, ROIC, Score MF, Score IA, Recomendação, métricas)
- Gráfico de barras ROIC (Chart.js)
- Gráfico scatter EV/EBIT vs ROIC
- Cards detalhados por empresa (métricas + análise IA + pontos fortes/riscos)
- Seção de metodologia

---

## 5. Skills Claude Code

Skills são arquivos `.md` em `.claude/commands/`. Disparadas com `/nome-da-skill` na sessão.

### `/magic-formula`

**Arquivo:** `.claude/commands/magic-formula.md`

**Fluxo:**
1. `python src/main.py` → `output/candidates.json`
2. Lê candidatos — extrai top 20
3. Dispara **agentes paralelos** (1 por ticker) com prompt estruturado
4. Cada agente retorna JSON: `{score_compra, recomendacao, pontos_fortes, riscos, analise, qualidade_roic, valuation}`
5. `python src/eval.py` — valida todos os JSONs
6. Se falha: corrige e re-valida (máx 2 iterações)
7. Seleciona top 15 por `score_compra` + diversificação
8. `python src/report.py` → `output/relatorio.html`
9. Abre HTML no browser

**Agentes paralelos:**
- Todos disparados em um único bloco de tool calls
- Cada agente recebe: métricas do CSV + `contexto_agente` (dados históricos do enricher)
- Prompt instrui a **não inventar dados** — apenas raciocinar sobre o que foi fornecido

---

### `/magic-formula-backtest`

**Arquivo:** `.claude/commands/magic-formula-backtest.md`

**Fluxo:**
1. `python src/export_tickers.py` → `output/universe_tickers.json`
2. `python src/backtester.py --tickers ... --start 2023-01-01 --top 15`
3. `python src/report_backtest.py --json output/backtest.json`
4. Abre `output/relatorio_backtest.html`
5. Claude analisa padrões: turnover médio, setores dominantes, consistência do alpha

---

## 6. Pipeline de Execução

### Tempo estimado por etapa

| Etapa | Tempo (30 tickers) |
|-------|-------------------|
| Leitura CSV + filtros | < 1s |
| Ranking | < 1s |
| Scraping StatusInvest (30 tickers × 1.2s) | ~36s |
| Limite de setor | < 1s |
| yfinance enrichment (~20 tickers × 1.5s) | ~30s |
| Agentes paralelos (todos simultâneos) | ~30-60s |
| EVAL + report HTML | < 5s |
| **Total** | **~2-3 min** |

### Tempo estimado — Backtest (127 tickers, 3 anos)

| Etapa | Tempo |
|-------|-------|
| Download preços mensais (batch) | ~10s |
| Fundamentals yfinance (primeira vez, sem cache) | ~10-15 min |
| Fundamentals yfinance (com cache 48h) | ~1 min |
| Loop de ranking mensal | ~2-5 min |
| Geração HTML | < 5s |

---

## 7. Sistema de Cache

### Cache de fundamentals (backtest)

**Localização:** `output/backtest_cache/{TICKER}.json`  
**TTL:** 48 horas (baseado em `mtime` do arquivo)  
**Formato:** JSON com séries trimestrais de `ebit`, `inv_cap`, `net_debt`, `shares`

**Invalidação manual:**
```powershell
Remove-Item "D:\Diana\MagicFormula\output\backtest_cache\*.json"
```

---

## 8. Guardrail de Recuperação Judicial

**Objetivo:** evitar tanto falso positivo (excluir empresa boa) quanto falso negativo (incluir empresa em RJ).

**Sinal primário** (badge oficial StatusInvest):
```html
<strong title="A empresa está em processo judicial" class="main-badge ... red ...">
  RECUPERAÇÃO JUDICIAL
</strong>
```
→ Sozinho é suficiente para marcar `em_rj=True` com confiança ALTA.

**Sinal secundário** (padrões textuais):
- "recuperação judicial", "em processo judicial", "plano de recuperação", "credores aprovam", "assembleia de credores"
→ Exige 2+ sinais para confirmar.

**Sinal terciário** (preço ausente):
- Elemento de preço não encontrado ou valor ≤ 0
→ Exige 2+ sinais para confirmar.

**Regra final:**
```python
em_rj = badge_oficial OR (n_sinais_ativos >= 2)
```

**Tratamento de erro de rede:** `em_rj=False` com `confianca=BAIXA`. Empresa não é removida por falha técnica.

---

## 9. EVAL Anti-Alucinação

**Objetivo:** garantir que as análises dos agentes sejam factualmente consistentes com os dados quantitativos fornecidos. Executado em Python puro — sem custo de IA adicional.

**Quando falha:**
- `valido=False` → agente recebe feedback e reanalisa
- Máximo 2 tentativas por ticker
- Após 2 falhas: análise marcada como "Não validada" no HTML

**Avisos** (não bloqueiam):
- Ponto forte menciona crescimento com CAGR receitas negativo
- `MUITO_BARATO` com EV/EBIT > 8x

**Uso standalone:**
```python
from eval import validate_all, print_eval_report
results = validate_all(analyses_dict, candidates_list)
n_invalidas = print_eval_report(results)
```

---

## 10. Backtester

**Limitação crítica — Survivorship Bias:**
O universo é fixo no CSV atual. Empresas que faliram, foram para RJ ou saíram da B3 no período histórico não estão incluídas. O retorno real da estratégia foi **menor** do que o calculado.

**Reconstrução de EV/EBIT histórico:**
```
EV(t) = Market Cap(t) + Net Debt(trimestre mais próximo antes de t)
Market Cap(t) = Preço(t) × Shares Outstanding(trimestre mais próximo)
EV/EBIT(t) = EV(t) / (EBIT trimestral × 4)
```

**Rebalanceamento:** mensal, final do mês, equal-weight (1/N por ação).

**IBOV:** `^BVSP` via yfinance, renomeado para `IBOV` internamente.

**Sharpe simplificado:** `retorno_médio_mensal / volatilidade_mensal` (sem taxa livre de risco).

---

## 11. Configurações e Parâmetros

### Filtros ajustáveis (`filters.py`)

| Parâmetro | Valor atual | Descrição |
|-----------|-------------|-----------|
| Liquidez mínima | R$ 500.000 | `apply_filters()` linha 32 |
| Dívida/EBIT máxima | 5x | `apply_filters()` linha 40 |
| Max empresas por setor | 3 | `apply_sector_limit()` parâmetro |

### Ranking (`ranking.py`)

| Parâmetro | Valor atual | Descrição |
|-----------|-------------|-----------|
| Top N para ranking | 30 | `main.py --top` |
| Top N candidatos para agentes | 20 | skill `magic-formula.md` |
| Top N final | 15 | skill `magic-formula.md` |

### Scraper

| Parâmetro | Valor atual |
|-----------|-------------|
| Delay entre requests | 1.2s |
| Timeout por request | 10s |

### Backtest

| Parâmetro | Valor atual | Descrição |
|-----------|-------------|-----------|
| Data de início | 2023-01-01 | `--start` |
| Portfolio size | 15 | `--top` |
| Delay yfinance | 0.3s/ticker | |
| Cache TTL | 48h | |

---

## 12. Troubleshooting

### `UnicodeEncodeError` no terminal
**Causa:** Windows PowerShell com encoding cp1252.  
**Solução:** já tratado em `main.py` via `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")`. Para outros scripts: `$env:PYTHONIOENCODING="utf-8"`.

### StatusInvest retorna 403 / bloqueio
**Causa:** muitas requisições sem delay.  
**Solução:** aumentar `delay` em `scraper.py` para 2.0s.

### yfinance retorna DataFrame vazio
**Causa:** ticker não encontrado no Yahoo Finance (alguns small caps BR não têm cobertura).  
**Solução:** `enricher.py` trata silenciosamente — campo `erro_yfinance` no JSON. Empresa não é removida por falta de dados históricos.

### Backtest com muitos meses "top0"
**Causa:** dados trimestrais do yfinance têm delay de 1-2 trimestres. Primeiros meses do backtest não têm fundamentals disponíveis.  
**Solução:** iniciar backtest com `--start` pelo menos 6 meses após o início dos dados históricos desejados.

### Cache de fundamentals desatualizado
**Solução:**
```powershell
Remove-Item "D:\Diana\MagicFormula\output\backtest_cache\*.json"
```
