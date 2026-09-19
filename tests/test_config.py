from sapnews.config import load_config

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
