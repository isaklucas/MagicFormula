"""
Gera um prompt por ativo da carteira em output/carteira_prompts/<TICKER>.txt.
Cada agente lê o seu arquivo e grava o JSON em output/carteira_out/<TICKER>.json.

Uso: python src/carteira_prompts.py
"""

import sys
import json
import shutil
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT = ROOT / "output"
PROMPTS = OUT / "carteira_prompts"
RESULTS = OUT / "carteira_out"

_REGRAS_ACAO = """REGRAS DE COERÊNCIA (ação):
- CAGR Lucros negativo → NÃO mencione crescimento de lucros
- Dív/EBIT > 1 → NÃO diga "dívida baixa" ou "caixa líquido"
- Margem EBIT < 10% → NÃO classifique como "margem alta"
- Valores absurdos (ex.: DY > 100%) são erro de dado — ignore-os
- Banco/seguradora sem EV/EBIT: avalie por ROE, P/VPA e contexto web"""

_REGRAS_FII = """REGRAS DE COERÊNCIA (FII/FIAgro):
- DY Limpo < 6% → NÃO classifique como "DY alto"
- P/VP > 1.0 → NÃO diga que está "descontado"
- Avalie risco de crédito (papel/CRI), vacância (tijolo) e tendência dos proventos"""

TPL = """Você é gestor de carteira especializado em ações e FIIs brasileiros, focado em value investing.
O USUÁRIO JÁ POSSUI {T}. Sua tarefa é decidir o que fazer com essa posição:
MANTER, REFORCAR (comprar mais), VENDER ou TROCAR por uma das alternativas listadas.

Use os dados abaixo como base. NÃO invente números.

{regras}

REGRAS DE DECISÃO:
0. PADRÃO É MANTER. Vender realiza o resultado e é irreversível — o usuário exige EMBASAMENTO MUITO FORTE
   para VENDER ou TROCAR. Na dúvida, MANTER. Preço caído sozinho NÃO é motivo de venda (pode ser oportunidade).
1. Resultado da posição NÃO decide sozinho — decida pelos fundamentos e pelo custo de oportunidade.
   Mas se a posição está NO PREJUÍZO, a barreira para VENDER/TROCAR sobe: exija os 3 critérios abaixo.

CRITÉRIOS OBRIGATÓRIOS PARA VENDER/TROCAR (todos, com evidência concreta):
  (a) TESE QUEBRADA: deterioração estrutural confirmada — não só um trimestre ruim. Exemplos válidos:
      queda de ROIC/margem em vários trimestres seguidos, alavancagem crescente perigosa, inadimplência
      relevante (FII de papel), vacância estrutural (tijolo), corte recorrente de proventos, diluição,
      governança/fraude, risco regulatório concreto. Exemplos INVÁLIDOS: "preço caiu", "está fora do screener",
      "alternativa tem score maior".
  (b) EVIDÊNCIAS: pelo menos 2 fatos verificáveis (dados acima e/ou busca web, com fonte) que sustentem (a).
  (c) DESTINO CLARAMENTE SUPERIOR (só TROCAR): melhor em pelo menos 2 de 3 dimensões — múltiplo
      (EV/EBIT ou P/VP), qualidade (ROIC/margem ou DY limpo sustentável) e risco (dívida/crédito) —
      E com perspectiva de recuperar a perda realizada mais rápido que o ativo atual.
  Se faltar qualquer um → MANTER (com riscos listados) e diga o que precisaria acontecer para vender.

2. TROCAR só se uma alternativa for claramente superior (múltiplo, qualidade ou risco) — cite qual e por quê.
   troca_por SÓ pode conter tickers da lista ALTERNATIVAS DE TROCA. Lista vazia → não use TROCAR.
   Liste de 2 a 3 opções em ORDEM DE PREFERÊNCIA, de setores diferentes quando possível.
   Outros ativos da carteira também podem ser trocados ao mesmo tempo: um alocador de carteira escolhe
   o destino final respeitando limites de concentração (máx. 1 troca por destino, 5% por ativo,
   30% por setor). Por isso NÃO escolha só pelo maior score — inclua opções boas e diversificadas.
3. VENDER quando a tese quebrou (deterioração, risco estrutural) e nenhuma alternativa fizer sentido.
4. REFORCAR só com fundamentos sólidos E preço atrativo; considere o peso atual na carteira (concentração).
5. score_conviccao = convicção em MANTER o ativo (1-10):
   MANTER/REFORCAR → 4-10 | VENDER/TROCAR → 1-4 (se convicção é 5+, a tese não quebrou → MANTER)

{ctx}

BUSCA WEB (obrigatória — máx 3 buscas):
- "{T} último resultado" / "{T} último relatório gerencial"
- notícias recentes de risco: "{T} dívida", "{T} inadimplência", "{T} guidance" conforme o caso
- Se TROCAR: 1 busca rápida sobre a alternativa escolhida
Use termos sem ano fixo. NÃO invente fatos não presentes na busca.
Sem resultado útil → web_resumo = "Sem dados web relevantes."

Antes do JSON: identifique o maior ponto forte e o maior risco (pontos_fortes[0] e riscos[0]).

Responda EXATAMENTE este JSON (sem markdown, sem texto fora):
{{
  "ticker": "{T}",
  "recomendacao": "MANTER" | "REFORCAR" | "VENDER" | "TROCAR",
  "score_conviccao": <1-10>,
  "motivo": "<resumo executivo, máx 160 chars>",
  "tese_atual": "<1-2 frases: a tese de investimento ainda vale? por quê>",
  "pontos_fortes": ["<ponto 1>", "<ponto 2>"],
  "riscos": ["<risco 1>", "<risco 2>"],
  "troca_por": [{{"ticker": "<1ª opção>", "motivo": "<por que é superior>"}},
                {{"ticker": "<2ª opção>", "motivo": "<...>"}}],
  "web_resumo": "<1-2 frases do que a busca confirmou ou adicionou>",
  "embasamento": {{
    "tese_quebrada": "<VENDER/TROCAR: qual deterioração estrutural. MANTER: '' >",
    "evidencias": ["<fato verificável 1 + fonte>", "<fato verificável 2 + fonte>"],
    "comparacao_destino": "<TROCAR: destino vs atual nas 3 dimensões, com números. Senão: ''>",
    "gatilho_venda": "<MANTER/REFORCAR: o que precisaria acontecer para vender. Senão: ''>"
  }}
}}
(troca_por = [] quando recomendacao != TROCAR; 2-3 opções ordenadas quando TROCAR)
"""


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="tickers separados por vírgula — reprocessa só esses, mantém o resto")
    args = parser.parse_args()

    with open(OUT / "carteira_candidates.json", encoding="utf-8") as f:
        data = json.load(f)
    ativos = data["acoes"] + data["fiis"]

    if args.only:
        only = {t.strip().upper() for t in args.only.split(",")}
        ativos = [a for a in ativos if a["TICKER"] in only]
        PROMPTS.mkdir(parents=True, exist_ok=True)
        RESULTS.mkdir(parents=True, exist_ok=True)
        for a in ativos:
            (RESULTS / f"{a['TICKER']}.json").unlink(missing_ok=True)
    else:
        shutil.rmtree(PROMPTS, ignore_errors=True)
        shutil.rmtree(RESULTS, ignore_errors=True)
        PROMPTS.mkdir(parents=True)
        RESULTS.mkdir(parents=True)

    for a in ativos:
        regras = _REGRAS_ACAO if a["classe"] == "ACAO" else _REGRAS_FII
        txt = TPL.format(T=a["TICKER"], regras=regras, ctx=a["contexto_agente"])
        (PROMPTS / f"{a['TICKER']}.txt").write_text(txt, encoding="utf-8")
    print(f"[carteira_prompts] {len(ativos)} prompts em {PROMPTS}")
    print(" ".join(a["TICKER"] for a in ativos))


if __name__ == "__main__":
    main()
