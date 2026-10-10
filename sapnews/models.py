"""Strutture dati condivise tra i vari passi della pipeline."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


_TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_cid|mc_eid|ref_?src)", re.I)


def canonical_url(url: str) -> str:
    """Toglie i parametri di tracciamento: due link identici diventano un id unico."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not _TRACKING.match(k)]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path,
                       urlencode(query), ""))


def make_id(url: str, title: str) -> str:
    base = canonical_url(url) or title.strip().lower()
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


@dataclass
class Item:
    """Una notizia normalizzata e classificata."""

    id: str
    titolo: str
    url: str
    fonte: str                      # nome leggibile della fonte
    fonte_id: str
    tipo_fonte: str                 # official | community | press | vendor
    pubblicato: str | None          # ISO 8601 UTC
    sommario: str = ""
    autore: str = ""
    categorie: list[str] = field(default_factory=list)
    match: list[str] = field(default_factory=list)   # termini che l'hanno agganciata
    score: int = 0
    livello: str = "info"           # must | watch | info
    vendor: str | None = None       # id vendor se la fonte è un vendor
    link_linkedin: str = ""
    link_sap_help: str = ""
    visto_il: str = ""              # prima volta che il radar l'ha vista
    aggiornato_il: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Item":
        campi = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in campi})


@dataclass
class SourceHealth:
    """Esito dell'ultima lettura di una fonte, mostrato nel pannello Controllo."""

    id: str
    nome: str
    tipo: str
    url: str
    ok: bool = False
    stato: str = ""                 # es. "200" oppure il messaggio di errore
    elementi: int = 0
    scartati: int = 0
    url_usato: str = ""
    suggerimento: str = ""          # url da mettere in config se trovato da solo
    ultimo_ok: str | None = None
    ultimo_tentativo: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
