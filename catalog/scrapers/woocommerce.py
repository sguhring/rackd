"""WooCommerce Store API scraper — for the reseller marketplaces on WordPress.

Most used/remanufactured marketplaces (Fitness Equipment Empire, Primo Fitness, …)
run on WooCommerce, which exposes a public, read-only JSON feed:

    https://<store>/wp-json/wc/store/v1/products?per_page=100&page=N
    https://<store>/wp-json/wc/store/v1/products/categories?per_page=100

Each product gives `name` (brand + model, with marketing noise), `categories`
(sometimes the brand, sometimes the type) and `images`. Unlike Shopify there is no
clean `vendor` field, so the brand is recovered with brands.extract_brand(), and the
strength-vs-cardio filtering uses brands.is_strength_machine() over name+categories.

These sites carry ~30 brands each (Life Fitness, Hammer Strength, Cybex, Precor,
Matrix, Nautilus, Hoist, Star Trac, Technogym, …) — the richest source for the catalog.
"""
from __future__ import annotations

import time
from typing import Iterator

import httpx

from brands import clean_model, extract_brand, is_strength_machine

from .base import RawMachine, Scraper

# WooCommerce + WordPress block default bot UAs; use a normal browser UA.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class WooCommerceScraper(Scraper):
    """Pull machine models from a WooCommerce store's Store API.

    Parameters
    ----------
    source       : source key stored on each RawMachine (e.g. 'empire').
    store        : base URL, e.g. 'https://www.fitnessequipmentempire.com'.
    categories   : optional category NAMES to limit the pull (resolved to ids). If a
                   store has a clean 'Strength Machines' category, name it here to avoid
                   paging the whole catalogue.
    machines_only: keep only products that look like trackable strength machines.
    """

    def __init__(self, source: str, store: str, *,
                 categories: list[str] | None = None,
                 machines_only: bool = True,
                 delay: float = 1.0, page_size: int = 100, max_pages: int = 60) -> None:
        self.source = source
        self.store = store.rstrip("/")
        self.want_categories = categories or []
        self.machines_only = machines_only
        self.delay = delay
        self.page_size = page_size
        self.max_pages = max_pages

    # --- public API -------------------------------------------------------
    def fetch(self) -> Iterator[RawMachine]:
        seen: set[tuple[str, str]] = set()
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=40,
                          follow_redirects=True) as client:
            cat_ids = self._resolve_categories(client)
            for product in self._paginate(client, cat_ids):
                rec = self._to_machine(product)
                if rec is None:
                    continue
                key = (rec.brand.lower(), rec.model.lower())
                if key in seen:
                    continue
                seen.add(key)
                yield rec

    # --- internals --------------------------------------------------------
    def _api(self, path: str) -> str:
        return f"{self.store}/wp-json/wc/store/v1/{path}"

    def _resolve_categories(self, client: httpx.Client) -> list[int]:
        if not self.want_categories:
            return []
        resp = client.get(self._api("products/categories"), params={"per_page": 100})
        resp.raise_for_status()
        wanted = {c.lower() for c in self.want_categories}
        return [c["id"] for c in resp.json() if c.get("name", "").lower() in wanted]

    def _paginate(self, client: httpx.Client, cat_ids: list[int]) -> Iterator[dict]:
        # one pass per category id, or a single whole-store pass when none given
        for cat in (cat_ids or [None]):
            page = 1
            while page <= self.max_pages:
                params = {"per_page": self.page_size, "page": page}
                if cat is not None:
                    params["category"] = cat
                resp = client.get(self._api("products"), params=params)
                resp.raise_for_status()
                products = resp.json()
                if not products:
                    break
                yield from products
                if len(products) < self.page_size:
                    break
                page += 1
                time.sleep(self.delay)  # be polite

    def _to_machine(self, p: dict) -> RawMachine | None:
        name = (p.get("name") or "").strip()
        if not name:
            return None
        cats = [c.get("name", "") for c in p.get("categories", [])]
        if self.machines_only and not is_strength_machine(name, *cats):
            return None

        brand = extract_brand(name, cats)
        if brand is None:      # no known brand → skip rather than invent a junk one
            return None
        model = clean_model(name, brand)
        if not model:
            return None

        images = p.get("images") or []
        image_url = images[0].get("src") if images else None
        return self.make(
            brand, model,
            category=cats[0] if cats else None,
            image_url=image_url,
            extra={"tags": [c.lower() for c in cats], "name": name,
                   "permalink": p.get("permalink")},
        )
