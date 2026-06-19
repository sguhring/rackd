"""Base contract for catalog scrapers.

Each source (a marketplace or a manufacturer catalog) implements `Scraper.fetch()`
and yields RawMachine records. normalize.py maps those into the DB schema.

IMPORTANT: check each source's robots.txt / ToS before enabling it. See
docs/DATA_SOURCES.md. Prefer official feeds/JSON over HTML scraping where available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class RawMachine:
    """A machine model as pulled from a source, before normalization."""
    brand: str                       # 'Hammer Strength' (raw, may need cleaning)
    model: str                       # 'Iso-Lateral Chest Press'
    category: str | None = None      # source's own category label
    image_url: str | None = None
    source: str = ""                 # source key, e.g. 'fitness-superstore'
    extra: dict = field(default_factory=dict)


class Scraper:
    """Subclass per source. Keep network IO inside fetch()."""

    source: str = "base"

    def fetch(self) -> Iterator[RawMachine]:
        raise NotImplementedError

    # convenience for subclasses
    def make(self, brand: str, model: str, **kw) -> RawMachine:
        return RawMachine(brand=brand.strip(), model=model.strip(),
                          source=self.source, **kw)
