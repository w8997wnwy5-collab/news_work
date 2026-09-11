"""Classificazione e punteggio di rilevanza rispetto alla nostra soluzione.

Il punteggio nasce da quattro contributi, tutti dichiarati nello YAML:

    credibilità della fonte   (config/sources.yaml -> peso)
  + aderenza alle categorie    (config/taxonomy.yaml -> categories[].keywords)
  + aderenza al nostro stack   (config/taxonomy.yaml -> profile.boost / penalize)
  + freschezza                 (bonus decrescente con l'età della notizia)

Il risultato viene tagliato a 0-100 e tradotto in un livello leggibile
(Da leggere / Da monitorare / Info) usando profile.soglie.
"""

from __future__ import annotations

import re
from datetime import timedelta
from functools import lru_cache
from typing import Any, Iterable
from urllib.parse import quote_plus

from .models import Item, now_utc, parse_iso

CAP_CATEGORIA = 30      # quanto può pesare al massimo l'insieme delle keyword
CAP_PROFILO = 40        # quanto può pesare al massimo l'aderenza allo stack

# Parole troppo generiche per finire nella spiegazione "perché ti riguarda".
_STOPWORDS_MATCH = {"erp", "release", "integration", "tax"}


@lru_cache(maxsize=2048)
def _pattern(term: str) -> re.Pattern[str]:
    """`btp` non deve agganciarsi dentro `abtpx`; `s/4hana` non ha confini \\b utili."""
    esc = re.escape(term.strip().lower())
    if term.strip().isalnum():
        return re.compile(rf"\b{esc}\b", re.I)
    return re.compile(rf"(?<![\w/]){esc}(?![\w])", re.I)


def _hits(testo: str, voci: Iterable[dict[str, Any]]) -> tuple[int, list[str]]:
    totale = 0
    trovati: list[str] = []
    for voce in voci or []:
        term = str(voce.get("term", "")).strip()
        if not term:
            continue
        if _pattern(term).search(testo):
            totale += int(voce.get("weight", 0))
            trovati.append(term.strip())
    return totale, trovati


def _bonus_freschezza(item: Item) -> int:
    pubblicato = parse_iso(item.pubblicato)
    if not pubblicato:
        return 0
    eta = now_utc() - pubblicato
    if eta < timedelta(hours=24):
        return 10
    if eta < timedelta(days=3):
        return 6
    if eta < timedelta(days=7):
        return 2
    return 0


def _linkedin_query(titolo: str) -> str:
    """Query LinkedIn costruita sulle parole portanti del titolo."""
    parole = re.findall(r"[\w/&\.-]+", titolo)
    utili = [p for p in parole if len(p) > 2][:9]
    return quote_plus(" ".join(utili) or titolo)


def classify(item: Item, source_weight: int, taxonomy: dict[str, Any]) -> Item:
    testo = f"{item.titolo}. {item.sommario}"
    profilo = taxonomy.get("profile", {}) or {}

    # --- categorie -------------------------------------------------------
    punteggi: list[tuple[int, str, list[str]]] = []
    for cat in taxonomy.get("categories", []):
        if not cat.get("keywords"):
            continue
        punti, trovati = _hits(testo, cat["keywords"])
        if punti > 0:
            punteggi.append((punti, cat["id"], trovati))
    punteggi.sort(key=lambda x: -x[0])

    categorie = [cid for punti, cid, _ in punteggi if punti >= 8][:3]
    if not categorie:
        categorie = [punteggi[0][1]] if punteggi else ["altro"]

    match_categoria: list[str] = []
    for punti, cid, trovati in punteggi:
        if cid in categorie:
            match_categoria.extend(trovati)
    punti_categoria = min(sum(p for p, cid, _ in punteggi if cid in categorie), CAP_CATEGORIA)

    # --- aderenza al nostro stack ---------------------------------------
    punti_boost, match_boost = _hits(testo, profilo.get("boost"))
    punti_boost = min(punti_boost, CAP_PROFILO)
    punti_penalita, _ = _hits(testo, profilo.get("penalize"))

    score = source_weight + punti_categoria + punti_boost + punti_penalita + _bonus_freschezza(item)
    item.score = max(0, min(100, int(score)))

    soglie = profilo.get("soglie", {}) or {}
    if item.score >= int(soglie.get("must", 60)):
        item.livello = "must"
    elif item.score >= int(soglie.get("watch", 35)):
        item.livello = "watch"
    else:
        item.livello = "info"

    # --- spiegazione e link di approfondimento ---------------------------
    ordinati = sorted(set(match_boost) | set(match_categoria),
                      key=lambda t: (t not in match_boost, t))
    item.categorie = categorie
    item.match = [t for t in ordinati if t not in _STOPWORDS_MATCH][:6]

    q = _linkedin_query(item.titolo)
    item.link_linkedin = (
        "https://www.linkedin.com/search/results/content/"
        f"?keywords={q}&sortBy=%22date_posted%22"
    )
    cat_principale = next((c for c in taxonomy.get("categories", [])
                           if c["id"] == categorie[0]), None)
    item.link_sap_help = (cat_principale or {}).get("sap_help") or "https://help.sap.com"
    return item


def classify_all(items: list[Item], sources: list[dict[str, Any]],
                 taxonomy: dict[str, Any]) -> list[Item]:
    pesi = {s["id"]: int(s.get("peso", 10)) for s in sources}
    min_score = int((taxonomy.get("profile", {}) or {}).get("min_score", 0))
    fuori: list[Item] = []
    for item in items:
        classify(item, pesi.get(item.fonte_id, 10), taxonomy)
        if item.score >= min_score:
            fuori.append(item)
    return fuori
