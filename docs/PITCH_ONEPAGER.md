# rackd — one-pager

## The equipment layer for fitness software

*Not another workout tracker — the gym-machine database everyone else is missing, licensed white-label to gyms and coaches.*

---

### Problem — software models exercises, people train on machines

A coach writes *"chest press — 3×10 @ 70 kg."* The client walks into a gym with a Hammer Strength Iso-Lateral, a Panatta, or a plate-loaded converging press. **Three different machines, three different loads — the plan doesn't survive contact with the gym floor.**

The same 70 kg is a different lift on each: different leverage, different stack, different starting resistance. So both core questions break down — *is this client progressing?* and *can they even perform this program here?* Members compensate with notebooks (*"HS iso press, seat 4, pin 8"*). That's the real unit of training, and no software stores it.

### Why it's unsolved — the database doesn't exist

**There is no public, cross-brand, machine-readable database of gym equipment *models*.** Every open dataset (ExerciseDB, free-exercise-db, wger) is keyed to generic categories, never to *"Hammer Strength MTS Iso-Lateral Decline Press"*. The data exists but sits scattered across manufacturer PDFs and used-equipment marketplaces in inconsistent formats — unbounded, unglamorous work nobody takes on. As a result **every fitness app, coaching platform and gym system is stuck at the generic-exercise layer**, even if they'd rather not be.

### Solution — we built it, plus the tracking it unlocks

| Built so far | |
|---|---|
| Machine models | **2,287** |
| Brands | **40** — Hammer Strength, Cybex, Life Fitness, Technogym, Panatta, Nautilus, Precor, gym80, Strive… |
| With product photos | **2,278 (99.6%)** — recognition is visual, not model codes |
| Movement library | **675** exercises across 32 movement types, mapped onto machines |

Assembled via **official structured feeds** (Shopify `/products.json`, WooCommerce Store API) rather than brittle scraping, ToS-checked per source; adding a source is a one-line change. A gym is a **subset** of the catalog — map a floor once and that gym has a precise digital inventory. On top sits tracking that is **machine-based, not exercise-based**: "last time *on this machine*", per-machine PRs, and machine settings that persist.

### Business model — white-label, B2B

**Gyms** get a branded app containing *their actual floor* — a retention tool without building software — plus **equipment utilization data they have never had**. Gyms spend six figures on equipment and buy it blind; we turn that into a data decision.

**Personal coaches** get programming that survives reality: build a plan **against the client's actual gym inventory**, instead of prescribing machines the gym doesn't own. Remote coaching means coaches routinely program for gyms they've never seen — today they guess. Per-machine progression shows real load progress, not noise from equipment swaps.

**Revenue: per-gym licence + per-coach seat.** The consumer app is the demo and the data flywheel — not the business. This is why we don't compete with Strong / Hevy / gainzy: **we sell them the layer they lack.**

### Status

Live infrastructure, not a mockup: catalog pipeline, **FastAPI + SQLModel API running on Azure**, and an Android client in **daily real-world use in Lisbon**.

Dogfooding has already produced product truth competitors don't have — duplicate equipment models that silently corrupt training history (solved via catalog de-duplication), and the fact that **a set logged with 0 reps is a *failed attempt***: it must be kept in history but must never count as a personal best. Exercise-based systems cannot express either distinction.

### Next & the ask

**Next 6 months:** per-gym floor-mapping tooling → white-label pilot with gyms and coaches → native iOS build.

**Ask: 3 pilot gyms and 10 coaches in Lisbon as design partners**, plus pre-seed to fund catalog expansion and the first city rollout.

---

*Contact: [name · email · link]*
