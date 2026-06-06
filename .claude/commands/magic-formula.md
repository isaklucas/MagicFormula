# Magic Formula BR — Multi-Agent Analysis

Pipeline: Python quantitativo → agentes paralelos por ticker → EVAL anti-alucinação → guardrail RJ → HTML consolidado.

---

## Passo 1 — Executar pipeline Python

```bash
cd D:\Diana\MagicFormula && python src/main.py
```

Aguarda finalizar. Salva `output/candidates.json` com candidatos + resultado do guardrail RJ por ticker.

---

## Passo 2 — Ler candidatos

Leia `output/candidates.json`. Extraia os primeiros 30 da lista `candidatos`.

---

## Passo 3 — Disparar agentes de análise em paralelo (um por ticker)

Para cada ticker nos 30 candidatos, dispare **um Agent em paralelo** (subagent_type: "claude").
Todos disparados **em uma única mensagem** (bloco simultâneo de tool calls).

**PROMPT DO AGENTE** (substitua os valores reais de cada empresa — use o campo `contexto_agente` do JSON para tendências trimestrais):

```
Você é analista sênior de ações brasileiras.
Analise {TICKER} com base EXCLUSIVAMENTE nos dados abaixo. NÃO invente nada. NÃO use conhecimento externo.

DADOS:
- EV/EBIT: {ev_ebit}x
- ROIC: {roic}%
- Score MF: {mf_score}
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
{
  "ticker": "{TICKER}",
  "recomendacao": "COMPRAR" | "NEUTRO" | "CAUTELA",
  "score_compra": <1-10>,
  "motivo": "<1-2 frases objetivas baseadas apenas nos dados, máx 160 chars>"
}
```

---

## Passo 4 — EVAL anti-alucinação (após todos os agentes retornarem)

Colete todos os JSONs dos agentes em um dict `analyses` com formato `{"TICKER": {json do agente}, ...}`.

Salve em arquivo:
```bash
cd D:\Diana\MagicFormula && python -c "
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
analyses = <COLE_AQUI_O_DICT_PYTHON_DE_ANALISES>
with open('output/analyses.json', 'w', encoding='utf-8') as f:
    json.dump(analyses, f, ensure_ascii=False)
print('Salvo output/analyses.json')
"
```

Rode o validador:
```bash
cd D:\Diana\MagicFormula && python -c "
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'src')
from eval import validate_all, print_eval_report

with open('output/candidates.json', encoding='utf-8') as f:
    data = json.load(f)
with open('output/analyses.json', encoding='utf-8') as f:
    analyses = json.load(f)

results = validate_all(analyses, data['candidatos'])
invalidas = print_eval_report(results)
sys.exit(invalidas)
"
```

**Se exit code > 0 (inconsistências):**
- Para cada ticker com falha: ajuste `score_compra`, `recomendacao` ou `motivo` para ficarem coerentes com os dados
- Salve novamente e rode o EVAL até passar (máximo 2 iterações)

**Apenas AVISOs (não inconsistências) são aceitos** — registram no HTML mas não bloqueiam.

---

## Passo 5 — Selecionar top 15

Com análises validadas:
1. Ordene os 30 candidatos por `score_compra` (desc)
2. Máximo 3 empresas por setor (use o campo `setor` do candidates.json)
3. Selecione os 15 com maior score respeitando diversificação

---

## Passo 6 — Gerar relatório HTML

O arquivo `output/analyses.json` já foi salvo no Passo 4. Use-o diretamente:

```bash
cd D:\Diana\MagicFormula && python src/report.py --json output/candidates.json --analysis-file output/analyses.json --top 15
```

Abra no browser:
```bash
start D:\Diana\MagicFormula\output\relatorio.html
```

---

## Passo 7 — Resumo final no terminal

```
TOP 15 MAGIC FORMULA BR — [data]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 #  | Ticker | EV/EBIT | ROIC  | Score IA | Rec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1  | WIZC3  |  2.04x  | 23.5% |   9/10   | COMPRAR
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Relatório: D:\Diana\MagicFormula\output\relatorio.html
Clique no ticker no relatório para ver detalhes + abrir StatusInvest.
```

2-3 linhas de observação geral: diversificação setorial, perfil de risco, destaques.

---

## Passo 8 — Deploy GitHub Pages

Copia o relatório para `docs/index.html` e faz push:

```bash
cd D:\Diana\MagicFormula && copy /Y output\relatorio.html docs\index.html
```

```bash
cd D:\Diana\MagicFormula && git add docs/index.html && git commit -m "Magic Formula BR — $(Get-Date -Format 'yyyy-MM-dd')" && git push origin master
```

Após o push, o site atualiza em ~1 minuto em: https://isaklucas.github.io/MagicFormula/
