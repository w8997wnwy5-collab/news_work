from sapnews.classify import classify
from sapnews.config import load_config
from sapnews.models import Item, iso, now_utc

from conftest import PROGETTO


def _item(titolo: str, sommario: str = "", ore_fa: int = 2) -> Item:  # noqa: D401
    from datetime import timedelta

    return Item(id="x", titolo=titolo, url="https://esempio.test/a", fonte="Test",
                fonte_id="sap_news_center", tipo_fonte="official",
                pubblicato=iso(now_utc() - timedelta(hours=ore_fa)), sommario=sommario)


def _tax():
    return load_config(PROGETTO).taxonomy


def test_notizia_sul_nostro_stack_e_prioritaria():
    i = classify(_item("SAP rilascia il nuovo feature pack per S/4HANA private cloud",
                       "Novità su clean core e ABAP Cloud per i clienti RISE with SAP."),
                 20, _tax())
    assert i.livello == "must"
    assert "s4hana" in i.categorie
    assert i.score >= 60
    assert any("s/4hana" in m or "clean core" in m for m in i.match)


def test_prodotto_fuori_perimetro_scende_di_punteggio():
    dentro = classify(_item("Nuova release di SAP S/4HANA on-premise"), 20, _tax())
    fuori = classify(_item("Nuova release di SAP Business One per le PMI"), 20, _tax())
    assert fuori.score < dentro.score


def test_le_sigle_corte_non_agganciano_dentro_altre_parole():
    # "btp" non deve comparire per "subtpartner", "sod" non per "sodio".
    i = classify(_item("Il subtpartner del sodio nel settore alimentare"), 10, _tax())
    assert "btp" not in i.match
    assert "sod" not in i.match


def test_integrazione_finisce_nella_categoria_btp():
    i = classify(_item("Come testare gli iFlow di SAP Integration Suite",
                       "Guida al trasporto degli iFlow tra tenant di Cloud Integration."),
                 16, _tax())
    assert "btp_integration" in i.categorie


def test_notizia_senza_agganci_finisce_in_altro():
    i = classify(_item("Nominato il nuovo direttore marketing per l'area sud"), 10, _tax())
    assert i.categorie == ["altro"]


def test_la_freschezza_conta():
    fresca = classify(_item("SAP S/4HANA: nuova nota", ore_fa=1), 20, _tax())
    vecchia = classify(_item("SAP S/4HANA: nuova nota", ore_fa=24 * 20), 20, _tax())
    assert fresca.score > vecchia.score


def test_link_di_approfondimento_generati():
    i = classify(_item("SAP Datasphere e Business Data Cloud"), 20, _tax())
    assert i.link_linkedin.startswith("https://www.linkedin.com/search/results/content/")
    assert "Datasphere" in i.link_linkedin or "datasphere" in i.link_linkedin.lower()
    assert i.link_sap_help.startswith("https://")


def test_i_titoli_in_alfabeto_non_latino_restano_fuori():
    from sapnews.classify import classify_all, in_alfabeto_latino

    assert in_alfabeto_latino("SAP BTP: guida all'onboarding")
    assert in_alfabeto_latino("Rilascio S/4HANA 2026 - novità")
    assert not in_alfabeto_latino("SAP BTP 온보딩 가이드: 7가지 핵심 영역 완벽 정리")
    assert not in_alfabeto_latino("SAP S/4HANA への移行について")

    fonti = [{"id": "sap_community_tech", "peso": 16}]
    tenuti = classify_all(
        [_item("SAP BTP 온보딩 가이드: 핵심 영역 정리"), _item("SAP BTP onboarding: le aree chiave")],
        fonti, _tax())
    assert [i.titolo for i in tenuti] == ["SAP BTP onboarding: le aree chiave"]
