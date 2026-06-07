# Magic Formula BR — Guia para Mesa de Investimento

> Como usar o sistema, entender os critérios de seleção e interpretar os relatórios.

---

## Sumário

1. [O que é a Magic Formula?](#1-o-que-é-a-magic-formula)
2. [Como o sistema funciona](#2-como-o-sistema-funciona)
3. [O que o sistema analisa](#3-o-que-o-sistema-analisa)
4. [Filtros de elegibilidade](#4-filtros-de-elegibilidade)
5. [Como usar — passo a passo](#5-como-usar--passo-a-passo)
6. [Como interpretar o relatório](#6-como-interpretar-o-relatório)
7. [A análise da IA — o que considera](#7-a-análise-da-ia--o-que-considera)
8. [Guardrails e proteções](#8-guardrails-e-proteções)
9. [Backtest — como analisar o histórico](#9-backtest--como-analisar-o-histórico)
10. [Limitações importantes](#10-limitações-importantes)
11. [Frequência de atualização recomendada](#11-frequência-de-atualização-recomendada)
12. [Glossário](#12-glossário)

---

## 1. O que é a Magic Formula?

A **Magic Formula** foi criada por Joel Greenblatt, gestor americano e professor de Columbia Business School, publicada no livro *"The Little Book That Beats the Market"* (2005).

O princípio é simples: **comprar boas empresas a preços baratos**, de forma sistemática e sem emoção.

A fórmula usa apenas dois critérios:

### EV/EBIT — "Quão barato estou pagando pela empresa?"

- **EV (Enterprise Value):** valor total da empresa — o que você pagaria para comprar 100% dela, incluindo a dívida
- **EBIT:** lucro operacional antes de juros e impostos — o caixa que o negócio gera
- **EV/EBIT:** quantas vezes o lucro operacional você está pagando

> **Exemplo:** EV/EBIT de 5x significa que você paga 5 anos de lucro operacional para comprar a empresa inteira.  
> EV/EBIT de 2x é muito barato. EV/EBIT de 20x é caro.

**Quanto menor, melhor.**

---

### ROIC — "Qual a qualidade do negócio?"

- **ROIC (Return on Invested Capital):** quanto a empresa gera de lucro operacional para cada real de capital investido no negócio
- Mede a eficiência e qualidade do modelo de negócios

> **Exemplo:** ROIC de 25% significa que para cada R$100 investidos no negócio, a empresa gera R$25 de lucro operacional por ano.

**Quanto maior, melhor.**

---

### Como o ranking funciona

1. Classifica todas as empresas do mais barato ao mais caro (menor EV/EBIT = posição 1)
2. Classifica todas as empresas da melhor à pior qualidade (maior ROIC = posição 1)
3. Soma as duas posições → **Magic Formula Score**
4. Menor score = melhor empresa (barata E boa ao mesmo tempo)

> Uma empresa que é a 3ª mais barata e a 5ª melhor em qualidade tem score 8.  
> É melhor do que uma que é a 1ª mais barata mas a 20ª em qualidade (score 21).

---

## 2. Como o sistema funciona

```
1. Você exporta o CSV do StatusInvest (busca avançada)
   ↓
2. O sistema aplica filtros automáticos de elegibilidade
   ↓
3. Calcula o ranking Magic Formula para todas as empresas elegíveis
   ↓
4. Verifica automaticamente quais estão em Recuperação Judicial
   ↓
5. Remove empresas com mais de 3 do mesmo setor (diversificação)
   ↓
6. Busca dados históricos (tendência de ROIC, margens, receita nos últimos trimestres)
   ↓
7. IA analisa profundamente cada empresa candidata
   ↓
8. Valida se a análise da IA é consistente com os dados reais
   ↓
9. Gera relatório HTML completo com Top 15 + análise por empresa
```

**Tempo total:** aproximadamente 2-3 minutos.

---

## 3. O que o sistema analisa

### Dados do CSV (StatusInvest)

| Métrica | O que mede |
|---------|-----------|
| **EV/EBIT** | Preço pago em múltiplos do lucro operacional |
| **ROIC** | Retorno sobre capital investido |
| **Margem EBIT** | Porcentagem da receita que vira lucro operacional |
| **ROE** | Retorno sobre patrimônio líquido |
| **Dívida Líquida / EBIT** | Quantos anos de lucro operacional para pagar a dívida |
| **CAGR Receitas 5 anos** | Crescimento anual composto da receita nos últimos 5 anos |
| **CAGR Lucros 5 anos** | Crescimento anual composto do lucro nos últimos 5 anos |
| **Liquidez Média Diária** | Volume financeiro negociado por dia (R$) |
| **Valor de Mercado** | Capitalização de mercado total |

### Dados históricos (via Yahoo Finance — busca automática)

| Dado | Para que serve |
|------|---------------|
| ROIC trimestral (6 trimestres) | Ver se o ROIC é consistente ou foi um evento pontual |
| Margem EBIT trimestral (6 trimestres) | Ver se as margens estão expandindo ou comprimindo |
| Receita trimestral (6 trimestres) | Ver tendência real de crescimento |
| Preço vs 52 semanas (máx/mín) | Contexto de valuation histórico |
| Beta | Sensibilidade ao mercado — medida de risco |

### Verificação de Recuperação Judicial (automática)

O sistema acessa o site do StatusInvest para cada empresa candidata e verifica se existe o badge oficial de Recuperação Judicial. Usa 3 sinais independentes para evitar erros.

---

## 4. Filtros de elegibilidade

Antes de ranquear, o sistema remove automaticamente empresas que não devem entrar:

| Filtro | Critério | Por quê |
|--------|----------|---------|
| **Setor financeiro** | Remove bancos, seguradoras, corretoras | Métricas de balanço são incompatíveis com a fórmula |
| **FIIs e Units problemáticas** | Tratamento especial por sufixo | Estrutura diferente de ações ordinárias |
| **Liquidez mínima** | Liquidez diária ≥ R$ 500 mil | Sem liquidez mínima é difícil montar/desmontar posição |
| **ROIC positivo** | ROIC > 0% | Empresa com retorno negativo sobre capital |
| **EV/EBIT positivo** | EV/EBIT > 0 | Empresa com EBIT negativo (prejuízo operacional) |
| **Endividamento extremo** | Dívida/EBIT < 5x | Risco de insolvência |
| **Recuperação Judicial** | Verificação automática no StatusInvest | Empresa em processo judicial é excluída |
| **Concentração setorial** | Máximo 3 por setor | Diversificação mínima do portfólio |

### Deduplicação de tickers

Quando a mesma empresa tem múltiplos tickers (ex: PETR3, PETR4), o sistema escolhe automaticamente o mais adequado:

- **11 (Units)** — preferencial quando existe (ex: KLBN11 em vez de KLBN3 e KLBN4)
- **4 (PN)** — preferencial quando não há Units (maior dividendo geralmente)
- **3 (ON)** — padrão quando não há alternativa melhor

---

## 5. Como usar — passo a passo

### Passo 1 — Exportar o CSV do StatusInvest

1. Acesse [statusinvest.com.br/acoes](https://statusinvest.com.br/acoes)
2. Vá em **Busca Avançada**
3. Clique em **Exportar** (botão verde no canto superior direito)
4. Salve o arquivo como `statusinvest-busca-avancada.csv`
5. Substitua o arquivo em `<diretório-do-projeto>\data\`

> **Importante:** exporte com todos os filtros em branco para incluir todas as ações. O sistema faz a filtragem internamente.

---

### Passo 2 — Abrir o Claude Code

Abra o terminal Claude Code no diretório do projeto (onde está o `README.md`).

---

### Passo 3 — Executar a análise

Digite na linha de comando do Claude Code:
```
/magic-formula
```

O sistema irá:
- Processar o CSV automaticamente
- Verificar recuperação judicial de cada candidata
- Analisar dados históricos
- Gerar análise por IA para cada empresa
- Abrir o relatório HTML no navegador

---

### Passo 4 — Interpretar o relatório

O relatório abrirá automaticamente no navegador. Veja a seção [Como interpretar o relatório](#6-como-interpretar-o-relatório).

---

## 6. Como interpretar o relatório

### Cabeçalho — Funil de seleção

```
Empresas no CSV: 202
Após filtros básicos: 127
Após verificação RJ: 125
Após limite de setor: 118
Selecionadas: 15
```

Mostra quantas empresas foram eliminadas em cada etapa.

---

### Tabela resumo

| Coluna | O que significa | Como ler |
|--------|----------------|----------|
| **#** | Posição no ranking Magic Formula | Menor é melhor |
| **EV/EBIT** | Preço em múltiplos do lucro | Verde < 5x, Amarelo 5-12x, Vermelho > 12x |
| **ROIC** | Qualidade do negócio | Verde ≥ 20%, Amarelo 10-20%, Vermelho < 10% |
| **Score MF** | Soma dos rankings | Menor é melhor |
| **Score IA** | Avaliação qualitativa da IA (1-10) | 9-10 = alta convicção |
| **Recomendação** | Decisão da IA | COMPRAR / NEUTRO / CAUTELA |
| **Mg EBIT** | Margem operacional | Acima de 15% é saudável |
| **Dív/EBIT** | Endividamento | Verde < 0 (caixa líquido), Amarelo 0-2x, Vermelho > 2x |
| **CAGR Receita** | Crescimento de receita (5 anos) | Positivo = empresa crescendo |

---

### Cards por empresa

Cada empresa tem um card com:

**Badge de recomendação:**
- 🟢 **COMPRAR** — IA identificou combinação favorável de qualidade + valuation + histórico
- 🟡 **NEUTRO** — empresa elegível mas com ressalvas a considerar
- 🔴 **CAUTELA** — métricas inconsistentes ou risco identificado

**Score IA (1-10):**
- 9-10: convicção máxima
- 7-8: boa oportunidade
- 5-6: oportunidade moderada
- 1-4: IA não recomenda mesmo passando nos filtros

**Pontos fortes:** argumentos favoráveis baseados nos dados
**Riscos:** fatores negativos identificados nos dados
**Tags:** `SUSTENTAVEL / PONTUAL / INCERTO` para ROIC e `MUITO_BARATO / BARATO / JUSTO / CARO` para valuation

> **Importante:** os pontos fortes e riscos são derivados **exclusivamente dos dados quantitativos disponíveis**. O sistema valida automaticamente que a IA não inventou informações.

---

### Gráficos

**ROIC por empresa (barras):** compara visualmente a qualidade dos negócios no portfólio.

**EV/EBIT vs ROIC (scatter):** o quadrante ideal é canto inferior direito — EV/EBIT baixo (barato) e ROIC alto (boa empresa). Empresas nesse quadrante são as mais atrativas pela Magic Formula.

---

## 7. A análise da IA — o que considera

A IA analisa cada empresa com os seguintes critérios:

### 1. Qualidade do ROIC — é sustentável?

- Compara o ROIC do CSV com o histórico trimestral dos últimos 6 trimestres
- ROIC crescente ao longo dos trimestres = negócio melhorando → `SUSTENTAVEL`
- ROIC muito alto em 1-2 trimestres seguido de queda = pode ser evento pontual → `PONTUAL`
- ROIC oscilando sem tendência clara → `INCERTO`

> **Exemplo de alerta:** RIAA3 tem ROIC de 26% no CSV, mas no histórico trimestral aparece um trimestre com 84% e os demais com 8-15%. A IA identifica que o ROIC alto é PONTUAL e não SUSTENTAVEL.

### 2. Endividamento — risco ou oportunidade?

- Dívida líquida negativa = empresa tem mais caixa do que dívida → positivo
- Dívida/EBIT < 1x com ROIC alto = combinação rara e muito valiosa
- Dívida/EBIT > 3x com margens caindo = risco real de deterioração
- Dívida crescendo com EBIT estagnado = bandeira vermelha

### 3. Crescimento — coerente?

- CAGR Receitas e CAGR Lucros ambos positivos = crescimento saudável
- CAGR Lucros > CAGR Receitas = empresa expandindo margem (muito bom)
- CAGR Lucros < CAGR Receitas = margem comprimindo (atenção)
- CAGR Lucros negativo com ROIC alto = resultado histórico provavelmente não sustentável

### 4. Valuation — o preço está correto?

| EV/EBIT | Classificação | Condição para COMPRAR |
|---------|--------------|----------------------|
| < 5x | MUITO_BARATO | Quase sempre recomenda (verificar outros sinais) |
| 5-10x | BARATO | Recomenda se ROIC > 15% |
| 10-15x | JUSTO | Recomenda apenas se ROIC > 25% |
| > 15x | CARO | Raramente recomenda |

### 5. Posição de preço vs 52 semanas

- Preço próximo ao mínimo de 52 semanas + fundamentos sólidos = oportunidade
- Preço próximo ao máximo sem crescimento correspondente nos fundamentos = risco

### 6. Beta — perfil de risco

- Beta < 0.7: ação defensiva, baixa volatilidade
- Beta 0.7-1.3: volatilidade próxima ao mercado
- Beta > 1.3: ação agressiva, alta volatilidade — IA pondera no score

---

## 8. Guardrails e proteções

### Recuperação Judicial — dupla verificação

O sistema verifica Recuperação Judicial com 3 sinais independentes:

1. **Badge oficial do StatusInvest** — elemento visual na página da empresa (mais confiável)
2. **Texto da página** — menções a "recuperação judicial", "credores", "plano de recuperação"
3. **Ausência de cotação** — empresas suspensas frequentemente não têm preço exibido

**Regra:** a empresa só é removida se o badge oficial aparecer, OU se 2 ou mais sinais confirmarem. Isso evita remover erroneamente uma empresa boa por uma menção casual ao tema.

---

### EVAL — a IA não pode inventar dados

Após cada análise gerada pela IA, um sistema de validação automática verifica se as afirmações são consistentes com os números:

- IA diz "dívida baixa" mas Dívida/EBIT é 3.5x → **bloqueado**
- IA diz "crescimento forte" mas CAGR Receitas é -12% → **bloqueado**
- IA diz "margem alta" mas Margem EBIT é 7% → **bloqueado**
- IA dá score 9/10 para empresa com ROIC de 6% → **bloqueado**

Se a análise falhar na validação, o sistema pede uma segunda análise. Se falhar novamente, a empresa é marcada como "análise não validada" no relatório.

---

## 9. Backtest — como analisar o histórico

O backtest simula o que teria acontecido se você tivesse rodado a Magic Formula mensalmente desde uma data de início.

### Como executar

```
/magic-formula-backtest
```

O sistema pergunta o período. Recomendamos iniciar com 2023-01-01 para ter ao menos 2-3 anos de histórico.

---

### Como interpretar o relatório de backtest

**Curva de capital:** linha verde = portfólio Magic Formula, linha cinza = IBOV. Quanto mais a linha verde supera a cinza, maior o alpha gerado.

**Retorno total:** valorização acumulada do portfólio de R$100 inicial.

**Alpha:** diferença de retorno vs IBOV. Alpha de +30% significa que a estratégia rendeu 30 pontos percentuais a mais que o índice.

**Max Drawdown:** maior queda do pico até o vale. Drawdown de -15% significa que em algum momento o portfólio perdeu 15% do seu valor máximo antes de se recuperar.

**Sharpe simplificado:** retorno médio mensal dividido pela volatilidade mensal. Acima de 0.5 é considerado bom.

**Tabela mensal:**
- **Entradas** (verde): ações que passaram a fazer parte do top 15 naquele mês → **comprar**
- **Saídas** (vermelho): ações que saíram do top 15 → **vender**

---

### Aviso importante — Survivorship Bias

> O backtest usa as empresas disponíveis **no CSV de hoje**. Empresas que faliram, entraram em recuperação judicial ou foram deslistadas da B3 durante o período histórico **não aparecem nos dados**.
>
> Isso faz o retorno histórico parecer **melhor do que foi na realidade**. Use o backtest para entender padrões (turnover médio, setores frequentes, consistência do alpha), não para projetar retorno futuro com exatidão.

---

## 10. Limitações importantes

| Limitação | Impacto | O que fazer |
|-----------|---------|-------------|
| **CSV é um snapshot** | Dados são da data de exportação | Atualizar o CSV mensalmente antes de rodar |
| **Survivorship bias no backtest** | Retorno histórico superestimado | Usar backtest para padrões, não projeções |
| **Dados yfinance incompletos** | Alguns small caps sem histórico | Sistema continua sem dados históricos — confiança apenas no CSV |
| **Setor pela B3, não por análise** | Empresa pode ser de setor diferente do classificado | Revisar classificações setoriais suspeitas |
| **Magic Formula ignora setores cíclicos** | Em fundo de ciclo, empresa parece barata mas EBIT é temporariamente alto | IA considera isso na análise qualitativa |
| **Não considera governança corporativa** | Empresa pode ter fundamentos bons mas gestão ruim | Pesquisa adicional recomendada para as top 5 |
| **Não considera liquidez do portfólio** | Portfolio de R$10M+ pode ter dificuldade de entrada em small caps | Verificar liquidez diária vs tamanho da posição pretendida |

---

## 11. Frequência de atualização recomendada

A Magic Formula original de Greenblatt recomenda **rebalanceamento anual**. Para o mercado brasileiro, recomendamos:

### Rebalanceamento mensal (mais ativo)

**Quando fazer:**
1. Exportar novo CSV do StatusInvest
2. Executar `/magic-formula`
3. Comparar top 15 atual com portfólio atual
4. Vender ações que saíram do top 15
5. Comprar novas entradas

**Vantagem:** captura mudanças mais rapidamente  
**Desvantagem:** mais custo de corretagem e IR sobre lucros de curto prazo

---

### Rebalanceamento trimestral (intermediário)

**Quando fazer:** após resultado trimestral das empresas (março, junho, setembro, dezembro)  
**Vantagem:** equilibra atualidade e custo  
**Desvantagem:** pode manter posições deterioradas por mais tempo

---

### Rebalanceamento semestral/anual (passivo)

**Alinhado com Greenblatt:** manter por 12 meses independente do que acontecer  
**Vantagem:** menor custo, benefício fiscal (IRPF isenta vendas até R$20k/mês)  
**Desvantagem:** pode ignorar deteriorações significativas

---

## 12. Glossário

| Termo | Definição |
|-------|-----------|
| **EV (Enterprise Value)** | Valor total da empresa = Market Cap + Dívida Líquida |
| **EBIT** | Lucro antes de juros e impostos (lucro operacional) |
| **EV/EBIT** | Múltiplo de valuation. Quanto você paga em anos de lucro operacional |
| **ROIC** | Return on Invested Capital. Retorno sobre o capital investido no negócio |
| **Magic Formula Score** | Soma do ranking de EV/EBIT com ranking de ROIC. Menor = melhor |
| **Margem EBIT** | EBIT / Receita Líquida. Eficiência operacional |
| **Dívida Líquida** | Dívidas financeiras − Caixa. Negativa = empresa tem mais caixa que dívidas |
| **CAGR** | Compound Annual Growth Rate. Taxa de crescimento anual composta |
| **Survivorship Bias** | Viés de usar apenas dados de empresas que sobreviveram (subestima risco) |
| **Alpha** | Retorno superior ao índice de referência (IBOV) |
| **Drawdown** | Queda do valor de pico até o vale em determinado período |
| **Beta** | Sensibilidade da ação às oscilações do mercado. Beta > 1 = mais volátil que o mercado |
| **Sharpe** | Retorno ajustado ao risco. Maior = melhor retorno por unidade de risco |
| **Recuperação Judicial** | Processo legal para reestruturação de dívidas de empresa insolvente |
| **PN (ticker 4)** | Ação Preferencial. Prioridade no dividendo, sem direito a voto |
| **ON (ticker 3)** | Ação Ordinária. Direito a voto nas assembleias |
| **Units (ticker 11)** | Certificados que representam conjunto de ações ON + PN |
| **FII** | Fundo de Investimento Imobiliário. Excluído da análise (métricas diferentes) |
| **Guardrail** | Sistema de proteção automático para evitar erros na seleção |
| **EVAL** | Sistema de validação que verifica se a IA não inventou informações |
| **Setor B3** | Classificação setorial da Bolsa brasileira (ex: Consumo Cíclico, Saúde) |
