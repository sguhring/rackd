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
- **wger** — open-source tracker (AGPL) with a REST API and equipment-tagged exercise wiki; good
  architectural precedent. Equipment is generic categories, not models.

## Tier 3 — niche / not useful for the catalog

- **Manufacturer APIs.** Life Fitness LFopen exposes workout/console telemetry, **not** a model
  catalog — doesn't solve "pick the machine in my gym".
- **Image-recognition datasets** (Kaggle, Roboflow, GitHub CNNs) — classify ~20–25 generic
  equipment *types*, not models. Possible future "point camera to identify machine" feature only.

## Practical first step

Pick **one** marketplace, confirm its ToS allows it, scrape 8–10 dominant brands (the ones that
fill real gyms), normalize to the `machines` schema. That covers the vast majority of machines a
user will stand in front of. Everything else is crowdsourced per gym.
