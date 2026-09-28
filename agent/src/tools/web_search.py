"""Real, free, keyless web search — a DuckDuckGo HTML-results scrape.

No API key, no new heavy dependency (plain regex over the HTML results
page, same style as the sina/tencent quote parsing in market.py). Returns
[] on any failure rather than inventing results.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 6

_RESULT_RE = re.compile(
    r'result__a"[^>]*>(?P<title>.*?)</a>.*?result__snippet[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(html: str) -> str:
    return _TAG_RE.sub("", html).replace("&#x27;", "'").replace("&amp;", "&").strip()


def search(query: str, limit: int = 5) -> list[dict]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        req = urllib.request.Request(url, headers=UA)
        html = urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8", errors="replace")
    except Exception:
        return []

    out = []
    for m in _RESULT_RE.finditer(html):
        out.append({"title": _clean(m.group("title")), "snippet": _clean(m.group("snippet"))})
        if len(out) >= limit:
            break
    return out
