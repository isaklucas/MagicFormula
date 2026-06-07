"""
Navbar compartilhado — Magic Formula.
Importe get_navbar(active) em todos os report scripts.
active: "br" | "us" | "smallcap" | "backtest_br" | "backtest_us" | "backtest_sc"
"""

_PAGES = [
    ("br",          "index.html",       "&#127463;&#127479; BR"),
    ("us",          "us.html",          "&#127482;&#127480; US"),
    ("smallcap",    "smallcap.html",    "&#128202; Small Cap"),
    ("backtest_br", "backtest.html",    "&#128200; Backtest BR"),
    ("backtest_us", "backtest_us.html", "&#128200; Backtest US"),
    ("backtest_sc", "backtest_sc.html", "&#128200; Backtest SC"),
]

_ACTIVE_STYLE  = "font-size:.85rem;color:#e6edf3;font-weight:700;text-decoration:underline;text-underline-offset:3px"
_DEFAULT_STYLE = "font-size:.85rem;opacity:.75"


def get_navbar(active: str = "") -> str:
    links = []
    for key, href, label in _PAGES:
        style = _ACTIVE_STYLE if key == active else _DEFAULT_STYLE
        links.append(f'    <a href="{href}" class="nav-link px-2" style="{style}">{label}</a>')
    links_html = "\n".join(links)
    return f"""\
<nav class="navbar navbar-dark py-2" style="background:#0d1117;border-bottom:1px solid #30363d;position:sticky;top:0;z-index:1030">
  <div class="container-fluid px-3 px-md-4 d-flex align-items-center gap-3">
    <span class="fw-bold me-2" style="color:#58a6ff">&#9998; Magic Formula</span>
{links_html}
  </div>
</nav>"""
