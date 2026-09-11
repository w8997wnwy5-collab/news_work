"""Persistenza dello storico in data/news.json.

Lo storico è un file JSON versionato in git: il diff quotidiano mostra
esattamente quali notizie sono entrate, ed è interrogabile con `jq` senza
dipendere dalla dashboard.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from .models import Item, SourceHealth, iso, now_utc, parse_iso

SCHEMA = 1
RETENTION_GIORNI = 60
MAX_ITEMS = 900


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.dati: dict[str, Any] = {"schema": SCHEMA, "items": [], "fonti": {},
                                     "link_health": {}, "aggiornato_il": None}

    # ---- I/O ------------------------------------------------------------
    def load(self) -> "Store":
        if self.path.exists():
            try:
                self.dati = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # Uno storico corrotto non deve bloccare l'aggiornamento del giorno.
                pass
        self.dati.setdefault("items", [])
        self.dati.setdefault("fonti", {})
        self.dati.setdefault("link_health", {})
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dati["schema"] = SCHEMA
        self.path.write_text(
            json.dumps(self.dati, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
            encoding="utf-8")

    # ---- contenuto ------------------------------------------------------
    @property
    def items(self) -> list[Item]:
        return [Item.from_dict(raw) for raw in self.dati.get("items", [])]

    def merge(self, nuovi: list[Item]) -> tuple[int, int]:
        """Unisce il giro odierno con lo storico. Ritorna (nuove, aggiornate)."""
        adesso = iso(now_utc())
        esistenti = {raw["id"]: raw for raw in self.dati.get("items", [])}
        n_nuove = n_agg = 0

        for item in nuovi:
            precedente = esistenti.get(item.id)
            if precedente:
                item.visto_il = precedente.get("visto_il") or adesso
                # La data di pubblicazione nota vince su un feed che la omette.
                item.pubblicato = item.pubblicato or precedente.get("pubblicato")
                n_agg += 1
            else:
                item.visto_il = adesso
                n_nuove += 1
            item.aggiornato_il = adesso
            esistenti[item.id] = item.to_dict()

        limite = now_utc() - timedelta(days=RETENTION_GIORNI)

        def _quando(raw: dict[str, Any]):
            return parse_iso(raw.get("pubblicato")) or parse_iso(raw.get("visto_il")) or limite

        vivi = [raw for raw in esistenti.values() if _quando(raw) >= limite]
        vivi.sort(key=_quando, reverse=True)
        self.dati["items"] = vivi[:MAX_ITEMS]
        self.dati["aggiornato_il"] = adesso
        return n_nuove, n_agg

    def update_health(self, salute: list[SourceHealth]) -> None:
        """Conserva l'ultimo successo noto anche quando il giro corrente fallisce."""
        registro = self.dati.setdefault("fonti", {})
        for s in salute:
            precedente = registro.get(s.id, {})
            if not s.ultimo_ok:
                s.ultimo_ok = precedente.get("ultimo_ok")
            registro[s.id] = asdict(s)

    def prune_health(self, id_configurati: set[str]) -> list[str]:
        """Dimentica le fonti tolte dalla configurazione: il pannello Controllo
        deve mostrare il panorama attuale, non quello di sei mesi fa."""
        registro = self.dati.setdefault("fonti", {})
        rimosse = [k for k in registro if k not in id_configurati]
        for k in rimosse:
            del registro[k]
        return rimosse

    def set_link_health(self, risultati: dict[str, Any]) -> None:
        self.dati["link_health"] = {"controllato_il": iso(now_utc()), "link": risultati}
