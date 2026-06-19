# catalog

Builds the **per-gym machine catalog** — the novel, hard part of rackd. There's no public
cross-brand database of machine *models*, so we assemble one. See `../docs/DATA_SOURCES.md`.

## pieces

- `seed_data.json` — real Lisbon gyms + machines for dev (loaded by `../api/seed.py`).
- `scrapers/` — one module per platform. `base.py` defines the `Scraper` + `RawMachine`
  contract.
  - `shopify.py` — Shopify `/products.json` feeds (clean `vendor`/`product_type`/`tags`).
    Used for `shop.lifefitness.com` and the Fitness Superstore reseller.
  - `woocommerce.py` — WooCommerce Store API (`/wp-json/wc/store/v1/products`). Used for the
    used/remanufactured marketplaces (Fitness Equipment Empire, Primo Fitness) — ~30 brands
    each, the richest source. No `vendor` field, so brand is recovered from name/category.
  - `marketplace_example.py` — skeleton for a non-API HTML source.
- `brands.py` — shared vocabulary: brand alias→canonical map, `extract_brand()` (skips rows
  with no *known* brand rather than inventing junk), `is_strength_machine()` (strength vs
  cardio vs non-machine signals), and `clean_model()` (strips `(Remanufactured)`, console and
  marketing noise + HTML entities).
- `categorize.py` — pure classifier. Two axes: **mechanism** (plate-loaded / selectorized /
  cable / …, from product_type+tags+name) and **movement** (chest-press, row, …, from the
  name), which carries the muscles worked.
- `normalize.py` — dedupes `(brand, model)`, categorizes, upserts `Brand` + `Machine` rows.
- `build_catalog.py` — runner. Scrapes the configured stores, categorizes, writes
  `scraped_machines.json`, and prints a coverage breakdown.

## usage

```bash
pip install -r requirements.txt
python build_catalog.py          # live pull + categorize + write scraped_machines.json
```

Current result: **~1,100 machines across ~33 brands** — Cybex, Life Fitness, Hammer Strength,
Precor, Nautilus, Technogym, Hoist, Matrix, Star Trac, Muscle D, Atlantis, FreeMotion, Keiser,
MedX, … — from four stores (Shopify: `shop.lifefitness.com`, `fitnesssuperstore.com`;
WooCommerce: `fitnessequipmentempire.com`, `primofitnessusa.com`). **89% auto-mapped** to a
movement; the unmapped tail is multi-station jungle gyms, functional trainers and cable
crossovers that genuinely aren't a single movement.

## next

1. Add more sources by appending one `ShopifyScraper(...)` or `WooCommerceScraper(...)` line to
   `SOURCES` in `build_catalog.py`. (`progymsupply.com` is Cloudflare-blocked; revisit if needed.)
2. Pipe `RawMachine` records through `normalize.upsert()` (with `../api` on `sys.path`) to load
   the DB, then verify `/gyms/{id}/machines`.
3. Seed the movement layer (`exercises`) from the public-domain free-exercise-db.
