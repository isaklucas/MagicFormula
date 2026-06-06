"""
Guardrail de dupla verificação para Recuperação Judicial.
Evita falsos positivos (excluir empresa boa) e falsos negativos (incluir empresa em RJ).

Sinal primário:  badge exato do StatusInvest (title="A empresa está em processo judicial")
Sinal secundário: outros indicadores textuais na página
Sinal terciário:  ausência de dados financeiros normais (página de empresa sem cotação ativa)

Regra: empresa é marcada em RJ apenas se PELO MENOS 2 sinais confirmam.
"""

from bs4 import BeautifulSoup


SECONDARY_PATTERNS = [
    "recuperação judicial",
    "recuperacao judicial",
    "em processo judicial",
    "plano de recuperação",
    "plano de recuperacao",
    "credores aprovam",
    "assembleia de credores",
]


def _extract_sector(soup: BeautifulSoup) -> str:
    """Extrai setor B3 do StatusInvest. Ex: 'Financeiro e Outros', 'Consumo Cíclico'."""
    setor_div = soup.find("div", string=lambda t: t and t.strip() == "SETOR")
    if setor_div:
        small = setor_div.find_next_sibling("small")
        if small:
            return small.get_text(strip=True)
    return "Desconhecido"


def _signal_primary(soup: BeautifulSoup) -> bool:
    """Badge oficial do StatusInvest."""
    badge = soup.find("strong", title="A empresa está em processo judicial")
    return badge is not None


def _signal_secondary(soup: BeautifulSoup) -> tuple[bool, list[str]]:
    """Texto RJ em qualquer parte da página."""
    text_lower = soup.get_text(separator=" ").lower()
    found = [p for p in SECONDARY_PATTERNS if p in text_lower]
    return len(found) > 0, found


def _signal_no_price(soup: BeautifulSoup) -> bool:
    """Empresa sem preço listado pode indicar suspensão de negociação."""
    price_el = soup.find(class_="value") or soup.find(attrs={"title": "Valor atual do ativo"})
    if price_el is None:
        return True
    try:
        val = float(price_el.get_text(strip=True).replace(",", ".").replace("R$", "").strip())
        return val <= 0
    except Exception:
        return False


def analyze_rj_signals(html: str, ticker: str) -> dict:
    """
    Retorna dict com resultado e evidências para auditoria.
    {
        "em_rj": bool,
        "confianca": "ALTA" | "MEDIA" | "BAIXA",
        "sinais": [...],
        "evidencias": [...]
    }
    """
    soup = BeautifulSoup(html, "html.parser")

    setor = _extract_sector(soup)
    primary = _signal_primary(soup)
    secondary, secondary_matches = _signal_secondary(soup)
    no_price = _signal_no_price(soup)

    sinais_ativos = []
    evidencias = []

    if primary:
        sinais_ativos.append("BADGE_OFICIAL")
        evidencias.append("Badge StatusInvest: 'A empresa está em processo judicial'")

    if secondary:
        sinais_ativos.append("TEXTO_RJ")
        evidencias.append(f"Padroes textuais encontrados: {secondary_matches[:3]}")

    if no_price:
        sinais_ativos.append("SEM_COTACAO")
        evidencias.append("Preco de cotacao ausente ou zero")

    n = len(sinais_ativos)

    # Regra: badge oficial sozinho ja basta (fonte autoritativa)
    # Outros sinais precisam de 2+ para confirmar
    em_rj = primary or (n >= 2)

    if primary:
        confianca = "ALTA"
    elif n >= 2:
        confianca = "MEDIA"
    elif n == 1:
        confianca = "BAIXA"
        em_rj = False  # 1 sinal sem badge = beneficio da duvida
    else:
        confianca = "ALTA"  # nenhum sinal = claramente nao em RJ

    return {
        "ticker": ticker,
        "em_rj": em_rj,
        "confianca": confianca,
        "sinais": sinais_ativos,
        "evidencias": evidencias,
        "setor": setor,
    }
