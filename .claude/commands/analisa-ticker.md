# Analisa Ticker — Avaliação Ad-hoc de Qualquer Ação B3

Avalia 1-5 tickers B3 sob demanda, sem necessidade de CSV do StatusInvest.
Pipeline: yfinance → enricher → agentes IA paralelos → EVAL → resumo.

**Uso:** `/analisa-ticker ITSA4` ou `/analisa-ticker MGLU3 PETR4 VALE3`

---

## Passo 1 — Buscar dados fundamentais

```bash
python src/analyze_ticker.py $ARGUMENTS
```

Aguarda finalizar. Salva `output/analyze_ticker_cache.json`.
Se ticker não encontrado no yfinance: avisar usuário e pular.

---

## Passo 2 — Ler candidatos

Leia `output/analyze_ticker_cache.json`. Extraia lista `candidatos`.

---

## Passo 3 — Disparar agentes em paralelo (um por ticker)

Para cada ticker, dispare **um Agent em paralelo** (subagent_type: "claude").
Todos em **uma única mensagem** (bloco simultâneo de tool calls).

**PROMPT DO AGENTE:**

```
Você é analista sênior de ações brasileiras.
Analise {TICKER} com base EXCLUSIVAMENTE nos dados abaixo. NÃO invente nada. NÃO use conhecimento externo.

DADOS:
- EV/EBIT: {ev_ebit}x
- ROIC: {roic}%
- Margem EBIT: {margem_ebit}%
- ROE: {roe}%
- Dívida Líq / EBIT: {div_ebit}x  (negativo = caixa líquido)
- CAGR Receitas 5a: {cagr_receitas}%
- CAGR Lucros 5a: {cagr_lucros}%
- Valor de Mercado: R$ {valor_mercado}
- Liquidez Diária: R$ {liquidez}
- Preço: R$ {preco}
- Setor: {setor}

{contexto_agente}

REGRAS:
1. CAGR Lucros negativo → NÃO mencione crescimento de lucros no motivo
2. Dív/EBIT > 1 → NÃO diga "dívida baixa" ou "caixa líquido"
3. Dív/EBIT < 0 → PODE mencionar caixa líquido
4. Margem EBIT < 10% → NÃO classifique como "margem alta"
5. ROIC < 10% → score_compra máximo 7
6. EV/EBIT > 15x com ROIC < 25% → NÃO recomende COMPRAR

Retorne EXATAMENTE este JSON (sem markdown, sem texto fora):
{"ticker":"{TICKER}","recomendacao":"COMPRAR"|"NEUTRO"|"CAUTELA","score_compra":<1-10>,"motivo":"<1-2 frases objetivas baseadas apenas nos dados, máx 160 chars>"}
```

---

## Passo 4 — EVAL anti-alucinação

Colete todos os JSONs em dict `analyses`.

```bash
cd D:\Diana\MagicFormula && python -c "
import json, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'src')
from eval import validate_all, print_eval_report

analyses = <COLE_AQUI>
with open('output/analyze_ticker_cache.json', encoding='utf-8') as f:
    data = json.load(f)

results = validate_all(analyses, data['candidatos'])
invalidas = print_eval_report(results)
sys.exit(invalidas)
"
```

Se exit > 0: corrigir inconsistências e revalidar (máx 1 iteração).

---

## Passo 5 — Resumo no terminal

```
ANÁLISE AD-HOC — {data}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Ticker | EV/EBIT | ROIC  | Score | Rec      | Motivo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ITSA4  |  7.84x  | 17.4% |  9/10 | COMPRAR  | ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

1-2 linhas de observação comparando os tickers analisados.

---

## Notas

- Dados vêm 100% do yfinance — podem diferir levemente do StatusInvest CSV
- EV/EBIT calculado via EBIT TTM (soma 4 últimos trimestres)
- ROIC = média dos últimos 4 trimestres anualizados
- CAGR 5a via demonstrativo anual (pode ser 4a se ticker não tem 5 anos de histórico)
- Sem deploy HTML — análise de terminal apenas
