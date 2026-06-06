import time
import httpx
from guardrail import analyze_rj_signals

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def _fetch_html(client: httpx.Client, ticker: str) -> str | None:
    url = f"https://statusinvest.com.br/acoes/{ticker.lower()}"
    try:
        resp = client.get(url, timeout=10)
        return resp.text if resp.status_code == 200 else None
    except Exception:
        return None


def check_recuperacao_judicial(tickers: list[str]) -> dict[str, dict]:
    """
    Retorna dict por ticker com resultado completo do guardrail:
    {
      "TICKER": {
        "em_rj": bool,
        "confianca": "ALTA"|"MEDIA"|"BAIXA",
        "sinais": [...],
        "evidencias": [...]
      }
    }
    """
    results = {}
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for i, ticker in enumerate(tickers):
            html = _fetch_html(client, ticker)
            if html is None:
                results[ticker] = {
                    "ticker": ticker,
                    "em_rj": False,
                    "confianca": "BAIXA",
                    "sinais": ["ERRO_REDE"],
                    "evidencias": ["Falha ao acessar StatusInvest — beneficio da duvida aplicado"],
                }
            else:
                results[ticker] = analyze_rj_signals(html, ticker)

            status = "RJ" if results[ticker]["em_rj"] else "OK"
            conf = results[ticker]["confianca"]
            print(f"[scraper] {ticker}: {status} (confianca={conf}) ({i+1}/{len(tickers)})")
            time.sleep(1.2)

    return results
