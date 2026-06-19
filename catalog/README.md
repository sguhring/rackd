# catalog

Builds the **per-gym machine catalog** — the novel, hard part of rackd. There's no public
cross-brand database of machine *models*, so we assemble one. See `../docs/DATA_SOURCES.md`.

## pieces

- `seed_data.json` — real Lisbon gyms + machines for dev (loaded by `../api/seed.py`).
- `scrapers/` — one module per source. `base.py` defines the `Scraper` + `RawMachine` contract.
  - `shopify.py` — **the primary source.** Pulls a Shopify store's public `/products.json`
    feed (structured JSON, not HTML scraping). `shop.lifefitness.com` alone covers
    Life Fitness + Hammer Strength + Cybex.
  - `marketplace_example.py` — skeleton for a non-Shopify HTML source.
- `categorize.py` — pure classifier. Puts each model on two axes: **mechanism**
  (plate-loaded / selectorized / cable / …, from product_type+tags) and **movement**
  (chest-press, row, …, from the model name), which carries the muscles worked.
- `normalize.py` — canonicalises brand names, dedupes `(brand, model)`, categorizes, and
  upserts `Brand` + `Machine` rows.
- `build_catalog.py` — runner. Scrapes the configured stores, categorizes, writes
  `scraped_machines.json`, and prints a coverage breakdown.

## usage

```bash
pip install -r requirements.txt
python build_catalog.py          # live pull + categorize + write scraped_machines.json
```

Current result: **366 machines across 6 brands** — Cybex, Hammer Strength, Life Fitness,
Technogym, Precor, Matrix — from two Shopify stores (`shop.lifefitness.com` + the multi-brand
reseller `fitnesssuperstore.com`). **84% auto-mapped** to a movement; the unmapped tail is
multi-station jungle gyms, functional trainers and cable crossovers that genuinely aren't a
single movement.

## next

1. Add more brands by appending one `ShopifyScraper(...)` line to `SOURCES` in
   `build_catalog.py` (point it at a store's brand collection; `machines_only` + `clean_model`
   handle cardio/remanufactured noise).
2. Pipe `RawMachine` records through `normalize.upsert()` (with `../api` on `sys.path`) to load
   the DB, then verify `/gyms/{id}/machines`.
3. Seed the movement layer (`exercises`) from the public-domain free-exercise-db.
