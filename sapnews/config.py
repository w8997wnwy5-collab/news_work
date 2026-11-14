"""Caricamento della configurazione YAML (fonti, tassonomia, vendor)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Palette categoriale validata (vedi README, sezione "Colori"). Lo slot 0 è il
# grigio neutro usato dalla categoria di ripiego.
SLOT_LIGHT = ["#898781", "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
              "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SLOT_DARK = ["#898781", "#3987e5", "#d95926", "#199e70", "#c98500",
             "#d55181", "#008300", "#9085e9", "#e66767"]

TIPI_FONTE = {
    "official": "SAP ufficiale",
    "community": "Community",
    "press": "Stampa & analisti",
    "vendor": "Vendor & partner",
}


@dataclass
class Config:
    root: Path
    sources: dict[str, Any]
    taxonomy: dict[str, Any]
    vendors: dict[str, Any]

    # ---- scorciatoie ----------------------------------------------------
    @property
    def source_list(self) -> list[dict[str, Any]]:
        return self.sources.get("sources", [])

    @property
    def source_defaults(self) -> dict[str, Any]:
        return self.sources.get("defaults", {}) or {}

    @property
    def categories(self) -> list[dict[str, Any]]:
        return self.taxonomy.get("categories", [])

    @property
    def profile(self) -> dict[str, Any]:
        return self.taxonomy.get("profile", {}) or {}

    @property
    def vendor_list(self) -> list[dict[str, Any]]:
        return self.vendors.get("vendors", [])

    @property
    def host_incerti(self) -> list[str]:
        """Host il cui codice di errore non dice nulla sullo stato della pagina."""
        return self.vendors.get("host_incerti", []) or []

    def vendor_by_id(self, vid: str | None) -> dict[str, Any] | None:
        if not vid:
            return None
        return next((v for v in self.vendor_list if v["id"] == vid), None)

    def categories_payload(self) -> list[dict[str, Any]]:
        """Metadati delle categorie così come li consuma la dashboard."""
        out = []
        for c in self.categories:
            slot = int(c.get("color_slot", 0)) % len(SLOT_LIGHT)
            out.append({
                "id": c["id"],
                "nome": c["nome"],
                "descrizione": c.get("descrizione", ""),
                "icona": c.get("icona", "dot"),
                "sap_help": c.get("sap_help", ""),
                "colore": SLOT_LIGHT[slot],
                "colore_dark": SLOT_DARK[slot],
            })
        return out

    # ---- validazione ----------------------------------------------------
    def validate(self) -> list[str]:
        """Errori bloccanti di configurazione, restituiti come lista di messaggi."""
        errori: list[str] = []
        cat_ids = {c["id"] for c in self.categories}
        if "altro" not in cat_ids:
            errori.append("config/taxonomy.yaml: manca la categoria di ripiego 'altro'")

        visti: set[str] = set()
        for s in self.source_list:
            for chiave in ("id", "nome", "tipo", "url"):
                if not s.get(chiave):
                    errori.append(f"fonte {s.get('id', '?')}: campo '{chiave}' mancante")
            if s.get("id") in visti:
                errori.append(f"fonte {s['id']}: id duplicato")
            visti.add(s.get("id"))
            if s.get("tipo") not in TIPI_FONTE:
                errori.append(f"fonte {s.get('id')}: tipo '{s.get('tipo')}' non valido")
            if s.get("vendor") and not self.vendor_by_id(s["vendor"]):
                errori.append(f"fonte {s['id']}: vendor '{s['vendor']}' non in vendors.yaml")

        for v in self.vendor_list:
            if v.get("categoria") not in cat_ids:
                errori.append(f"vendor {v.get('id')}: categoria '{v.get('categoria')}' sconosciuta")
            if not (v.get("link") or {}).get("sito"):
                errori.append(f"vendor {v.get('id')}: manca link.sito")
        return errori


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"file di configurazione mancante: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(root: str | Path = ".") -> Config:
    root = Path(root).resolve()
    cfg_dir = root / "config"
    return Config(
        root=root,
        sources=_load(cfg_dir / "sources.yaml"),
        taxonomy=_load(cfg_dir / "taxonomy.yaml"),
        vendors=_load(cfg_dir / "vendors.yaml"),
    )
