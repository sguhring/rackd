# rackd — 5-slide pitch

**The equipment layer for fitness software.**
Not another workout tracker — the machine database everyone else is missing, licensed to gyms and coaches.

> Deck version. One idea per slide. Speaker notes in blockquotes.

---

## Slide 1 — Fitness software is built on exercises. Training happens on machines.

**Every platform models a generic *"chest press"*. Nobody trains on a generic chest press.**

- A coach writes *"chest press — 3×10 @ 70 kg"*. The client walks into a gym with a Hammer Strength Iso-Lateral, a Panatta, or a plate-loaded converging press. **Three different machines, three different loads. The plan doesn't survive contact with the floor.**
- The same 70 kg is a different lift on every one of them — different leverage, different stack, different starting resistance.
- So "am I progressing?" and "can my client actually do this program?" are both unanswerable.
- Members compensate with notebooks: *"HS iso press, seat 4, pin 8."* That's the real unit of training — and no software stores it.

> The gap isn't UX. It's that the underlying data model is wrong for how people actually train.

---

## Slide 2 — The reason: that database doesn't exist

**There is no public, cross-brand, machine-readable database of gym equipment *models*.**

- Every open dataset — ExerciseDB, free-exercise-db, wger — is keyed to **categories**, never to *"Hammer Strength MTS Iso-Lateral Decline Press"*.
- The model-level data exists, but scattered across manufacturer PDFs and used-equipment marketplaces, in inconsistent formats.
- Nobody assembles it because it's unbounded, unglamorous data work — not a feature you ship in a sprint.
- **Consequence:** every fitness app, coaching platform and gym CMS is stuck at the generic-exercise layer. They can't go deeper even if they want to.

> This is the wedge. Whoever owns the equipment layer becomes infrastructure for everyone above it.

---

## Slide 3 — We built the database. And the tracking that only it makes possible.

**2,287 machine models · 40 brands · 99.6% with product photos**

| | |
|---|---|
| Machine models | **2,287** |
| Brands | **40** — Hammer Strength, Cybex, Life Fitness, Technogym, Panatta, Nautilus, Precor, gym80, Strive… |
| With product photos | **2,278 (99.6%)** — you pick by sight, not by model code |
| Movement library | **675** exercises across 32 movement types, mapped onto the machines |

- Assembled through **official structured feeds** (Shopify `/products.json`, WooCommerce Store API) — not brittle scraping. ToS-checked. Adding a source is a one-line change.
- **A gym is a subset of the catalog.** Map a gym's floor once → that gym now has a precise digital inventory.
- On top of it: tracking that is **machine-based, not exercise-based** — "last time *on this machine*", per-machine PRs, and settings that persist (*seat 4, pin 1*).

> Show the floor-mapping: a gym goes from "we have machines" to a structured, queryable inventory.

---

## Slide 4 — The business: white-label for gyms and coaches

**We don't sell another consumer app. We license the layer underneath one.**

**For gyms —** a branded app with *their actual floor* in it.
- Members log against the real equipment; the gym gets a retention tool without building software.
- **Equipment utilization data they've never had:** which machines get used, how often, by whom. Gyms spend six figures on equipment and buy it blind. We make that a data decision.

**For personal coaches —** programming that survives contact with reality.
- Build a plan **against the client's actual gym inventory**. No more prescribing a machine the gym doesn't own.
- Remote coaching is the norm now — coaches routinely program for gyms they've never set foot in. Today they guess.
- Progression is tracked per machine, so the coach sees real load progression, not noise from equipment swaps.

**Revenue:** per-gym licence + per-coach seat (B2B SaaS), not consumer subscriptions. The consumer app is the demo and the data flywheel — **not** the business.

> This is the slide that separates us from Strong/Hevy/gainzy. They compete for consumers. We sell them the layer they lack.

---

## Slide 5 — Working today, and the ask

**Not a mockup — live infrastructure with a working client.**

- **Shipped:** catalog pipeline, **FastAPI + SQLModel API live on Azure**, Android client in **daily real-world use in Lisbon**.
- **Dogfooding has already produced product truth competitors don't have:** duplicate equipment models that silently corrupt history (solved with catalog de-duplication), and that **a set logged with 0 reps is a *failed attempt*** — it must be recorded, but must never count as a personal best. Exercise-based systems can't express either.
- **Next 6 months:** per-gym floor mapping tooling → white-label pilot with gyms + coaches → native iOS build.
- **The ask:** **3 pilot gyms and 10 coaches in Lisbon as design partners**, plus pre-seed to fund catalog expansion and the first city rollout.

> Close: own the equipment layer, and every gym, coach and app above it becomes a customer — not a competitor.
