"""Lettura dei feed RSS/Atom, con fallback e diagnostica per fonte."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Item, SourceHealth, canonical_url, iso, make_id, now_utc

log = logging.getLogger("sapnews.fetch")

UA = ("Mozilla/5.0 (compatible; SAP-News-Radar/1.0; "
      "+https://github.com/w8997wnwy5-collab/news_work)")


def build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1.5,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET", "HEAD"]))
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
    return s


def _clean(html: str, limit: int = 420) -> str:
    """Sommario leggibile: via i tag, via gli spazi doppi, taglio su parola."""
    import html as html_mod
    import re

    testo = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    testo = re.sub(r"<[^>]+>", " ", testo)
    testo = html_mod.unescape(testo)
    testo = re.sub(r"\s+", " ", testo).strip()
    if len(testo) <= limit:
        return testo
    taglio = testo[:limit].rsplit(" ", 1)[0]
    return taglio + "…"


def _published(entry: Any) -> str | None:
    import calendar
    from datetime import datetime, timezone

    for campo in ("published_parsed", "updated_parsed", "created_parsed"):
        st = getattr(entry, campo, None)
        if st:
            try:
                return iso(datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc))
            except (ValueError, OverflowError):
                continue
    return None


def _passa_filtro(entry_text: str, termini: Iterable[str] | None) -> bool:
    if not termini:
        return True
    basso = entry_text.lower()
    return any(t.lower() in basso for t in termini)


def parse_feed(testo: str, source: dict[str, Any], max_items: int) -> tuple[list[Item], int]:
    """Trasforma il corpo di un feed negli Item grezzi (non ancora classificati)."""
    feed = feedparser.parse(testo)
    items: list[Item] = []
    scartati = 0
    for entry in feed.entries[: max_items * 3]:
        url = (getattr(entry, "link", "") or "").strip()
        titolo = _clean(getattr(entry, "title", "") or "", 240)
        if not url or not titolo:
            scartati += 1
            continue
        sommario = _clean(
            getattr(entry, "summary", "")
            or (getattr(entry, "content", [{}])[0].get("value", "") if getattr(entry, "content", None) else "")
        )
        if not _passa_filtro(f"{titolo} {sommario}", source.get("solo_se")):
            scartati += 1
            continue
        items.append(Item(
            id=make_id(url, titolo),
            titolo=titolo,
            url=canonical_url(url),
            fonte=source["nome"],
            fonte_id=source["id"],
            tipo_fonte=source["tipo"],
            pubblicato=_published(entry),
            sommario=sommario,
            autore=_clean(getattr(entry, "author", "") or "", 80),
            vendor=source.get("vendor"),
        ))
        if len(items) >= max_items:
            break
    return items, scartati


def fetch_source(source: dict[str, Any], session: requests.Session,
                 defaults: dict[str, Any]) -> tuple[list[Item], SourceHealth]:
    """Prova url principale e fallback; restituisce gli item e lo stato della fonte."""
    max_items = int(source.get("max_items", defaults.get("max_items", 25)))
    timeout = int(source.get("timeout", defaults.get("timeout", 20)))
    salute = SourceHealth(id=source["id"], nome=source["nome"], tipo=source["tipo"],
                          url=source["url"], ultimo_tentativo=iso(now_utc()))

    candidati = [source["url"], *(source.get("fallback") or [])]
    ultimo_errore = ""
    for url in candidati:
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code >= 400:
                ultimo_errore = f"HTTP {r.status_code}"
                continue
            items, scartati = parse_feed(r.text, source, max_items)
            if not items:
                ultimo_errore = "feed vuoto o nessun elemento utile"
                continue
            salute.ok = True
            salute.stato = f"HTTP {r.status_code}"
            salute.elementi = len(items)
            salute.scartati = scartati
            salute.url_usato = url
            salute.ultimo_ok = salute.ultimo_tentativo
            return items, salute
        except requests.RequestException as exc:
            ultimo_errore = type(exc).__name__
            log.warning("fonte %s: %s su %s", source["id"], ultimo_errore, url)

    salute.stato = ultimo_errore or "nessun url disponibile"
    salute.url_usato = candidati[-1] if candidati else ""
    return [], salute


def fetch_from_fixtures(source: dict[str, Any], directory: Path,
                        defaults: dict[str, Any]) -> tuple[list[Item], SourceHealth]:
    """Variante offline: legge `<directory>/<source_id>.xml` invece della rete.

    Serve ai test e a provare la pipeline in ambienti senza egress.
    """
    max_items = int(source.get("max_items", defaults.get("max_items", 25)))
    salute = SourceHealth(id=source["id"], nome=source["nome"], tipo=source["tipo"],
                          url=source["url"], ultimo_tentativo=iso(now_utc()))
    percorso = directory / f"{source['id']}.xml"
    if not percorso.exists():
        salute.stato = "fixture assente"
        return [], salute
    items, scartati = parse_feed(percorso.read_text(encoding="utf-8"), source, max_items)
    salute.ok = bool(items)
    salute.stato = "fixture" if items else "fixture senza elementi utili"
    salute.elementi = len(items)
    salute.scartati = scartati
    salute.url_usato = str(percorso)
    salute.ultimo_ok = salute.ultimo_tentativo if items else None
    return items, salute


def fetch_all(sources: list[dict[str, Any]], defaults: dict[str, Any],
              fixtures: Path | None = None,
              workers: int = 8) -> tuple[list[Item], list[SourceHealth]]:
    """Legge tutte le fonti in parallelo. Una fonte rotta non ferma le altre."""
    if fixtures is not None:
        risultati = [fetch_from_fixtures(s, fixtures, defaults) for s in sources]
    else:
        session = build_session()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            risultati = list(pool.map(lambda s: fetch_source(s, session, defaults), sources))

    items: list[Item] = []
    salute: list[SourceHealth] = []
    for lista, stato in risultati:
        items.extend(lista)
        salute.append(stato)
    return items, salute
