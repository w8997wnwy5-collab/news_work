"""Interfaccia a riga di comando del radar."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .fetch import fetch_all
from .classify import classify_all
from .links import check_links, raccogli_link
from .models import Item
from .render import build_payload, write_outputs
from .store import Store

log = logging.getLogger("sapnews")


def _store_path(root: Path) -> Path:
    return root / "data" / "news.json"


def _setup_log(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
    )


def cmd_update(args: argparse.Namespace) -> int:
    cfg = load_config(args.root)
    errori = cfg.validate()
    if errori:
        for e in errori:
            log.error("configurazione: %s", e)
        return 2

    sorgenti = cfg.source_list
    if args.only:
        richieste = set(args.only)
        sorgenti = [s for s in sorgenti if s["id"] in richieste]
        if not sorgenti:
            log.error("nessuna fonte corrisponde a %s", ", ".join(sorted(richieste)))
            return 2

    fixtures = Path(args.fixtures).resolve() if args.fixtures else None
    log.info("lettura di %d fonti%s", len(sorgenti), " (fixture offline)" if fixtures else "")
    grezzi, salute = fetch_all(sorgenti, cfg.source_defaults, fixtures=fixtures)

    ok = sum(1 for s in salute if s.ok)
    log.info("fonti raggiungibili: %d/%d - elementi grezzi: %d", ok, len(salute), len(grezzi))
    for s in salute:
        if not s.ok:
            log.warning("fonte non disponibile: %s (%s)", s.nome, s.stato)

    classificati = classify_all(grezzi, cfg.source_list, cfg.taxonomy)
    log.info("elementi rilevanti dopo la classificazione: %d", len(classificati))

    store = Store(_store_path(cfg.root)).load()
    nuove, aggiornate = store.merge(classificati)
    store.update_health(salute)
    dimenticate = store.prune_health({s["id"] for s in cfg.source_list})
    if dimenticate:
        log.info("fonti non più configurate, rimosse dallo stato: %s", ", ".join(dimenticate))
    log.info("storico: %d nuove, %d già note, %d totali",
             nuove, aggiornate, len(store.dati["items"]))

    if args.check_links:
        urls = raccogli_link(cfg.vendor_list)
        log.info("controllo di %d link vendor", len(urls))
        store.set_link_health(check_links(urls))

    if args.dry_run:
        log.info("dry-run: nessun file scritto")
        return 0

    store.save()
    payload = build_payload(cfg, store.items, list(store.dati["fonti"].values()),
                            store.dati.get("link_health", {}))
    scritti = write_outputs(cfg, payload)
    for p in scritti:
        log.info("scritto %s", p.relative_to(cfg.root))

    if ok == 0 and not fixtures:
        log.error("nessuna fonte raggiungibile: controllare rete o url in config/sources.yaml")
        return 1
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Rigenera dashboard e digest dallo storico, senza toccare la rete."""
    cfg = load_config(args.root)
    store = Store(_store_path(cfg.root)).load()
    payload = build_payload(cfg, store.items, list(store.dati.get("fonti", {}).values()),
                            store.dati.get("link_health", {}))
    for p in write_outputs(cfg, payload):
        log.info("scritto %s", p.relative_to(cfg.root))
    return 0


def cmd_check_links(args: argparse.Namespace) -> int:
    cfg = load_config(args.root)
    urls = raccogli_link(cfg.vendor_list)
    risultati = check_links(urls)
    rotti = {u: r for u, r in risultati.items() if not r.get("ok")}
    for u, r in sorted(rotti.items()):
        log.warning("link rotto (%s): %s", r.get("stato") or r.get("errore"), u)
    log.info("link controllati: %d - rotti: %d", len(risultati), len(rotti))

    store = Store(_store_path(cfg.root)).load()
    store.set_link_health(risultati)
    store.save()
    payload = build_payload(cfg, store.items, list(store.dati.get("fonti", {}).values()),
                            store.dati.get("link_health", {}))
    write_outputs(cfg, payload)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cfg = load_config(args.root)
    errori = cfg.validate()
    for e in errori:
        log.error("%s", e)
    if errori:
        return 2
    log.info("configurazione valida: %d fonti, %d categorie, %d vendor",
             len(cfg.source_list), len(cfg.categories), len(cfg.vendor_list))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    cfg = load_config(args.root)
    store = Store(_store_path(cfg.root)).load()
    payload = build_payload(cfg, store.items, list(store.dati.get("fonti", {}).values()),
                            store.dati.get("link_health", {}))
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Serve docs/ in locale: la dashboard legge i dati via fetch()."""
    import functools
    import http.server
    import socketserver

    cfg = load_config(args.root)
    docs = cfg.root / "docs"
    if not (docs / "index.html").exists():
        log.error("docs/index.html non esiste: lanciare prima `python -m sapnews update`")
        return 1
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(docs))
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        log.info("dashboard su http://localhost:%d  (Ctrl+C per uscire)", args.port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log.info("chiuso")
    return 0


def build_parser() -> argparse.ArgumentParser:
    # Opzioni valide sia prima sia dopo il sottocomando: `sapnews -v update` e
    # `sapnews update -v` devono funzionare entrambi. SUPPRESS evita che il
    # sottoparser azzeri il valore gia' impostato dal parser principale.
    comuni = argparse.ArgumentParser(add_help=False)
    comuni.add_argument("-v", "--verbose", action="store_true",
                        default=argparse.SUPPRESS, help="log di dettaglio")
    comuni.add_argument("--root", default=argparse.SUPPRESS,
                        help="radice del progetto (default: .)")

    p = argparse.ArgumentParser(
        prog="sapnews", parents=[comuni],
        description="Radar giornaliero di notizie SAP e tool di ecosistema.")
    p.add_argument("--version", action="version", version=f"sapnews {__version__}")
    sub = p.add_subparsers(dest="comando", required=True)

    u = sub.add_parser("update", parents=[comuni],
                       help="legge le fonti, classifica e rigenera la dashboard")
    u.add_argument("--dry-run", action="store_true", help="non scrive nulla su disco")
    u.add_argument("--only", nargs="+", metavar="ID", help="limita a queste fonti")
    u.add_argument("--fixtures", metavar="DIR",
                   help="legge i feed da file locali invece che dalla rete")
    u.add_argument("--check-links", action="store_true",
                   help="verifica anche i link del catalogo vendor")
    u.set_defaults(func=cmd_update)

    r = sub.add_parser("render", parents=[comuni], help="rigenera dashboard e digest dallo storico")
    r.set_defaults(func=cmd_render)

    c = sub.add_parser("check-links", parents=[comuni], help="verifica i link del catalogo vendor")
    c.set_defaults(func=cmd_check_links)

    v = sub.add_parser("validate", parents=[comuni], help="controlla la coerenza dei file in config/")
    v.set_defaults(func=cmd_validate)

    s = sub.add_parser("stats", parents=[comuni], help="stampa le statistiche correnti in JSON")
    s.set_defaults(func=cmd_stats)

    w = sub.add_parser("serve", parents=[comuni], help="apre la dashboard in locale")
    w.add_argument("--port", type=int, default=8000)
    w.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_log(getattr(args, "verbose", False))
    if not hasattr(args, "root"):
        args.root = "."
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
