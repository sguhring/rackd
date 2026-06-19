# rackd

A workout tracker that knows the **exact machine** in front of you.

Most trackers log a generic "chest press". rackd logs *the Hammer Strength Iso-Lateral Chest
Press on your gym's floor* — and tracks your progression against that specific machine, because
a load on one model isn't the same as on another. You can also build custom workouts from any
exercise. Design follows the iOS app *gainzy*: native, dark, lowercase, minimal.

## why this is interesting (and hard)

There is no public, cross-brand database of gym machine models. The value — and the work — is
assembling one from manufacturer and marketplace sources and letting users grow it per gym.
See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

## repo layout

```
rackd/
├── CLAUDE.md              # constitution for Claude Code — read this first
├── docs/
│   ├── ARCHITECTURE.md    # decisions, especially the per-gym catalog idea
│   ├── DATA_SOURCES.md    # where machine-model data actually lives
│   └── schema.sql         # full Postgres DDL
├── catalog/               # Python — scrape + normalize machine models (the novel part)
│   ├── seed_data.json     # real Lisbon gyms + machines for dev
│   ├── normalize.py       # raw scrape -> our schema
│   └── scrapers/          # one module per source
├── api/                   # FastAPI + SQLModel — serves gyms / machines / sets
│   ├── models.py
│   ├── database.py
│   ├── seed.py
│   └── main.py
└── web/prototype/         # the working design reference (index.html)
```

## quick start

```bash
# 1. API + DB
cd api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# set DATABASE_URL (defaults to sqlite for local dev)
python seed.py            # load catalog/seed_data.json into the DB
uvicorn main:app --reload # http://127.0.0.1:8000/docs

# 2. design reference
open web/prototype/index.html
```

## roadmap

- [x] Interactive design prototype (gainzy-style flow + custom workouts)
- [ ] Schema + seeded API (`/gyms`, `/gyms/{id}/machines`, `/exercises`, `/sets`)
- [ ] Catalog: first scraper (a used-equipment marketplace) → normalized machines
- [ ] Pull exercise base layer from ExerciseDB / free-exercise-db
- [ ] Frontend proper (React/Next, or SwiftUI for a native iOS build)
- [ ] Per-gym crowdsourced machine adds

## license

TBD.
