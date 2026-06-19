# Architecture

## The problem that shapes everything

There is no public, machine-readable database of gym machine **models** across brands.
Every open exercise dataset is keyed to generic *categories* ("chest press", "cable"), not to
branded models ("Hammer Strength Iso-Lateral Chest Press"). The model-level data exists but is
scattered across manufacturer catalogs and resale marketplaces. See `DATA_SOURCES.md`.

This single fact drives the design:

## Decision 1 — a gym is a subset, not the world

We do **not** need an exhaustive global catalog on day one. A user only needs to *recognize and
pick* the machine in front of them. So:

- The global catalog (`machines`) holds the models we know about.
- Each gym (`gym_machines`) maps the subset it actually has.
- Coverage grows as users add their gym's machines. That crowdsourced growth is the moat, and it
  turns "no complete DB exists" from a weakness into a defensible asset.

## Decision 2 — track progression per machine, never across models

Weight stacks and leverage differ between models: a "68" on a Hammer Strength press is not a "68"
on a Technogym one. So `sets` reference a specific `gym_machine_id`, and "last time" / PR logic
reads history **for that machine only**. We never compare loads across models. This also sidesteps
unit-normalization headaches and is honest about what the number means.

## Decision 3 — reuse the movement layer, build the model layer

`exercises` is seeded from an existing open dataset (ExerciseDB or free-exercise-db) — we don't
rebuild it. Our contribution is the `brands` + `machines` + `gym_machines` layer on top, plus the
scrapers that populate it.

## Decision 4 — local-first, gainzy-style

Following gainzy: minimal, native-feeling, no mandatory accounts or cloud. `user_id` exists so the
data model is multi-user-ready, but the product can ship on-device first.

## Data flow

```
manufacturer & marketplace sources
        │  catalog/scrapers/*  (one module per source)
        ▼
   raw records  ──►  catalog/normalize.py  ──►  machines + brands
                                                     │
exercise dataset (ExerciseDB) ──► exercises ─────────┤
                                                     ▼
                              api/  (FastAPI + SQLModel)  ──►  web / iOS client
                                                     ▲
                          users mapping their gym ───┘  (grows gym_machines)
```

## Build order

1. Schema + seeded API from `catalog/seed_data.json` (real Lisbon gyms). Fastest path to a
   working `/gyms` → `/gym/{id}/machines` → `/sets` loop that the prototype can talk to.
2. First scraper against one marketplace (richest cross-brand, model-level source) → normalize →
   load. Prove the catalog pipeline end-to-end on a few brands.
3. Pull the exercise base layer.
4. Real frontend (the prototype is the spec).

## Frontend note

The prototype (`web/prototype/index.html`) is built in gainzy's language (SF Pro, dark, lowercase,
"last time" + PR). Two viable real builds: a React/Next web app, or a SwiftUI native iOS app
(closer to gainzy). The accent colour is isolated in one CSS variable for easy rebranding.
