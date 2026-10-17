"""SAP News Radar - radar giornaliero di notizie SAP e tool di ecosistema.

Il flusso è sempre lo stesso:

    config/  ->  fetch  ->  classify  ->  store  ->  render  ->  docs/

Ogni passo vive in un modulo dedicato e non conosce i dettagli degli altri,
così aggiungere una fonte o una categoria resta un'operazione di solo YAML.
"""

__version__ = "1.0.0"
