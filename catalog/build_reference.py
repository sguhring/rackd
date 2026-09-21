"""Build docs/machine-reference.html — the browsable machine reference — from the
live database the API serves (api/rackd.db).

Every machine row is placed in the region -> muscle -> movement tree. The curated
taxonomy in catalog/machines_resolved.json wins when it has the (brand, model); rows
it doesn't know (the brochure lines added straight into the DB) fall back to the same
alias / movement / facet rules build_taxonomy.py uses.

Photos are inlined as small JPEG thumbnails so the page stays a single file. Remote
photo URLs are fetched once and cached in catalog/reference_thumbs/ (gitignored).

    python catalog/build_reference.py             # rebuild the page
    python catalog/build_reference.py --no-fetch  # skip remote photos not yet cached
"""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_taxonomy import MUSCLE_REGION, REGIONS, canon_movement, facets, slug, tokens, ALIAS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "api" / "rackd.db"
RESOLVED = ROOT / "catalog" / "machines_resolved.json"
CACHE = ROOT / "catalog" / "reference_thumbs"
OUT = ROOT / "docs" / "machine-reference.html"

THUMB_PX = 200
THUMB_Q = 68
FETCH_WORKERS = 4
FETCH_RETRIES = 3

REGION_COLOR = {
    "chest": "#e2685c", "back": "#2fb083", "shoulders": "#e0973a", "arms": "#a07ce8",
    "legs": "#5b8def", "glutes": "#dd6aa5", "abs": "#3aa8c9", "neck": "#8b93a1",
    "functional-other": "#7c8593",
}
MECHANISMS = {"plate-loaded", "selectorized", "cable", "smith/rack", "machine"}
NON_MACHINE = {"bench", "rack", "storage", "accessory"}


# ── data ──────────────────────────────────────────────────────────────────────

def key(brand: str, model: str) -> tuple[str, str]:
    return brand.strip().lower(), model.strip().lower()


def load_machines() -> list[dict]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """select m.id, b.name as brand, m.model, m.machine_type, m.muscle_label,
                  m.image_url, m.source, e.slug as exercise, e.name as exercise_name
           from machine m join brand b on b.id = m.brand_id
           left join exercise e on e.id = m.exercise_id
           order by b.name, m.model"""
    ).fetchall()
    return [dict(r) for r in rows]


def classify(m: dict, curated: dict[tuple, dict]) -> dict:
    """{region, muscle, movement, secondary, facets, function}"""
    cur = curated.get(key(m["brand"], m["model"]))
    if cur:
        return {
            "region": cur.get("region") or "functional-other",
            "muscle": cur.get("muscle"),
            "movement": cur.get("movement"),
            "secondary": cur.get("secondary") or [],
            "facets": cur.get("facets") or {},
            "function": cur.get("mechanism") or m["exercise_name"],
        }
    mtype = m["machine_type"] or ""
    toks = [ALIAS[t] for t in tokens(m["muscle_label"] or "") if t in ALIAS]
    primary = toks[0] if toks else None
    region = MUSCLE_REGION.get(primary, "functional-other") if primary else "functional-other"
    if mtype.lower() in NON_MACHINE:
        region, primary = "functional-other", None
    f = facets(m["model"], mtype if mtype in MECHANISMS else "machine")
    if mtype.lower() in NON_MACHINE:
        f["implement"] = mtype.lower()
    return {
        "region": region,
        "muscle": primary,
        "movement": canon_movement(m["exercise"]),
        "secondary": list(dict.fromkeys(toks[1:])),
        "facets": f,
        "function": m["exercise_name"] or (mtype if mtype and mtype not in MECHANISMS else None),
    }


# ── photos ────────────────────────────────────────────────────────────────────

def _thumb(raw: bytes) -> bytes:
    im = Image.open(io.BytesIO(raw))
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    im.thumbnail((THUMB_PX, THUMB_PX))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=THUMB_Q, optimize=True)
    return out.getvalue()


def _cache_path(url: str) -> Path:
    tag = f"{THUMB_PX}q{THUMB_Q}"
    return CACHE / (hashlib.sha1(url.encode()).hexdigest() + f"-{tag}.jpg")


