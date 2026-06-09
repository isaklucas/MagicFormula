# Magic Formula BR — Multi-Agent Analysis

Pipeline: Python quantitativo → agentes paralelos por ticker → EVAL anti-alucinação → guardrail RJ → HTML consolidado.

## ⚠️ Regra de Isolamento — NUNCA VIOLAR

- Este skill committa **APENAS** `docs/index.html`
- **NUNCA** rode pipelines de outras skills (US, FII, Backtest) para atualizar navbar ou qualquer outra razão
- **Se navbar.py mudou:** rode `python src/patch_navbar.py` para atualizar todos os HTMLs cirurgicamente — sem regenerar dados
- **Antes de commitar:** verifique que `docs/index.html` contém `Analisadas: N` com N > 0. Se N = 0, o relatório está vazio — **NÃO commite**

---

## Passo 1 — Executar pipeline Python

```bash
python src/main.py
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
Você é analista sênior de ações brasileiras, especializado em value investing e Magic Formula.
Analise {TICKER} com base EXCLUSIVAMENTE nos dados abaixo. NÃO invente nada. NÃO use conhecimento externo.

REGRAS OBRIGATÓRIAS:
1. CAGR Lucros negativo → mencione apenas estabilidade ou contração de lucros (NÃO mencione crescimento)
2. Dív/EBIT > 1 → NÃO diga "dívida baixa" ou "caixa líquido"
3. Dív/EBIT < 0 → PODE mencionar caixa líquido
4. Margem EBIT < 10% → NÃO classifique como "margem alta"
5. ROIC < 10% → score_compra máximo 7
6. EV/EBIT > 15x com ROIC < 25% → NÃO recomende COMPRAR

Calibração de score:
- 9-10: EV/EBIT < 8x E ROIC > 25% E Dív/EBIT < 0.5x
- 7-8:  fundamentals sólidos, risco controlado
- 5-6:  dados mistos ou incerteza relevante
- 1-4:  múltiplo caro OU dívida alta (>3x) OU ROIC < 10%

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

BUSCA WEB (obrigatória — máx 2 buscas):
Para validar os pontos que você identificou, faça buscas direcionadas:
- Se bull_case menciona "expansão de margens" → busque "{TICKER} margem resultado recente"
- Se bear_case menciona "alavancagem crescente" → busque "{TICKER} dívida último balanço"
- Use termos como "último balanço", "resultado recente", "últimos resultados" — SEM ano fixo
Use os achados para confirmar/corrigir pontos e preencher web_resumo.
Se busca não retornar nada útil: web_resumo = "Sem dados web relevantes."
NÃO invente fatos não presentes na busca.

Antes de gerar o JSON: identifique qual é o maior ponto forte e o maior risco deste ticker. Eles devem ser bull_case[0] e bear_case[0].

Retorne EXATAMENTE este JSON (sem markdown, sem texto fora):
{
  "ticker": "{TICKER}",
  "recomendacao": "COMPRAR" | "NEUTRO" | "CAUTELA",
  "score_compra": <1-10>,
  "motivo": "<resumo executivo, máx 160 chars>",
  "bull_case": ["<ponto forte 1>", "<ponto forte 2>", "<ponto forte 3 — entre 2 e 3 itens, mínimo 2>"],
  "bear_case": ["<ponto fraco 1>", "<ponto fraco 2>", "<ponto fraco 3 — entre 2 e 3 itens, mínimo 2>"],
  "web_resumo": "<1-2 frases do que a busca web confirmou ou adicionou. Se sem resultado: 'Sem dados web relevantes.'>"
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
start output\relatorio.html
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
Relatório: output\relatorio.html
Clique no ticker no relatório para ver detalhes + abrir StatusInvest.
```

2-3 linhas de observação geral: diversificação setorial, perfil de risco, destaques.

---

## Passo 8 — Deploy GitHub Pages

Copia o relatório para `docs/index.html` e faz push:

```bash
cd D:\Diana\MagicFormula && copy /Y output\relatorio.html docs\index.html
```

**Se navbar.py foi alterado nesta sessão** (novo link, renome), atualize todos os outros relatórios sem regenerar dados:
```bash
cd D:\Diana\MagicFormula && python src/patch_navbar.py
```

Commit — **apenas os arquivos listados abaixo**, nada mais:
```bash
cd D:\Diana\MagicFormula && git add docs/index.html && git commit -m "Magic Formula BR — $(Get-Date -Format 'yyyy-MM-dd')" && git push origin master
```

Se patch_navbar.py foi rodado, inclua também os demais HTMLs de docs/ que foram modificados (apenas navbar, sem regenerar):
```bash
git add docs/ src/navbar.py src/patch_navbar.py
```

Após o push, o site atualiza em ~1 minuto no seu GitHub Pages.
