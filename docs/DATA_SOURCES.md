# Data sources

Where gym machine **model** data actually lives, ranked for building the catalog. No single
source has every model; the catalog is assembled from these and grown by users.

## Tier 1 — model-level, cross-brand (best for the catalog)

**Used / remanufactured equipment marketplaces.** Richest source: ~30 brands each, with a
per-model page (photo, name, specs) in a consistent structure. Ideal to scrape into
`brand / model / category / image`. Examples to evaluate: Fitness Superstore, Pro Gym Supply,
Fitness Equipment Empire, Primo Fitness. ⚠️ Check each site's robots.txt / ToS before scraping;
prefer official feeds where offered.

**Manufacturer catalogs.** Authoritative per brand.
- Life Fitness publishes a full PDF catalog covering Life Fitness + Hammer Strength + Cybex +
  ParaBody + SCIFIT (one company, post-consolidation). Shop is organized into model lines
  (Axiom, Insignia, Hammer Strength Select, MTS).
- Technogym product pages embed structured JSON in the HTML (`item_id`, `item_name`,
  `item_brand`, `item_category`) — scraper-friendly.
- Matrix, Precor, Hoist, etc. publish their own catalogs / spec sheets.

## Tier 2 — movement/exercise base layer (category-level, reuse don't rebuild)

- **ExerciseDB API** — open-source, 5,000–11,000+ exercises, self-hostable (Vercel/Supabase),
  `equipments` field, images/GIFs/instructions.
- **yuhonas/free-exercise-db** — 800+ public-domain exercises, clean JSON, `equipment` field.
  **Implemented**: `api/load_library.py` loads it into the `LibraryExercise` table (675 gym-
  relevant movements, grouped push/pull/legs/core, with images); served at `GET /library` and
  used as the default exercise options + search in the custom-workout builder.
- **wger** — open-source tracker (AGPL) with a REST API and equipment-tagged exercise wiki; good
  architectural precedent. Equipment is generic categories, not models.

## Tier 3 — niche / not useful for the catalog

- **Manufacturer APIs.** Life Fitness LFopen exposes workout/console telemetry, **not** a model
  catalog — doesn't solve "pick the machine in my gym".
- **Image-recognition datasets** (Kaggle, Roboflow, GitHub CNNs) — classify ~20–25 generic
  equipment *types*, not models. Possible future "point camera to identify machine" feature only.

## Chosen method (implemented) — Shopify `/products.json`

The commercial-equipment shops (`shop.lifefitness.com`, Fitness Superstore, Gym Pros, …) run on
**Shopify**, which exposes an official, structured product feed — no HTML scraping required:

```
https://<store>/products.json?limit=250&page=N           # whole store
https://<store>/collections/<handle>/products.json        # one collection
```

Each product gives `vendor` (brand), `title` (brand + model), `product_type` + `tags`
(mechanism + body region), and image URLs. `shop.lifefitness.com`'s robots.txt disallows
`/cart`, `/checkout` and sorted/filtered collection URLs but **not** `/collections/` or `*.json`.

## Chosen method (implemented) — WooCommerce Store API

The used/remanufactured marketplaces — the richest source (~30 brands each) — run on
**WooCommerce**, which exposes a public Store API:

```
https://<store>/wp-json/wc/store/v1/products?per_page=100&page=N
https://<store>/wp-json/wc/store/v1/products/categories
```

Each product gives `name` (brand + model), `categories` and `images`. There's no clean vendor
field, so the brand is recovered by `brands.extract_brand()` (a known-brand alias map; rows with
no known brand are skipped rather than mislabelled), and `brands.clean_model()` strips the heavy
marketing/condition noise. Implemented in `catalog/scrapers/woocommerce.py`. Note: some sites
(`progymsupply.com`) sit behind Cloudflare and return 403.

## Combined result (implemented)

Run via `catalog/build_catalog.py` across four stores — Shopify (`shop.lifefitness.com`,
`fitnesssuperstore.com`) + WooCommerce (`fitnessequipmentempire.com`, `primofitnessusa.com`) —
yielding **~1,100 machines across ~33 brands** (Cybex, Life Fitness, Hammer Strength, Precor,
Nautilus, Technogym, Hoist, Matrix, Star Trac, Muscle D, Atlantis, FreeMotion, Keiser, MedX, …),
89% auto-categorized. Add a source by appending one `ShopifyScraper(...)` / `WooCommerceScraper(...)`
line to `SOURCES`.

## Practical first step (done)

Pick **one** source, confirm its ToS allows it, pull the dominant brands, normalize to the
`machines` schema. That covers the vast majority of machines a user will stand in front of.
Everything else is crowdsourced per gym.

## Exercise illustrations (the library layer)

**Everkinetic** line-art exercise drawings, via
[chaosbastler/opentraining-exercises](https://github.com/chaosbastler/opentraining-exercises)
— **CC BY-SA 3.0**, credit "Everkinetic". ~170 movements (start/end poses, svg + png).
`api/everkinetic_images.py` token-matches these onto the free-exercise-db library exercises
(~97 matched); unmatched exercises keep their free-exercise-db photo. Attribution must be
shown in-app wherever these illustrations appear (BY-SA also makes derivatives share-alike).
