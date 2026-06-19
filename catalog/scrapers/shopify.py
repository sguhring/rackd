"""Shopify storefront scraper — the primary catalog source.

Most commercial gym-equipment shops (shop.lifefitness.com, Fitness Superstore, …)
run on Shopify, which exposes a public, structured product feed at:

    https://<store>/products.json?limit=250&page=N            (whole store)
    https://<store>/collections/<handle>/products.json?...     (one collection)

This is an official JSON endpoint, not HTML scraping: it returns vendor (brand),
title (brand + model), product_type, tags and image URLs directly. We prefer it
over parsing rendered pages, per docs/DATA_SOURCES.md.

robots.txt note: shop.lifefitness.com disallows /cart, /checkout, sorted/filtered
collection URLs and a few traps — but NOT /collections/ or *.json. We only hit the
plain product feed, throttled, with a descriptive User-Agent.
"""
from __future__ import annotations

import time
from typing import Iterator

import httpx

import re

from .base import RawMachine, Scraper

USER_AGENT = "rackd-catalog/0.1 (+https://github.com/sguhring/rackd; gym machine catalog)"

# Substring signals (matched across product_type + tags, lowercased) that mark a
# product as a trackable strength machine. Stores vary wildly in tag vocabulary, so
# we match substrings, not exact tags. A strength signal keeps it; a cardio signal
# alone drops it (treadmills, bikes, ellipticals are not per-machine load tracking).
STRENGTH_SIGNALS = ("strength training", "strength machine", "selectorized", "pin loaded",
                    "plate loaded", "plate-loaded", "leverage", "gym system", "multi stack",
                    "machine")
CARDIO_SIGNALS = ("cardio", "treadmill", "elliptical", "exercise bike", "recumbent",
                  "upright bike", "rower", "rowing", "stair", "climbmill", "ascent trainer")

# Title noise to strip when deriving a clean model name (reseller listings).
_CONSOLE = re.compile(r"\s*w/.*?console", re.I)
_PARENS = re.compile(r"\s*\((remanufactured|refurbished|newer style|new|used|outlet|kg|"
                     r"floor model|open box)\)", re.I)
_OUTLET = re.compile(r"\s*-\s*outlet\b", re.I)


def clean_model(s: str) -> str:
    s = _CONSOLE.sub("", s)
    s = _PARENS.sub("", s)
    s = _OUTLET.sub("", s)
    return re.sub(r"\s{2,}", " ", s).strip(" -–—")


class ShopifyScraper(Scraper):
    """Pull machine models from a Shopify store's public product feed.

    Parameters
    ----------
    source      : source key stored on each RawMachine (e.g. 'shop-lifefitness').
    store       : base URL, e.g. 'https://shop.lifefitness.com'.
    collections : optional list of collection handles to limit the pull. If empty,
                  the whole store feed is paginated and filtered to machines.
    brands      : optional allow-list of vendor names (case-insensitive). If empty,
                  every vendor is kept.
    machines_only : when True (default) keep only products that look like trackable
                  strength machines (see MACHINE_TAGS / MACHINE_TYPES).
    """

    def __init__(self, source: str, store: str, *,
                 collections: list[str] | None = None,
                 brands: list[str] | None = None,
                 machines_only: bool = True,
                 delay: float = 1.0, page_size: int = 250) -> None:
        self.source = source
        self.store = store.rstrip("/")
        self.collections = collections or []
        self.brands = {b.lower() for b in (brands or [])}
        self.machines_only = machines_only
        self.delay = delay
        self.page_size = page_size

    # --- public API -------------------------------------------------------
    def fetch(self) -> Iterator[RawMachine]:
        seen: set[tuple[str, str]] = set()
        feeds = (
            [f"{self.store}/collections/{h}" for h in self.collections]
            if self.collections else [self.store]
        )
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30,
                          follow_redirects=True) as client:
            for feed in feeds:
                for product in self._paginate(client, feed):
                    rec = self._to_machine(product)
                    if rec is None:
                        continue
                    key = (rec.brand.lower(), rec.model.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    yield rec

    # --- internals --------------------------------------------------------
    def _paginate(self, client: httpx.Client, feed: str) -> Iterator[dict]:
        page = 1
        while True:
            url = f"{feed}/products.json"
            resp = client.get(url, params={"limit": self.page_size, "page": page})
            resp.raise_for_status()
            products = resp.json().get("products", [])
            if not products:
                return
            yield from products
            if len(products) < self.page_size:
                return
            page += 1
            time.sleep(self.delay)  # be polite

    def _to_machine(self, p: dict) -> RawMachine | None:
        vendor = (p.get("vendor") or "").strip()
        title = (p.get("title") or "").strip()
        if not vendor or not title:
            return None
        if self.brands and vendor.lower() not in self.brands:
            return None

        tags = [t.lower() for t in _as_list(p.get("tags"))]
        ptype = (p.get("product_type") or "").strip()
        if self.machines_only and not self._is_machine(tags, ptype):
            return None

        images = p.get("images") or []
        image_url = images[0].get("src") if images else None

        return self.make(
            vendor,
            clean_model(_strip_brand(title, vendor)),
            category=ptype or None,
            image_url=image_url,
            extra={"tags": tags, "handle": p.get("handle"), "title": title},
        )

    @staticmethod
    def _is_machine(tags: list[str], ptype: str) -> bool:
        hay = " ".join([ptype.lower(), *tags])
        if any(c in hay for c in CARDIO_SIGNALS):
            return False  # treadmills, bikes, rowers — not per-machine load tracking
        return any(s in hay for s in STRENGTH_SIGNALS)


def _as_list(tags) -> list[str]:
    """Shopify tags come as a list (.json) or a comma string (some themes)."""
    if isinstance(tags, list):
        return tags
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return []


def _strip_brand(title: str, vendor: str) -> str:
    """'Hammer Strength Plate-Loaded Iso-Lateral Row' -> 'Plate-Loaded Iso-Lateral Row'."""
    t = title.strip()
    if t.lower().startswith(vendor.lower()):
        t = t[len(vendor):].lstrip(" -–—")
    return t or title.strip()
