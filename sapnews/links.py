"""Controllo periodico dei link del catalogo vendor.

Le pagine "richiedi una demo" cambiano spesso indirizzo. Invece di fidarci,
le verifichiamo: la dashboard ripiega sul sito ufficiale per ogni link che
qui risulta rotto, così un pulsante non porta mai su un 404.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from .fetch import build_session
from .models import iso, now_utc


def _check(session: requests.Session, url: str, timeout: int = 15) -> dict[str, Any]:
    try:
        r = session.head(url, timeout=timeout, allow_redirects=True)
        # Diversi siti non implementano HEAD: si riprova con una GET.
        if r.status_code >= 400 or r.status_code == 405:
            r = session.get(r.url if r.history else url, timeout=timeout,
                            allow_redirects=True, stream=True)
            r.close()
        return {"stato": r.status_code, "ok": r.status_code < 400,
                "finale": r.url, "controllato_il": iso(now_utc())}
    except requests.RequestException as exc:
        return {"stato": 0, "ok": False, "errore": type(exc).__name__,
                "controllato_il": iso(now_utc())}


def raccogli_link(vendors: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for v in vendors:
        for url in (v.get("link") or {}).values():
            if isinstance(url, str) and url.startswith("http"):
                urls.append(url)
    return sorted(set(urls))


def check_links(urls: list[str], workers: int = 8) -> dict[str, Any]:
    session = build_session()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        esiti = list(pool.map(lambda u: _check(session, u), urls))
    return dict(zip(urls, esiti))
