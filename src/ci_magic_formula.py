"""
Pipeline Magic Formula para CI/CD.
Usa Anthropic SDK diretamente (sem Claude Code subagents).
Requer ANTHROPIC_API_KEY no ambiente.
"""

import io
import json
import sys
import time
from pathlib import Path

import anthropic

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from eval import validate_all, print_eval_report

MODEL = "claude-opus-4-8"

PROMPT_TEMPLATE = """\
Você é um analista de investimentos sênior especializado em ações brasileiras.
Analise a ação {TICKER} com base APENAS nos dados abaixo. NÃO invente dados. NÃO use conhecimento externo sobre a empresa.
Baseie TODAS as afirmações exclusivamente nos números fornecidos.

DADOS QUANTITATIVOS (fonte: StatusInvest — snapshot atual):
- EV/EBIT: {ev_ebit}x
- ROIC: {roic}%
- Magic Formula Score: {mf_score}
- Margem EBIT: {margem_ebit}%
- ROE: {roe}%
- Dívida Líquida / EBIT: {div_ebit}x  (negativo = empresa tem caixa líquido)
- CAGR Receitas 5 anos: {cagr_receitas}%
- CAGR Lucros 5 anos: {cagr_lucros}%
- Valor de Mercado: R$ {valor_mercado}
- Liquidez Diária: R$ {liquidez}
- Preço atual: R$ {preco}

{contexto_agente}

REGRAS OBRIGATÓRIAS:
1. Se CAGR Lucros for negativo, NÃO mencione crescimento de lucros como ponto forte
2. Se Dívida/EBIT > 1, NÃO diga que a empresa tem "dívida baixa" ou "caixa líquido"
3. Se Dívida/EBIT < 0, PODE dizer que empresa tem caixa líquido
4. Se Margem EBIT < 10%, NÃO classifique como "margem alta"
5. Score de compra deve ser coerente: ROIC < 10% não justifica score 9+
6. EV/EBIT > 15x com ROIC < 25% não justifica recomendação COMPRAR

CRITÉRIOS DE ANÁLISE:
- Qualidade do ROIC: é sustentável pelas margens e crescimento, ou pontual?
- Endividamento: saudável ou preocupante dado o EBIT?
- Crescimento: CAGR Receitas e Lucros coerentes entre si?
- Valuation: EV/EBIT justificado pela qualidade do negócio?

Retorne EXATAMENTE este JSON (sem markdown, sem texto fora):
{{
  "ticker": "{TICKER}",
  "score_compra": <1-10>,
  "recomendacao": "COMPRAR" | "NEUTRO" | "CAUTELA",
  "pontos_fortes": ["...", "..."],
  "riscos": ["...", "..."],
  "analise": "<2-3 frases objetivas baseadas APENAS nos dados acima>",
  "qualidade_roic": "SUSTENTAVEL" | "PONTUAL" | "INCERTO",
  "valuation": "MUITO_BARATO" | "BARATO" | "JUSTO" | "CARO"
}}"""


def _fmt(v, default="N/D"):
    if v is None or (isinstance(v, float) and v != v):
        return default
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def build_prompt(cand: dict) -> str:
    return PROMPT_TEMPLATE.format(
        TICKER=cand.get("TICKER", ""),
        ev_ebit=_fmt(cand.get("EV/EBIT")),
        roic=_fmt(cand.get("ROIC")),
        mf_score=_fmt(cand.get("posicao_mf")),
        margem_ebit=_fmt(cand.get("MARGEM EBIT")),
        roe=_fmt(cand.get("ROE")),
        div_ebit=_fmt(cand.get("DIVIDA LIQUIDA / EBIT")),
        cagr_receitas=_fmt(cand.get("CAGR RECEITAS 5 ANOS")),
        cagr_lucros=_fmt(cand.get("CAGR LUCROS 5 ANOS")),
        valor_mercado=_fmt(cand.get("VALOR DE MERCADO")),
        liquidez=_fmt(cand.get("LIQUIDEZ MEDIA DIARIA")),
        preco=_fmt(cand.get("PRECO")),
        contexto_agente=cand.get("contexto_agente", ""),
    )


def analyze_ticker(client: anthropic.Anthropic, cand: dict, max_retries: int = 2) -> dict | None:
    prompt = build_prompt(cand)
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"  JSON inválido (tentativa {attempt+1}): {e}")
            if attempt == max_retries:
                return None
            time.sleep(2)
        except anthropic.RateLimitError:
            print(f"  Rate limit — aguardando 30s...")
            time.sleep(30)
        except Exception as e:
            print(f"  Erro: {e}")
            return None
    return None


def main():
    candidates_path = ROOT / "output" / "candidates.json"
    analyses_path = ROOT / "output" / "analyses.json"

    with open(candidates_path, encoding="utf-8") as f:
        data = json.load(f)

    candidates = data.get("candidatos", [])
    print(f"[ci] {len(candidates)} candidatos carregados")

    client = anthropic.Anthropic()
    analyses = {}

    for i, cand in enumerate(candidates):
        ticker = cand.get("TICKER", f"idx_{i}")
        print(f"[{i+1}/{len(candidates)}] {ticker}...")
        result = analyze_ticker(client, cand)
        if result:
            analyses[ticker] = result
            rec = result.get("recomendacao", "?")
            score = result.get("score_compra", "?")
            print(f"  → {rec} | score {score}")
        else:
            print(f"  → FALHOU")
        time.sleep(0.5)

    # EVAL anti-alucinação
    print("\n[ci] Rodando EVAL...")
    eval_results = validate_all(analyses, candidates)
    invalidas = print_eval_report(eval_results)

    with open(analyses_path, "w", encoding="utf-8") as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)

    print(f"\n[ci] {len(analyses)} análises salvas em {analyses_path}")

    comprar = [t for t, a in analyses.items() if a.get("recomendacao") == "COMPRAR"]
    neutro = [t for t, a in analyses.items() if a.get("recomendacao") in ("NEUTRO", "CAUTELA")]
    print(f"[ci] COMPRAR: {len(comprar)} | NEUTRO/CAUTELA: {len(neutro)}")

    return invalidas


if __name__ == "__main__":
    sys.exit(main() or 0)
