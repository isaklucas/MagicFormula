---
description: Aporte — onde colocar dinheiro novo na carteira (ETF internacional / FIIs / Ações, ~1/3 cada). Use quando o usuário falar em aporte, aportar, investir mais, colocar dinheiro, "tenho X para investir", "onde coloco R$ X".
argument-hint: <valor em R$>
---

# Aporte — Onde Colocar Dinheiro Novo

Distribui um aporte entre **ETF internacional / FIIs+FIAgro / Ações**, mirando cerca de 1/3 em cada. Usa a análise da carteira (convicção e gatilhos) e os screeners para escolher ativos existentes ou novos.

Uso: `/aporte 10000` (o argumento é o valor em R$).

**Quando usar:** sempre que o usuário falar em aporte, aportar, investir mais, colocar dinheiro novo, "tenho X para investir" ou "onde coloco R$ X". Também vale quando ele não digitar `/aporte`.

## ⚠️ Regras

- **Privacidade:** não commita nem publica nada. Os relatórios ficam em `output/` (gitignored), como no `/carteira`.
- **Só compra:** o aporte nunca vende. O rebalanceamento acontece direcionando o dinheiro novo para as classes abaixo do alvo.
- **Carteira atualizada sempre:** a carteira tem que refletir as posições de hoje. Sem isso, as quantidades, os pesos e os tetos saem errados. Siga o Passo 0 sempre, sem pular.

---

## Passo 0 — Preparação (obrigatório)

**0.1 Valor.** Se o usuário não informou o valor, pergunte. Aceite "10k", "R$ 10.000" ou "10 mil" e converta para número.

**0.2 Carteira atualizada.** Antes de qualquer cálculo, pergunte ao usuário (AskUserQuestion):

> "Você exportou a carteira atualizada do StatusInvest depois da última compra/venda?
> (StatusInvest → Carteira → Patrimônio → Exportar — o arquivo cai em Downloads como `carteira-patrimonio-export.xlsx`)"

Opções:
- **Sim, exportei agora:** siga para 0.3.
- **Não mudou nada desde a última análise:** siga para 0.3.
- **Vou exportar agora:** espere o usuário avisar que exportou e depois siga para 0.3.

**0.3 Verificar o frescor dos dados:**

```bash
python src/aporte_check.py
```

| Exit | Significado | Ação |
|---|---|---|
| 0 | Análise mais nova que o export e com até 7 dias | Siga para o Passo 1 |
| 1 | O export é mais novo que a análise, a análise tem mais de 7 dias ou nunca rodou | **Rode o fluxo completo do `/carteira`** (coleta → prompts → agentes → EVAL → alocador → relatório) e só depois volte ao Passo 1. Avise o usuário: "Carteira mudou — reanalisando as posições antes do aporte." |
| 2 | Export não encontrado | Peça ao usuário para exportar e pare |

Se a verificação indicar screener VELHO (mais de 7 dias), avise o usuário e sugira rodar `/magic-formula` ou `/fii-analysis` antes. Pergunte se ele quer atualizar ou seguir com o screener velho. Nunca rode os screeners sem perguntar, porque são demorados.

Mostre ao usuário a saída do check (datas do export, da análise e dos screeners) antes de seguir.

---

## Passo 1 — Divisão por classe + candidatos

```bash
python src/aporte_main.py --valor <VALOR>
```

O script faz quatro coisas:
- Divide o aporte pelas classes, proporcional ao quanto cada uma está abaixo de 33%. Se sobrar dinheiro depois de igualar as classes, divide igualmente.
- Monta os candidatos de Ações e FIIs: posições atuais com convicção ≥ 6 e fora de VENDER/TROCAR, mais até 8 ativos COMPRAR do screener que o usuário ainda não tem.
- Monta os candidatos de ETF: IVVB11 e NASD11, mais a lista fechada `ETFS_PERMITIDOS` em `src/aporte_main.py`.
- Gera `output/aporte_prompts/<CLASSE>.txt`. Classe com orçamento abaixo de R$ 300 não ganha agente.

Mostre ao usuário a divisão por classe (antes → depois).

## Passo 2 — Agentes (um por classe, em paralelo)

```
Leia output\aporte_prompts\{CLASSE}.txt e siga EXATAMENTE as instruções (alocação + busca web). Grave apenas o JSON válido (UTF-8) em output\aporte_out\{CLASSE}.json com a ferramenta Write. Responda só "OK {CLASSE} <ticker:valor, ...>".
```

## Passo 3 — EVAL + plano de ordens

```bash
python src/aporte_eval.py
```

O EVAL verifica:
- a soma de cada classe bate com o orçamento (±2%);
- os tickers estão na lista de candidatos;
- cada classe tem no máximo 4 ativos e cada ordem é de pelo menos R$ 300;
- cada ativo fica dentro do teto (5% nas ações, 8% nos FIIs);
- os setores ficam dentro do teto (30% das ações, 40% dos FIIs);
- ETF novo tem preço no yfinance (confirma que o ticker existe).

Depois calcula as cotas inteiras e o troco, e grava `output/aporte_plano.json`.

**Exit > 0:** corrija `output/aporte_out/<CLASSE>.json` e rode de novo (no máximo 2 iterações). AVISOs (por exemplo, classe fora da banda de 26–40%) não bloqueiam, mas mostre ao usuário.

## Passo 4 — Relatório

```bash
python src/aporte_report.py && start output\aporte.html
```

## Passo 5 — Resumo no terminal

```
APORTE R$ X — [data]
Classes: ETF a%→b% | FII a%→b% | Ações a%→b%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Ticker | Classe | Novo? | Qtd | Valor   | % aporte | Peso antes→depois
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
...
Troco: R$ Y
```

Depois da tabela, escreva 2-3 linhas sobre a lógica da distribuição. Lembre que os preços são do último fechamento e precisam ser conferidos na corretora. Sempre feche com: "Não é recomendação de investimento."

Limites ajustáveis: constantes no topo de `src/aporte_main.py`.