def _fetch(url: str) -> bytes:
    safe = quote(url, safe=":/?&=%+,;@#~")          # non-ASCII path chars -> %xx
    req = Request(safe, headers={"User-Agent": "Mozilla/5.0 (rackd reference builder)"})
    last: Exception | None = None
    for attempt in range(FETCH_RETRIES):
        try:
            with urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — retry transient network errors
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def thumb_for(url: str | None, fetch: bool) -> bytes | None:
    if not url:
        return None
    CACHE.mkdir(exist_ok=True)
    p = _cache_path(url)
    if p.exists():
        return p.read_bytes()
    try:
        if url.startswith("data:"):
            raw = base64.b64decode(url.split(",", 1)[1])
        elif fetch:
            raw = _fetch(url)
        else:
            return None
        data = _thumb(raw)
    except Exception as e:  # noqa: BLE001 — one bad photo must not kill the build
        print(f"  [photo] {url[:80]} -> {type(e).__name__}: {e}")
        return None                 # not cached, so the next run retries it
    p.write_bytes(data)
    return data


# ── html ──────────────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg:#0d0f13; --panel:#14171d; --card:#171b22; --line:#242932; --line2:#2e343f;
  --ink:#f2f4f7; --ink2:#a8b0bc; --ink3:#6f7784;
  --accent:#d7ff3e; --shot:#ffffff;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg:#f7f8f6; --panel:#ffffff; --card:#ffffff; --line:#e5e8e3; --line2:#d4d9d0;
    --ink:#14171b; --ink2:#59616b; --ink3:#8d959f; --accent:#5f7d00; --shot:#f4f5f3;
  }
}
:root[data-theme="light"] {
  --bg:#f7f8f6; --panel:#ffffff; --card:#ffffff; --line:#e5e8e3; --line2:#d4d9d0;
  --ink:#14171b; --ink2:#59616b; --ink3:#8d959f; --accent:#5f7d00; --shot:#f4f5f3;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.5 "IBM Plex Sans","Segoe UI",system-ui,sans-serif; -webkit-font-smoothing:antialiased; }
.wrap { max-width:1460px; margin:0 auto; padding:0 22px 96px; }
header { padding:40px 0 20px; }
.mark { font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif; font-weight:700;
  font-size:36px; letter-spacing:-.02em; line-height:1; margin:0; }
.mark .dot { color:var(--accent); }
.tag { margin:9px 0 0; color:var(--ink2); max-width:66ch; }
.stats { display:flex; flex-wrap:wrap; gap:26px; margin-top:22px; }
.stat b { display:block; font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:23px;
  letter-spacing:-.02em; font-variant-numeric:tabular-nums; color:var(--accent); }
.stat span { font-size:11.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--ink3); }

.bar { position:sticky; top:0; z-index:30; background:var(--bg);
  border-bottom:1px solid var(--line); padding:11px 0; margin-top:18px;
  display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
input[type=search] { flex:1 1 260px; min-width:200px; font:14px "IBM Plex Sans",sans-serif;
  color:var(--ink); background:var(--panel); border:1px solid var(--line2);
  border-radius:7px; padding:9px 11px; }
input:focus-visible, a:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.count { margin-left:auto; font-family:"IBM Plex Mono",monospace; font-size:13px;
  color:var(--ink3); font-variant-numeric:tabular-nums; }
.count b { color:var(--ink); }

.toc { display:flex; flex-wrap:wrap; gap:7px; padding:14px 0 4px; }
.tocitem { display:inline-flex; align-items:baseline; gap:7px; text-decoration:none;
  border:1px solid color-mix(in srgb, var(--rg) 34%, transparent);
  background:color-mix(in srgb, var(--rg) 13%, transparent);
  color:var(--rg); border-radius:6px; padding:5px 10px; font-size:13px; font-weight:600; }
.tocitem b { font-family:"IBM Plex Mono",monospace; font-size:11px; opacity:.75; font-weight:600; }
.tocitem:hover { background:color-mix(in srgb, var(--rg) 22%, transparent); }

.region { margin-top:52px; scroll-margin-top:64px; }
.region h2 { display:flex; align-items:center; gap:10px; margin:0 0 4px;
  font-family:"IBM Plex Sans Condensed",sans-serif; font-weight:700; font-size:27px;
  letter-spacing:-.015em; padding-bottom:10px; border-bottom:2px solid var(--rg); }
.dotr { width:9px; height:9px; border-radius:50%; background:var(--rg); flex:none; }
.region h2 .c { margin-left:auto; font-family:"IBM Plex Mono",monospace; font-size:12px;
  font-weight:400; color:var(--ink3); letter-spacing:0; }
.mu { margin-top:26px; }
.mu > h3 { display:flex; align-items:baseline; gap:9px; margin:0 0 2px; font-size:16px;
  font-weight:600; letter-spacing:-.01em; }
.mu > h3 .c { font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink3); font-weight:400; }
.mv { margin-top:14px; }
.mv h4 { display:flex; align-items:baseline; gap:8px; margin:0 0 9px;
  font-size:10.5px; font-weight:600; letter-spacing:.1em; text-transform:uppercase;
  color:var(--ink3); padding-bottom:6px; border-bottom:1px solid var(--line); }
