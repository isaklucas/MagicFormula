---
description: Carteira — analisa minhas posições (export StatusInvest) vs screeners e decide MANTER / REFORÇAR / VENDER / TROCAR. Use quando o usuário falar em analisar/revisar a carteira, "minhas ações", "o que vender", "devo trocar X".
---

# Carteira — Análise das Minhas Posições vs Screeners

Pipeline: export StatusInvest → fundamentos atuais por ativo → alternativas de troca (screeners BR + FII) → agentes IA paralelos (MANTER / REFORÇAR / VENDER / TROCAR) → EVAL anti-alucinação → HTML local.

Se o usuário falar em **aporte, investir mais ou colocar dinheiro**, use `/aporte`. Ele chama este fluxo automaticamente quando a carteira está desatualizada.

**Antes do Passo 1:** pergunte se o usuário exportou a carteira atualizada do StatusInvest depois da última movimentação (StatusInvest → Carteira → Patrimônio → Exportar). O pipeline pega o export mais recente da pasta Downloads.

## ⚠️ Regra de Privacidade — NUNCA VIOLAR

- Este skill **NÃO commita nada** e **NÃO publica** no GitHub Pages (é público)
- Carteira fica só em `data/carteira*.xlsx` (gitignored) ou `~/Downloads`, e o relatório em `output/carteira.html` (gitignored)
- **NUNCA** copie `carteira.html` para `docs/` nem adicione link no `navbar.py`
- **NUNCA** rode pipelines de outras skills para "atualizar" o screener. Se `output/candidates.json` / `output/fii_candidates.json` estiverem velhos, avise o usuário e sugira `/magic-formula` e `/fii-analysis` antes

---

## ⚠️ Regra de Venda — barreira alta

Vender realiza o resultado e é irreversível. O padrão é **MANTER**: na dúvida, mantém. VENDER/TROCAR exige `embasamento` com:
- **Tese quebrada:** deterioração estrutural concreta. "Preço caiu", "fora do screener" ou "outro ativo tem score maior" não contam.
- **Evidências:** pelo menos 2 fatos verificáveis, com fonte.
- **Comparação com o destino (TROCAR):** o destino precisa ser superior em 2 de 3 dimensões (múltiplo, qualidade, risco).
- **Convicção:** score_conviccao ≤ 4.

Se a posição está no prejuízo, o contexto mostra a perda em R$, o quanto o ativo precisa subir para voltar ao preço médio e a regra de compensação de IR. O EVAL bloqueia a troca se faltar qualquer item. MANTER/REFORÇAR deve trazer `gatilho_venda` (o que faria vender).

---

## Dados de entrada

StatusInvest → Carteira → Patrimônio → Exportar (xlsx). O arquivo tem uma aba por classe: **Ações, FIIs, ETF, FIAGRO**.

O pipeline procura, nesta ordem:
1. `--file <caminho>`
2. `data/carteira.xlsx`
3. Export mais recente em `~/Downloads/carteira-patrimonio-export*.xlsx`

ETFs entram só na alocação, sem análise de troca.

---

## Passo 1 — Coletar dados

```bash
cd D:\Diana\MagicFormula && python src/carteira_main.py
```

Saída: `output/carteira_candidates.json`, com uma entrada por ação/FII/FIAgro. Cada entrada traz:
- a posição (PM, quantidade, resultado, peso)
- os fundamentos atuais (yfinance para ações; Fundamentus + DY limpo para FIIs)
- o status no screener
- até 5 **alternativas de troca**: ativos COMPRAR no último screener, fora da carteira, com o mesmo setor/segmento primeiro

Confira a data do screener no resumo. Se for de mais de 7 dias atrás, avise o usuário.

---

## Passo 2 — Gerar prompts

```bash
cd D:\Diana\MagicFormula && python src/carteira_prompts.py
```

Cria `output/carteira_prompts/<TICKER>.txt` e limpa `output/carteira_out/`.

---

## Passo 3 — Agentes em paralelo (um por ativo)

Dispare **um Agent por ticker** (subagent_type: "claude"), todos em uma única mensagem. O limite é de 20 simultâneos; se houver mais ativos, dispare o resto conforme os primeiros terminarem.

Prompt de cada agente:
```
Leia D:\Diana\MagicFormula\output\carteira_prompts\{TICKER}.txt e siga EXATAMENTE as instruções (análise + busca web). Grave apenas o JSON válido (UTF-8) em D:\Diana\MagicFormula\output\carteira_out\{TICKER}.json com a ferramenta Write. Responda só "OK {TICKER} <recomendacao> <score> <troca_por ou ->".
```

---

## Passo 4 — EVAL anti-alucinação

```bash
cd D:\Diana\MagicFormula && python src/carteira_eval.py
```

O comando junta `output/carteira_out/*.json` em `output/carteira_analyses.json` e valida:
- a recomendação é válida
- TROCAR tem `troca_por` com tickers da lista de alternativas
- VENDER/TROCAR têm riscos
- a convicção é coerente com a recomendação
- as regras de margem/dívida/DY são respeitadas

**Exit > 0:** corrija o JSON do ticker em `output/carteira_out/` e rode de novo (no máximo 2 iterações). AVISOs não bloqueiam.

---

## Passo 4b — Alocador de carteira (concentração)

```bash
cd D:\Diana\MagicFormula && python src/carteira_alocacao.py
```

Os agentes decidem cada ativo isoladamente. Sem esse passo, todos tendem a escolher o mesmo destino, o de maior score. O alocador resolve as trocas para a carteira inteira:
- **1 troca por destino:** cada destino recebe no máximo uma troca.
- **Peso por ativo:** o peso final de cada destino fica em até 5% do patrimônio.
- **Peso por setor:** cada setor fica em até 30% das ações; cada segmento, em até 40% dos FIIs.
- **Divisão:** uma posição maior que o limite por ativo é dividida entre até 3 destinos, com parcela mínima de 0,5% do patrimônio.
- **Ordem:** a troca mais urgente (menor convicção) escolhe primeiro. Se a 1ª opção estourar algum limite, o alocador tenta a 2ª e depois a 3ª. Nunca usa destino que o agente não justificou. Se nenhuma couber, o ativo fica em MANTER.

Saída: `output/carteira_alocacao.json`. O relatório usa esse plano como decisão final. Para mudar os limites, edite as constantes no topo de `src/carteira_alocacao.py`.

Para reprocessar só alguns ativos: `python src/carteira_prompts.py --only T1,T2` (não apaga os demais resultados).

---

## Passo 5 — Relatório local

```bash
cd D:\Diana\MagicFormula && python src/carteira_report.py && start output\carteira.html
```

---

## Passo 6 — Resumo no terminal

```
MINHA CARTEIRA — [data] — Patrimônio R$ X
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Ticker | Classe | Peso | Result. | Ação     | Conv. | Trocar por
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 XXXX3  | ACAO   | 2.0% | -10.0%  | TROCAR   | 3/10  | YYYY3
...
```

Depois da tabela, escreva 3-4 linhas de observação:
- alocação por classe e concentração
- quais VENDER/TROCAR priorizar
- se o screener usado está atualizado

Sempre feche com: "Não é recomendação de investimento."
