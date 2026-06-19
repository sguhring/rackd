"""Example scraper stub for a used-equipment marketplace.

This is a SKELETON. Before implementing:
  1. Confirm the site's robots.txt / ToS permits automated access.
  2. Prefer any structured JSON the page embeds over parsing rendered HTML.
  3. JS-rendered listings need a headless browser — use the Playwright MCP server
     from Claude Code rather than plain requests.

See docs/DATA_SOURCES.md for candidate sources and which brands to prioritise.
"""
from __future__ import annotations

from typing import Iterator

from .base import RawMachine, Scraper


class MarketplaceScraper(Scraper):
    source = "marketplace-example"

    # Map the brands we care about to the site's brand-filter URLs.
    BRAND_URLS: dict[str, str] = {
        # "Hammer Strength": "https://example.com/collections/hammer-strength",
        # "Technogym": "https://example.com/collections/technogym",
    }

    def fetch(self) -> Iterator[RawMachine]:
        for brand, url in self.BRAND_URLS.items():
            for model, image in self._models_for(brand, url):
                yield self.make(brand, model, image_url=image)

    def _models_for(self, brand: str, url: str) -> Iterator[tuple[str, str | None]]:
        """TODO: fetch `url`, extract (model_name, image_url) per product card.

        With Playwright MCP from Claude Code:
          - navigate(url), wait for product grid, read each card's title + img.
        Return cleaned model names (strip the brand prefix if the title repeats it).
        """
        return iter(())  # not implemented yet
