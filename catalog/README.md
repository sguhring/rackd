# catalog

Builds the **per-gym machine catalog** — the novel, hard part of rackd. There's no public
cross-brand database of machine *models*, so we assemble one. See `../docs/DATA_SOURCES.md`.

## pieces

- `seed_data.json` — real Lisbon gyms + machines for dev (loaded by `../api/seed.py`).
- `scrapers/` — one module per source. `base.py` defines the `Scraper` + `RawMachine` contract;
  `marketplace_example.py` is a skeleton to copy.
- `normalize.py` — maps scraped `RawMachine` records into the DB (`brands`, `machines`),
  canonicalises brand names, dedupes, and best-effort maps each model to an exercise.

## first task for Claude Code

1. Read `../docs/DATA_SOURCES.md`, pick ONE marketplace, confirm its ToS allows scraping.
2. Implement its scraper by copying `marketplace_example.py`. JS-rendered pages → use the
   Playwright MCP server.
3. Run it for 8–10 dominant brands, pass records through `normalize.upsert()`, and verify the
   `/gyms/{id}/machines` endpoint surfaces them.

## requirements

```
pip install -r requirements.txt
```
