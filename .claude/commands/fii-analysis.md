# FII / FIAgro — Screener DY Limpo + Análise IA

Pipeline: screener quantitativo → agentes IA paralelos por fundo → EVAL anti-alucinação → HTML consolidado.

## ⚠️ Regra de Isolamento — NUNCA VIOLAR

- Este skill committa **APENAS** `docs/fii.html`
- **NUNCA** rode pipelines de outras skills (BR, US, Backtest) para atualizar navbar ou qualquer outra razão
- **Se navbar.py mudou:** rode `python src/patch_navbar.py` para atualizar todos os HTMLs cirurgicamente — sem regenerar dados de outros reports

**Critérios:** P/VP < 0.90 · Fundo com > 1 ano · DY Limpo (IQR) · TOP 10 · Análise IA opcional

---

## Dados de entrada (CSV recomendado)

yfinance não tem dados de P/VP para muitos FIIs. Use CSV do StatusInvest:

1. Acesse `statusinvest.com.br/fundos-imobiliarios` → Busca Avançada → Exportar → salve como `data/fiis.csv`
2. Acesse `statusinvest.com.br/fundos-agro` → Busca Avançada → Exportar → salve como `data/fiagros.csv`

**Quando os CSVs existem em `data/`, o pipeline os usa automaticamente** (P/VP do CSV é mais confiável).
Sem CSVs → fallback automático para Funds Explorer + yfinance.

---

## Passo 1 — Executar pipeline Python

```powershell
cd D:\Diana\MagicFormula
python src/fii_main.py
```

Aguarda finalizar. Salva:
- `output/fii_relatorio.html` — relatório quantitativo
- `output/fii_candidates.json` — TOP 10 com dados completos para agentes IA

---

## Passo 2 — Ler candidatos

Leia `output/fii_candidates.json`. Extraia a lista `top10` — cada item tem o campo `contexto_agente` com todos os dados do fundo formatados para o agente.

---

## Passo 3 — Disparar agentes IA em paralelo (um por fundo)

Para cada fundo em `top10`, dispare **um Agent em paralelo** (subagent_type: "claude").
Todos disparados **em uma única mensagem** (bloco simultâneo de tool calls).

**PROMPT DO AGENTE** (substitua `{TICKER}` e `{contexto_agente}` pelos valores reais do JSON):

```
Você é analista especializado em Fundos de Investimento Imobiliário (FII) brasileiros.
Analise {TICKER} com base EXCLUSIVAMENTE nos dados abaixo. NÃO invente dados. NÃO use informações externas.

REGRAS OBRIGATÓRIAS — viola uma delas → análise INVÁLIDA:
1. DY Limpo < 6% → NÃO classifique como "DY alto" ou "dividendo alto"
2. DY Limpo < 8% → score_compra máximo 8
3. score_compra ≥ 9 exige DY Limpo ≥ 8% E P/VP ≤ 0.70
4. recomendacao=CAUTELA → campo "alertas" NÃO pode estar vazio
5. NÃO mencione informações ausentes dos dados acima

Calibração de score:
- 9-10: DY Limpo ≥ 8% E P/VP ≤ 0.70 E vacância controlada
- 7-8:  DY sólido, desconto razoável, risco identificado mas controlado
- 5-6:  dados mistos ou incerteza relevante no segmento
- 1-4:  DY baixo OU P/VP próximo de 1 OU risco estrutural elevado

TAREFAS:
1. Diagnostique a hipótese mais provável para o desconto P/VP atual
2. Avalie riscos operacionais com base no segmento e perfil quantitativo
3. Emita recomendação: COMPRAR (score 7-10) / NEUTRO (score 4-6) / CAUTELA (score 1-3)

{contexto_agente}

BUSCA WEB (obrigatória — máx 2 buscas):
Para validar os pontos que você identificou, faça buscas direcionadas:
- Se pontos_fortes menciona "vacância baixa" → busque "{TICKER} vacância resultado recente"
- Se alertas menciona "refinanciamento" ou "dívida" → busque "{TICKER} dívida último relatório"
- Use "último relatório", "resultado recente", "últimas cotas" — SEM ano fixo
Use os achados para confirmar/corrigir pontos e preencher web_resumo.
Se busca não retornar nada útil: web_resumo = "Sem dados web relevantes."
NÃO invente fatos não presentes na busca.

Antes de gerar o JSON: identifique qual é o maior ponto forte e o maior risco deste fundo. Eles devem ser pontos_fortes[0] e alertas[0].

Responda EXATAMENTE neste JSON (sem markdown, sem texto externo):
{
  "ticker": "{TICKER}",
  "recomendacao": "COMPRAR|NEUTRO|CAUTELA",
  "score_compra": <1-10>,
  "nivel_risco": "BAIXO|MEDIO|ALTO",
  "hipotese_desconto": "<1 frase objetiva — por que está descontado>",
  "motivo": "<1-2 frases, máx 160 chars>",
  "alertas": ["<risco 1>", "<risco 2>"],
  "pontos_fortes": ["<ponto 1>", "<ponto 2>"],
  "web_resumo": "<1-2 frases do que a busca web confirmou ou adicionou. Se sem resultado: 'Sem dados web relevantes.'>"
}
```

