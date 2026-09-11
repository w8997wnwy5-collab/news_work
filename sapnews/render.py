"""Generazione degli output: dati per la dashboard, shell HTML e digest."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from .config import TIPI_FONTE, Config
from .models import Item, iso, now_utc, parse_iso

TEMPLATE = Path(__file__).parent / "templates" / "dashboard.html"


def _eta(item: Item):
    return parse_iso(item.pubblicato) or parse_iso(item.visto_il)


def build_payload(cfg: Config, items: list[Item], fonti: list[dict[str, Any]],
                  link_health: dict[str, Any]) -> dict[str, Any]:
    adesso = now_utc()
    ultime_24h = [i for i in items if (_eta(i) or adesso) >= adesso - timedelta(hours=24)]
    ultime_7g = [i for i in items if (_eta(i) or adesso) >= adesso - timedelta(days=7)]

    per_categoria = Counter()
    for i in items:
        for c in i.categorie:
            per_categoria[c] += 1

    stats = {
        "totale": len(items),
        "ultime_24h": len(ultime_24h),
        "ultime_7g": len(ultime_7g),
        "da_leggere": sum(1 for i in ultime_7g if i.livello == "must"),
        "per_categoria": dict(per_categoria),
        "per_tipo": dict(Counter(i.tipo_fonte for i in items)),
        "fonti_ok": sum(1 for f in fonti if f.get("ok")),
        "fonti_totali": len(fonti),
        "link_rotti": sum(1 for v in (link_health.get("link") or {}).values()
                          if not v.get("ok")),
    }

    return {
        "generato_il": iso(adesso),
        "profilo": {
            "nome": cfg.profile.get("name", ""),
            "descrizione": (cfg.profile.get("descrizione") or "").strip(),
            "soglie": cfg.profile.get("soglie", {}),
        },
        "categorie": cfg.categories_payload(),
        "tipi_fonte": TIPI_FONTE,
        "items": [i.to_dict() for i in items],
        "vendor": cfg.vendor_list,
        "hub": cfg.vendors.get("hub", {}),
        "fonti": fonti,
        "link_health": link_health,
        "stats": stats,
    }


def write_outputs(cfg: Config, payload: dict[str, Any]) -> list[Path]:
    """Scrive docs/data/news.json, docs/index.html e docs/digest.md."""
    docs = cfg.root / "docs"
    (docs / "data").mkdir(parents=True, exist_ok=True)

    dati = docs / "data" / "news.json"
    dati.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")

    index = docs / "index.html"
    shutil.copyfile(TEMPLATE, index)

    (docs / ".nojekyll").write_text("", encoding="utf-8")

    digest = docs / "digest.md"
    digest.write_text(build_digest(payload), encoding="utf-8")
    return [dati, index, digest]


def build_digest(payload: dict[str, Any], ore: int = 24, massimo: int = 20) -> str:
    """Digest testuale delle ultime ore, pronto da incollare in chat o mail."""
    adesso = now_utc()
    limite = adesso - timedelta(hours=ore)
    nomi = {c["id"]: c["nome"] for c in payload["categorie"]}

    def quando(raw):
        return parse_iso(raw.get("pubblicato")) or parse_iso(raw.get("visto_il")) or adesso

    recenti = [i for i in payload["items"] if quando(i) >= limite]
    recenti.sort(key=lambda i: (-i["score"], -quando(i).timestamp()))
    recenti = recenti[:massimo]

    righe = [
        f"# Radar SAP - {adesso.strftime('%d/%m/%Y')}",
        "",
        f"Profilo: {payload['profilo']['nome']}",
        f"Ultime {ore}h: {payload['stats']['ultime_24h']} notizie "
        f"({payload['stats']['da_leggere']} da leggere) da "
        f"{payload['stats']['fonti_ok']}/{payload['stats']['fonti_totali']} fonti attive.",
        "",
    ]
    if not recenti:
        righe.append("_Nessuna notizia nelle ultime ore._")
        return "\n".join(righe) + "\n"

    per_cat: dict[str, list[dict[str, Any]]] = {}
    for i in recenti:
        per_cat.setdefault(i["categorie"][0] if i["categorie"] else "altro", []).append(i)

    for cat, lista in sorted(per_cat.items(), key=lambda kv: -len(kv[1])):
        righe.append(f"## {nomi.get(cat, cat)}")
        righe.append("")
        for i in lista:
            marchio = {"must": "**[Da leggere]**", "watch": "[Da monitorare]"}.get(i["livello"], "")
            righe.append(f"- {marchio} [{i['titolo']}]({i['url']}) - _{i['fonte']}_ "
                         f"(rilevanza {i['score']}) - [post LinkedIn]({i['link_linkedin']})")
        righe.append("")
    return "\n".join(righe) + "\n"