.mv h4 .c { margin-left:auto; font-family:"IBM Plex Mono",monospace; letter-spacing:0; }

.grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(212px,1fr)); }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px;
  overflow:hidden; display:flex; flex-direction:column; }
.shot { height:158px; background:var(--shot); display:grid; place-items:center; flex:none;
  overflow:hidden; border-bottom:1px solid var(--line); }
.shot img { width:100%; height:158px; object-fit:contain; display:block; }
.shot.none { background:transparent; }
.shot.none span { font-family:"IBM Plex Mono",monospace; font-size:9.5px;
  letter-spacing:.09em; text-transform:uppercase; color:var(--ink3); }
.cb { padding:10px 11px 11px; display:flex; flex-direction:column; gap:5px; }
.model { margin:0; font-size:13.4px; line-height:1.34; font-weight:500; overflow-wrap:anywhere; }
.brand { font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.06em;
  text-transform:uppercase; color:var(--ink3); }
.mech { font-size:12.2px; color:var(--ink2); }
.sec { font-size:11.4px; color:var(--ink3); }
.chips { display:flex; flex-wrap:wrap; gap:4px; margin-top:1px; }
.fc { font-family:"IBM Plex Mono",monospace; font-size:9.6px; padding:2px 6px; border-radius:4px;
  background:var(--panel); color:var(--ink2); border:1px solid var(--line2); }
.hide { display:none !important; }
.nores { padding:60px 0; text-align:center; color:var(--ink3); }
@media (prefers-reduced-motion: no-preference) { .card, .tocitem { transition:border-color .12s ease, background .12s ease; } }
.card:hover { border-color:var(--line2); }
"""

JS = """
const q=document.getElementById("q"), n=document.getElementById("n"), nores=document.getElementById("nores");
const cards=[...document.querySelectorAll(".card")];
cards.forEach(c => c._hay = c.textContent.toLowerCase().replace(/\\s+/g," "));
const mvs=[...document.querySelectorAll(".mv")], mus=[...document.querySelectorAll(".mu")],
      regs=[...document.querySelectorAll(".region")];
