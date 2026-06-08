"""
Patch navbar in all docs/*.html without regenerating report content.
Run this whenever navbar.py changes (new link, rename, etc).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from navbar import get_navbar

FILE_TO_ACTIVE = {
    "index.html":        "br",
    "us.html":           "us",
    "smallcap.html":     "smallcap",
    "fii.html":          "fii",
    "backtest.html":     "backtest_br",
    "backtest_us.html":  "backtest_us",
    "backtest_sc.html":  "backtest_sc",
    "backtest_fii.html": "backtest_fii",
}

NAV_PATTERN = re.compile(r'<nav\b[^>]*class="[^"]*navbar[^"]*"[^>]*>[\s\S]*?</nav>', re.MULTILINE)


def patch_file(path: Path, active: str) -> bool:
    html = path.read_text(encoding="utf-8")
    new_nav = get_navbar(active)
    patched, count = NAV_PATTERN.subn(new_nav, html, count=1)
    if count == 0:
        print(f"  [SKIP] {path.name} — <nav> not found")
        return False
    if patched == html:
        print(f"  [OK]   {path.name} — already up to date")
        return False
    path.write_text(patched, encoding="utf-8")
    print(f"  [PATCH] {path.name}")
    return True


def main():
    docs = ROOT / "docs"
    changed = []
    for filename, active in FILE_TO_ACTIVE.items():
        p = docs / filename
        if not p.exists():
            print(f"  [MISS]  {filename} — not found, skipping")
            continue
        if patch_file(p, active):
            changed.append(filename)
    print(f"\nDone. {len(changed)} file(s) patched: {changed or 'none'}")


if __name__ == "__main__":
    main()
