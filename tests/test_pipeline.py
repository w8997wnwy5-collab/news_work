"""Test end-to-end della pipeline, completamente offline (feed da fixture)."""

from __future__ import annotations

import json
from pathlib import Path

from sapnews.cli import main
from sapnews.fetch import parse_feed
from sapnews.models import Item, canonical_url, make_id
from sapnews.store import Store

from conftest import rss


def _scrivi_feed(dir_fixture: Path) -> None:
    (dir_fixture / "sap_news_center.xml").write_text(rss([
        {"titolo": "SAP annuncia il nuovo feature pack di S/4HANA",
         "url": "https://news.sap.com/2026/09/feature-pack/",
         "sommario": "Novità per i clienti private cloud e on-premise, con focus clean core.",
         "ore_fa": 3},
        {"titolo": "SAP Business Data Cloud amplia l'integrazione con Datasphere",
         "url": "https://news.sap.com/2026/09/bdc-datasphere/",
         "sommario": "Analytics e AI sui dati SAP.", "ore_fa": 20},
    ]), encoding="utf-8")

    (dir_fixture / "sap_community_tech.xml").write_text(rss([
        {"titolo": "Trasportare gli iFlow di Integration Suite tra tenant",
         "url": "https://community.sap.com/blog/iflow-transport",
         "sommario": "Guida pratica al DevOps su SAP BTP Cloud Integration.", "ore_fa": 6},
    ]), encoding="utf-8")

    (dir_fixture / "onapsis_blog.xml").write_text(rss([
        {"titolo": "SAP Patch Day: analisi delle security note critiche",
         "url": "https://onapsis.com/blog/patch-day",
         "sommario": "Vulnerabilità con CVSS elevato sui sistemi ABAP.", "ore_fa": 10},
    ]), encoding="utf-8")

    # Fonte generalista: solo la prima voce parla di SAP, l'altra va scartata.
    (dir_fixture / "diginomica.xml").write_text(rss([
        {"titolo": "Cosa cambia per i clienti SAP S/4HANA nel 2027",
         "url": "https://diginomica.com/sap-2027", "sommario": "Manutenzione e roadmap.", "ore_fa": 30},
        {"titolo": "Salesforce annuncia risultati trimestrali",
         "url": "https://diginomica.com/salesforce-q3",
         "sommario": "Crescita oltre le attese nel cloud CRM.", "ore_fa": 5},
    ]), encoding="utf-8")


def test_pipeline_completa_genera_dashboard_e_digest(progetto: Path, fixtures: Path):
    _scrivi_feed(fixtures)

    rc = main(["--root", str(progetto), "update", "--fixtures", str(fixtures)])
    assert rc == 0

    storico = json.loads((progetto / "data" / "news.json").read_text(encoding="utf-8"))
    assert len(storico["items"]) >= 5

    payload = json.loads((progetto / "docs" / "data" / "news.json").read_text(encoding="utf-8"))
    titoli = [i["titolo"] for i in payload["items"]]
    assert any("feature pack" in t for t in titoli)
    assert not any("Salesforce" in t for t in titoli), "il filtro solo_se non ha scartato il fuori tema"

    # La dashboard è la shell statica: deve esistere e sapere dove prendere i dati.
    index = (progetto / "docs" / "index.html").read_text(encoding="utf-8")
    assert "data/news.json" in index

    digest = (progetto / "docs" / "digest.md").read_text(encoding="utf-8")
    assert "Radar SAP" in digest and "linkedin.com" in digest

    # Le fonti senza fixture risultano non raggiungibili, non fanno cadere il giro.
    fonti = {f["id"]: f for f in payload["fonti"]}
    assert fonti["sap_news_center"]["ok"] is True
    assert fonti["reddit_sap"]["ok"] is False
    assert payload["stats"]["fonti_ok"] == 4


def test_secondo_giro_non_duplica_e_conserva_la_prima_visione(progetto: Path, fixtures: Path):
    _scrivi_feed(fixtures)
    main(["--root", str(progetto), "update", "--fixtures", str(fixtures)])
    primo = json.loads((progetto / "docs" / "data" / "news.json").read_text(encoding="utf-8"))

    main(["--root", str(progetto), "update", "--fixtures", str(fixtures)])
    secondo = json.loads((progetto / "docs" / "data" / "news.json").read_text(encoding="utf-8"))

    assert len(primo["items"]) == len(secondo["items"])
    per_id = {i["id"]: i for i in secondo["items"]}
    for i in primo["items"]:
        assert per_id[i["id"]]["visto_il"] == i["visto_il"]


def test_configurazione_incoerente_blocca_l_aggiornamento(progetto: Path, fixtures: Path, caplog):
    percorso = progetto / "config" / "vendors.yaml"
    percorso.write_text(percorso.read_text(encoding="utf-8").replace(
        "categoria: security", "categoria: inesistente", 1), encoding="utf-8")
    assert main(["--root", str(progetto), "update", "--fixtures", str(fixtures)]) == 2


def test_url_equivalenti_producono_lo_stesso_id():
    a = make_id("https://news.sap.com/post/?utm_source=newsletter", "T")
    b = make_id("https://news.sap.com/post", "T")
    assert a == b
    assert canonical_url("https://NEWS.sap.com/Post/") == "https://news.sap.com/Post"


def test_il_filtro_solo_se_scarta_le_voci_fuori_tema():
    feed = rss([
        {"titolo": "SAP e la supply chain", "url": "https://x.test/1"},
        {"titolo": "Novità su Oracle Fusion", "url": "https://x.test/2"},
    ])
    items, scartati = parse_feed(feed, {"id": "t", "nome": "T", "tipo": "press",
                                        "solo_se": ["sap"]}, max_items=10)
    assert [i.titolo for i in items] == ["SAP e la supply chain"]
    assert scartati == 1


def test_lo_storico_scarta_le_notizie_troppo_vecchie(tmp_path: Path):
    from datetime import timedelta
    from sapnews.models import iso, now_utc

    store = Store(tmp_path / "news.json").load()
    vecchia = Item(id="v", titolo="Vecchia", url="https://x.test/v", fonte="T", fonte_id="t",
                   tipo_fonte="press", pubblicato=iso(now_utc() - timedelta(days=200)))
    nuova = Item(id="n", titolo="Nuova", url="https://x.test/n", fonte="T", fonte_id="t",
                 tipo_fonte="press", pubblicato=iso(now_utc()))
    store.merge([vecchia, nuova])
    assert [i.id for i in store.items] == ["n"]


def test_uno_storico_corrotto_non_blocca_il_giro(tmp_path: Path):
    percorso = tmp_path / "news.json"
    percorso.write_text("{non json", encoding="utf-8")
    store = Store(percorso).load()
    assert store.dati["items"] == []