function apply(){
  const t=q.value.trim().toLowerCase();
  let shown=0;
  for(const c of cards){ const ok=!t||c._hay.includes(t); c.classList.toggle("hide",!ok); if(ok)shown++; }
  const vis=el=>!el.classList.contains("hide");
  for(const g of mvs) g.classList.toggle("hide", ![...g.querySelectorAll(".card")].some(vis));
  for(const g of mus) g.classList.toggle("hide", ![...g.querySelectorAll(".mv")].some(vis));
  for(const g of regs) g.classList.toggle("hide", ![...g.querySelectorAll(".mu")].some(vis));
  n.textContent=shown; nores.classList.toggle("hide", shown>0);
}
q.addEventListener("input", apply);
"""


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def card(m: dict, c: dict, thumb: bytes | None) -> str:
    if thumb:
        shot = (f'<div class="shot"><img loading="lazy" decoding="async" alt="" '
                f'src="data:image/jpeg;base64,{base64.b64encode(thumb).decode("ascii")}"></div>')
    else:
        shot = '<div class="shot none"><span>no photo</span></div>'
    parts = [f'<p class="model">{esc(m["model"])}</p>', f'<div class="brand">{esc(m["brand"])}</div>']
    if c["function"]:
        parts.append(f'<div class="mech">{esc(c["function"])}</div>')
    if c["secondary"]:
        parts.append(f'<div class="sec">+ {esc(" · ".join(c["secondary"]))}</div>')
    chips = [c["facets"].get("implement")] + [v for k, v in c["facets"].items() if k != "implement"]
    parts.append('<div class="chips">' + "".join(f'<span class="fc">{esc(v)}</span>' for v in chips if v) + "</div>")
    return f'<article class="card">{shot}<div class="cb">{"".join(parts)}</div></article>'


def build(fetch: bool = True) -> None:
    machines = load_machines()
    curated = {key(r["brand"], r["model"]): r for r in json.loads(RESOLVED.read_text(encoding="utf-8"))}
    classes = {m["id"]: classify(m, curated) for m in machines}

    print(f"{len(machines)} machines · rendering thumbnails "
          f"({sum(1 for m in machines if m['image_url'])} photos)…")
    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        thumbs = dict(zip((m["id"] for m in machines),
                          pool.map(lambda m: thumb_for(m["image_url"], fetch), machines)))

    # region -> muscle -> movement -> [machines]
    tree: dict[str, dict[str, dict[str, list[dict]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for m in machines:
        c = classes[m["id"]]
        region = c["region"] if c["region"] in REGION_COLOR else "functional-other"
        muscle = c["muscle"] if region != "functional-other" else None
        tree[region][muscle or "—"][c["movement"] or "—"].append(m)

    region_order = [r for r in REGIONS if r in tree] + [r for r in tree if r not in REGIONS and r != "functional-other"]
    if "functional-other" in tree:
        region_order.append("functional-other")

    def region_count(r: str) -> int:
        return sum(len(ms) for mus in tree[r].values() for ms in mus.values())

    sections, toc = [], []
    for r in region_order:
        color = REGION_COLOR.get(r, "#7c8593")
        label = "functional / other" if r == "functional-other" else r
        toc.append(f'<a class="tocitem" href="#r-{slug(r)}" style="--rg:{color}">'
                   f'<span>{esc(r)}</span><b>{region_count(r)}</b></a>')
        muscles = tree[r]
        order = [mu for mu in REGIONS.get(r, []) if mu in muscles] + \
                [mu for mu in muscles if mu not in REGIONS.get(r, []) and mu != "—"] + \
                (["—"] if "—" in muscles else [])
        mu_html = []
        for mu in order:
            moves = muscles[mu]
            mv_order = sorted(moves, key=lambda k: (k == "—", -len(moves[k]), k))
            mv_html = []
            for mv in mv_order:
                ms = sorted(moves[mv], key=lambda x: (x["brand"].lower(), x["model"].lower()))
                cards = "".join(card(m, classes[m["id"]], thumbs.get(m["id"])) for m in ms)
                mv_label = "unassigned movement" if mv == "—" else mv
                mv_html.append(f'<div class="mv"><h4>{esc(mv_label)}<span class="c">{len(ms)}</span></h4>'
                               f'<div class="grid">{cards}</div></div>')
            n_mu = sum(len(v) for v in moves.values())
            mu_label = "no single target muscle" if mu == "—" else mu
            mu_html.append(f'<div class="mu"><h3>{esc(mu_label)}<span class="c">{n_mu}</span></h3>{"".join(mv_html)}</div>')
        sections.append(f'<section class="region" id="r-{slug(r)}" style="--rg:{color}">'
                        f'<h2><span class="dotr"></span>{esc(label)}<span class="c">{region_count(r)} machines</span></h2>'
                        f'{"".join(mu_html)}</section>')

    n_total = len(machines)
    n_brands = len({m["brand"] for m in machines})
    n_class = sum(1 for c in classes.values() if c["region"] != "functional-other" and c["muscle"] and c["movement"])
    n_photo = sum(1 for t in thumbs.values() if t)
    stats = [(n_total, "machines"), (n_brands, "brands"), (len(region_order), "regions"),
             (n_class, "fully classified"), (n_photo, "with photo")]

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>rackd Machine Reference</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{CSS}</style></head><body>
<div class="wrap">
  <header>
    <h1 class="mark">rackd<span class="dot">.</span></h1>
    <p class="tag">The machine reference — every catalogued model, ordered by the movement
      taxonomy: region, then muscle, then movement. Weight is never comparable across models,
      so progression is tracked per machine.</p>
    <div class="stats">{"".join(f'<div class="stat"><b>{n}</b><span>{lbl}</span></div>' for n, lbl in stats)}</div>
  </header>
  <div class="bar">
    <input type="search" id="q" placeholder="Search model, brand, muscle, movement…" aria-label="Search the reference">
    <div class="count"><b id="n">{n_total}</b> shown</div>
  </div>
  <nav class="toc">{"".join(toc)}</nav>
  {"".join(sections)}
  <div class="nores hide" id="nores">No machines match that search.</div>
</div>
<script>{JS}</script>
</body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 2**20:.1f} MB)")
    for n, lbl in stats:
        print(f"  {n:>5} {lbl}")
    unjoined = sum(1 for m in machines if key(m["brand"], m["model"]) not in curated)
    print(f"  {unjoined:>5} classified by rules (not in machines_resolved.json)")


if __name__ == "__main__":
    build(fetch="--no-fetch" not in sys.argv)