---

## Passo 4 — EVAL anti-alucinação

Colete todos os JSONs dos agentes em um dict `analyses` com formato `{"TICKER11": {json do agente}, ...}`.

Salve em arquivo:
```powershell
cd D:\Diana\MagicFormula
python -c "
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
analyses = <COLE_AQUI_O_DICT_PYTHON>
with open('output/fii_analyses.json', 'w', encoding='utf-8') as f:
    json.dump(analyses, f, ensure_ascii=False)
print('Salvo output/fii_analyses.json')
"
```

Rode o validador:
```powershell
cd D:\Diana\MagicFormula
python -c "
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, 'src')
from fii_eval import validate_all, print_eval_report

with open('output/fii_candidates.json', encoding='utf-8') as f:
    data = json.load(f)
with open('output/fii_analyses.json', encoding='utf-8') as f:
    analyses = json.load(f)

results = validate_all(analyses, data['top10'])
invalidas = print_eval_report(results)
sys.exit(invalidas)
"
```

**Se exit code > 0 (inconsistências):**
- Para cada ticker com falha: ajuste `score_compra`, `recomendacao`, `alertas` ou `motivo` para ficarem coerentes com os dados
- Salve novamente e rode o EVAL até passar (máximo 2 iterações)

**Apenas AVISOs (não inconsistências) são aceitos** — registrados no HTML mas não bloqueiam.

---

## Passo 5 — Gerar relatório HTML com IA

```powershell
cd D:\Diana\MagicFormula
python src/fii_report.py --analysis-file output/fii_analyses.json
```

Abre no navegador:
```powershell
start output\fii_relatorio.html
```

O relatório mostra nos cards de cada fundo:
- Recomendação: COMPRAR / NEUTRO / CAUTELA (badge colorido)
- Nível de risco: BAIXO / MÉDIO / ALTO
- Score IA: 1–10
- Hipótese para o desconto P/VP
- Alertas e pontos positivos

---

## Passo 6 — Resumo final no terminal

```
TOP 10 FIIs e FIAgros — DY Limpo — [data]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 #  | Ticker  | P/VP  | DY Limpo | Score IA | Rec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1  | MFII11  | 0.462 |  12.45%  |   8/10   | COMPRAR
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Relatório: output\fii_relatorio.html
```

2-3 linhas de observação geral: diversificação de segmentos, fundos com maior desconto vs maior DY, destaques.

---

## Flags do pipeline

| Flag | Efeito |
|------|--------|
| *(padrão)* | CSV se disponível, API se não; salva `fii_candidates.json` |
| `--sem-ia` | Pula geração de `fii_candidates.json` (mais rápido se não vai rodar IA) |

---

## Passo 7 — Deploy GitHub Pages

```powershell
cd D:\Diana\MagicFormula
copy /Y output\fii_relatorio.html docs\fii.html
```

**Se navbar.py foi alterado nesta sessão**, atualize todos os outros relatórios sem regenerar dados:
```powershell
python src/patch_navbar.py
```

Commit — **apenas os arquivos listados abaixo**, nada mais:
```powershell
git add docs/fii.html
git commit -m "FII screener: atualizacao $(Get-Date -Format 'yyyy-MM-dd')"
git push origin master
```

Se patch_navbar.py foi rodado, inclua também os demais HTMLs modificados:
```powershell
git add docs/ src/navbar.py src/patch_navbar.py
```

---

## Parâmetros de filtragem (padrão)

| Critério | Valor |
|----------|-------|
| P/VP máximo | < 0.90 |
| Liquidez mínima | R$ 100.000/dia |
| Idade mínima | 365 dias |
| Meses mínimos de dados DY | 8 de 12 |
| Método anomalia DY | IQR (Q3 + 1.5×IQR) |
| Fundos analisados pela IA | TOP 10 (todos que passaram o screener) |
