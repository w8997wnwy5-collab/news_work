"""Helper condivisi: costruiscono feed RSS/Atom finti con date relative a oggi.

Le fixture sono generate al volo invece di essere file committati: così non
"invecchiano" e i test restano validi anche fra un anno.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROGETTO = Path(__file__).resolve().parents[1]


def rss(voci: list[dict], titolo: str = "Feed di prova") -> str:
    def item(v):
        quando = datetime.now(timezone.utc) - timedelta(hours=v.get("ore_fa", 2))
        return f"""  <item>
    <title>{v['titolo']}</title>
    <link>{v['url']}</link>
    <description><![CDATA[{v.get('sommario', '')}]]></description>
    <pubDate>{format_datetime(quando)}</pubDate>
  </item>"""

    corpo = "\n".join(item(v) for v in voci)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>{titolo}</title>
  <link>https://esempio.test</link>
{corpo}
</channel></rss>
"""


@pytest.fixture
def progetto(tmp_path: Path) -> Path:
    """Copia di lavoro del progetto: i test non scrivono mai su docs/ o data/ reali."""
    radice = tmp_path / "progetto"
    (radice / "config").mkdir(parents=True)
    for nome in ("sources.yaml", "taxonomy.yaml", "vendors.yaml"):
        shutil.copyfile(PROGETTO / "config" / nome, radice / "config" / nome)
    return radice


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    d = tmp_path / "feeds"
    d.mkdir()
    return d
