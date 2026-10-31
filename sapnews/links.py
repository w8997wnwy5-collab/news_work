"""Controllo periodico dei link del catalogo vendor.

Le pagine "richiedi una demo" cambiano spesso indirizzo. Invece di fidarci,
le verifichiamo: la dashboard ripiega sul sito ufficiale per ogni link che
qui risulta rotto, così un pulsante non porta mai su un 404.

Il verdetto ha tre stati, non due, perché non tutti i siti rispondono a uno
script come risponderebbero a un browser. "bloccato" vuol dire che il
controllo non è riuscito a stabilire nulla, e in quel caso il link resta dov'è:
degradare un link valido è peggio che lasciarne passare uno morto.

"rotto" lo dice solo un codice HTTP di errore, arrivato da un host che non
combatte gli script. Se la risposta non arriva affatto — DNS, TLS, timeout,
connessione chiusa — non sappiamo niente della pagina, e il link resta dov'è.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

import requests

from .fetch import build_session
from .models import iso, now_utc


# Codici con cui un sito dice "non sei un browser", non "la pagina non esiste".
ANTIBOT = {401, 403, 429, 999}


def host_incerto(url: str, host_incerti: list[str] | None) -> bool:
    """Vero se l'host è noto per rispondere agli script in modo incoerente."""
    if not host_incerti:
        return False
    dominio = urlparse(url).hostname or ""
    return any(dominio == h or dominio.endswith("." + h) for h in host_incerti)


def esito_da_stato(stato: int, incerto: bool = False) -> str:
    if stato < 400:
        return "ok"
    if stato in ANTIBOT:
        return "bloccato"
    # Su un host incerto lo stesso indirizzo torna 200, 999 o 404 a pochi minuti
    # di distanza: un errore non distingue la pagina sparita dallo script
    # respinto, quindi non lo si spaccia per un verdetto.
    if incerto:
        return "bloccato"
    return "rotto"


def _check(session: requests.Session, url: str, timeout: int = 15,
           incerto: bool = False) -> dict[str, Any]:
    try:
        r = session.head(url, timeout=timeout, allow_redirects=True)
        # Diversi siti non implementano HEAD: si riprova con una GET.
        if r.status_code >= 400 or r.status_code == 405:
            r = session.get(r.url if r.history else url, timeout=timeout,
                            allow_redirects=True, stream=True)
            r.close()
        esito = esito_da_stato(r.status_code, incerto)
        return {"stato": r.status_code, "esito": esito, "ok": esito != "rotto",
                "finale": r.url, "controllato_il": iso(now_utc())}
    except requests.RequestException as exc:
        # Qui non è arrivata nessuna risposta: DNS, TLS, timeout, connessione
        # chiusa. Non è un verdetto sulla pagina, è l'assenza di un verdetto, e
        # vale per qualsiasi host. Il 28/09 blackline.com ha dato ConnectionError
        # alle 11:39 dopo un 200 quattro ore prima e in tutti i controlli
        # precedenti: chiamarlo "rotto" ha degradato un link valido, e sarebbe
        # rimasto così una settimana, fino al controllo del lunedì dopo.
        return {"stato": 0, "esito": "bloccato", "ok": True,
                "errore": type(exc).__name__, "controllato_il": iso(now_utc())}


def raccogli_link(vendors: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for v in vendors:
        for url in (v.get("link") or {}).values():
            if isinstance(url, str) and url.startswith("http"):
                urls.append(url)
    return sorted(set(urls))


def check_links(urls: list[str], workers: int = 8,
                host_incerti: list[str] | None = None) -> dict[str, Any]:
    session = build_session()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        esiti = list(pool.map(
            lambda u: _check(session, u, incerto=host_incerto(u, host_incerti)), urls))
    return dict(zip(urls, esiti))
