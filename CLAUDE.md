# CLAUDE.md

The constitution for this repo. Read at the start of every session.

## what we're building

**rackd** (working codename — rename freely) is a workout tracker whose differentiator is a
**per-gym machine catalog**: a user picks the exact branded machine in front of them
(e.g. "Hammer Strength Iso-Lateral Chest Press"), not a generic "chest press". Sets are
logged and tracked against that specific machine, plus custom workouts assembled from any
exercise. Design language follows the iOS app *gainzy*: native-iOS, dark, lowercase, minimal,
with "last time" and PR detection as the emotional core.

## the core architectural idea (do not lose this)

There is **no public database of gym machine models** across brands. So:

1. A **gym is a subset** of a global machine catalog, not the whole thing. The catalog only
   needs to be good enough for a user to *recognize and pick* their machine — not exhaustive.
2. The catalog is **assembled by us** (scraped/normalized from manufacturer + marketplace
   sources) and **grown by users** adding their gym's machines. That crowdsourced growth is
   the moat. See `docs/DATA_SOURCES.md`.
3. **Weight is not comparable across machines** (different stacks/leverage). Never compare a
   load on one model to another. Track and show progression **per machine only**.
4. The **exercise/movement layer** comes from an existing open dataset (ExerciseDB or
   free-exercise-db); we do not rebuild it. We add the brand+model layer on top.

## stack & layout

- `catalog/` — Python. Scrape + normalize machine models into our schema. The novel, hard part.
- `api/` — FastAPI + SQLModel (Python). Serves gyms, machines, exercises, sets.
- `web/prototype/` — the working design reference (`index.html`). The real frontend grows from this.
- `docs/` — `ARCHITECTURE.md`, `DATA_SOURCES.md`, `schema.sql`.

## conventions

- Python: 3.11+, type hints everywhere, `ruff` for lint/format, `pydantic`/`SQLModel` for models.
- Keep functions small and pure where possible; the scrapers are the only IO-heavy area.
- Database is the source of truth; `catalog/seed_data.json` is dev seed data only.
- API responses are typed; no untyped dicts crossing the boundary.
- Respect each source's robots.txt / ToS before scraping — check `docs/DATA_SOURCES.md` notes.
- UI copy is lowercase and plain (gainzy voice). Accent colour lives in one CSS variable.

## data model (see docs/schema.sql for the full DDL)

`gyms` ──< `gym_machines` >── `machines` ──> `exercises`
`sets` references `gym_machines` (the specific machine instance) + a workout/session.

## what "done" looks like for the first milestone

A user can: open the app → pick their gym (or build a custom workout) → see that gym's
machines → log a set against a specific machine → see "last time on this machine" and a PR
when they beat it. The API serves all of that from a seeded Postgres DB.

## non-goals (for now)

- No social feed, no accounts/cloud (on-device / local-first, like gainzy).
- No cross-machine weight comparison.
- No attempt at an exhaustive global machine DB on day one — seed a handful of real Lisbon gyms.
