from sapnews.config import load_config
from sapnews.links import esito_da_stato, host_incerto

from conftest import PROGETTO


def test_la_configurazione_reale_e_coerente():
    cfg = load_config(PROGETTO)
    assert cfg.validate() == []


def test_ogni_categoria_ha_un_colore_assegnato():
    cfg = load_config(PROGETTO)
    payload = cfg.categories_payload()
    assert len(payload) == len(cfg.categories)
    for c in payload:
        assert c["colore"].startswith("#") and c["colore_dark"].startswith("#")


def test_errori_di_configurazione_vengono_segnalati():
    cfg = load_config(PROGETTO)
    cfg.sources["sources"].append({"id": "rotta", "nome": "Rotta", "tipo": "boh", "url": ""})
    errori = cfg.validate()
    assert any("rotta" in e for e in errori)


def test_un_404_da_host_incerto_non_e_un_verdetto():
    """LinkedIn risponde allo stesso indirizzo 200, 999 o 404 a pochi minuti di
    distanza: un errore lì non prova che la pagina sia sparita, e trattarlo come
    rotto ha già portato a cancellare due link validi dal catalogo."""
    incerti = ["linkedin.com"]

    assert host_incerto("https://www.linkedin.com/company/acme", incerti)
    assert host_incerto("https://linkedin.com/company/acme", incerti)
    assert not host_incerto("https://www.acme.com/linkedin.com", incerti)
    assert not host_incerto("https://acme.com/demo", incerti)

    # Stesso codice, verdetto diverso a seconda di chi lo restituisce.
    assert esito_da_stato(404, incerto=True) == "bloccato"
    assert esito_da_stato(404, incerto=False) == "rotto"
    assert esito_da_stato(500, incerto=True) == "bloccato"

    # Quello che già funzionava non cambia.
    assert esito_da_stato(200) == "ok"
    assert esito_da_stato(999) == "bloccato"
    assert esito_da_stato(403) == "bloccato"


def test_linkedin_e_dichiarato_host_incerto_nella_configurazione_reale():
    cfg = load_config(PROGETTO)
    assert "linkedin.com" in cfg.host_incerti
