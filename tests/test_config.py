import requests

from sapnews.config import load_config
from sapnews.links import _check, esito_da_stato, host_incerto

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

def test_una_connessione_fallita_non_e_un_verdetto_su_nessun_host():
    """Il 28/09 blackline.com ha dato ConnectionError alle 11:39 dopo un 200
    quattro ore prima e in ogni controllo precedente. Una risposta che non arriva
    non dice nulla sulla pagina: se diventa "rotto", la dashboard ripiega sul
    sito ufficiale per un link valido e ci resta fino al lunedì dopo."""

    class SessioneMorta:
        def head(self, *a, **k):
            raise requests.ConnectionError("nome non risolto")

    esito = _check(SessioneMorta(), "https://www.blackline.com")
    assert esito["esito"] == "bloccato"
    assert esito["ok"] is True
    assert esito["stato"] == 0
    assert esito["errore"] == "ConnectionError"

    # Vale anche sugli host già dichiarati incerti, e per un timeout.
    class SessioneLenta:
        def head(self, *a, **k):
            raise requests.Timeout("troppo lenta")

    lento = _check(SessioneLenta(), "https://www.linkedin.com/company/acme",
                   incerto=True)
    assert lento["esito"] == "bloccato"
    assert lento["ok"] is True
