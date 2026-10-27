"""HBP (Hefele Borenski GmbH) — recovered from the Internet Archive.

HBP is a German strength-equipment maker in Grenzach-Wyhlen ("Health Beauty
Power"). Their site is dead — hbp-gmbh.com and .de both fail DNS — so the only
surviving manufacturer source is the Wayback Machine, which caught the whole PHP
product catalog before it went. There is no brochure: zero PDFs are archived for
either domain. The detail pages ARE the catalog.

    https://web.archive.org/.../deu/produkte/detail.php?id=<n>&linie=<line>

Each page yields article number, German machine name, L/B/H in mm, GG (total
weight) / GM (weight stack) in kg, a 2003-2007 price, and a product photo. That
is richer than anything the live scrapers return — they give brand + model only.

Seven product lines: StandardLine, Avantgarde, ExclusiveLine, FitnessLine,
DynamicLineDS, DynamicLineDG, ActiveLine.

    python catalog/scrapers/wayback_hbp.py           # scrape -> hbp_from_wayback.json + hbp_images/

Snapshot caveat: this is the 2003-2007 site. Some models are long discontinued —
fine for recognising a machine on a gym floor, which is what the catalog is for.
"""
from __future__ import annotations

import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "hbp_from_wayback.json"
IMG_DIR = ROOT / "hbp_images"

CDX = "http://web.archive.org/cdx/search/cdx"
WB = "https://web.archive.org/web/{ts}id_/{url}"
DOMAINS = ("hbp-gmbh.com", "hbp-gmbh.de")
UA = "rackd-catalog/0.1 (+https://github.com/sguhring/rackd; archival gym machine catalog)"

# the page is HTML 4.0 with Latin-1 umlauts and no charset declaration
ENC = "latin-1"
RE_DETAIL = re.compile(r"detail\.php\?id=(\d+)&(?:amp;)?linie=(\w+)", re.I)
RE_TITLE = re.compile(
    r'class="titel">\s*<b>\s*(?P<art>[^<]*?)\s*</span>\s*<br>\s*'
    r'<span class="titel">\s*(?P<name>.*?)\s*</span>', re.S | re.I)
RE_TECH = re.compile(r'class="techn_angaben">(?P<tech>.*?)</span>', re.S | re.I)
RE_IMG = re.compile(r'src="(?P<src>[^"]*/upload/[^"]+)"', re.I)
RE_DIMS = re.compile(r"L\s*(\d+)\s*B\s*(\d+)\s*H\s*(\d+)", re.I)
# StandardLine/Fitness/Dynamic write "GG: 278 kg"; Avantgarde/Exclusive/Active omit the colon
RE_GG = re.compile(r"GG:?\s*([\d.,]+)\s*kg", re.I)
RE_GM = re.compile(r"GM:?\s*([\d.,]+)\s*kg", re.I)
# ActiveLine prefixes the specs with English / French names: "Squat / Squats / GG 178 kg L …"
RE_TRANS = re.compile(r"^(?P<t>[^0-9]{3,}?)\s*/?\s*(?=(?:GG|L)\b)", re.I)
RE_PRICE = re.compile(r"Preis:\s*([\d.,]+)", re.I)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=90, follow_redirects=True)


def _get(cl: httpx.Client, url: str, tries: int = 4) -> httpx.Response | None:
    """Archive.org rate-limits and 5xx's under load; back off rather than hammer."""
    for attempt in range(tries):
        try:
            r = cl.get(url)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503, 502, 504):
                time.sleep(2 * (attempt + 1))
                continue
            return None
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def discover() -> dict[tuple[str, str], str]:
    """(id, line) -> newest snapshot timestamp+url, across both dead domains."""
    found: dict[tuple[str, str], tuple[str, str]] = {}
    with _client() as cl:
        for dom in DOMAINS:
            r = _get(cl, f"{CDX}?url={dom}&matchType=domain&output=text"
                          f"&fl=timestamp,original&collapse=urlkey&limit=5000")
            if not r:
                continue
            for line in r.text.splitlines():
                parts = line.split()
                if len(parts) != 2:
                    continue
                ts, url = parts
                m = RE_DETAIL.search(url)
                if not m:
                    continue
                key = (m.group(1), m.group(2))
                if key not in found or ts > found[key][0]:   # keep the newest capture
                    found[key] = (ts, url)
    return {k: WB.format(ts=v[0], url=v[1]) for k, v in found.items()}


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse(body: str, pid: str, line: str) -> dict | None:
    t = RE_TITLE.search(body)
    if not t:
        return None
    name = _text(t.group("name"))
    if not name:
        return None
    tech = _text(RE_TECH.search(body).group("tech")) if RE_TECH.search(body) else ""
    rec: dict = {
        "id": int(pid), "line": line,
        "article": _text(t.group("art")) or None,
        "name": name,
        "specs_raw": tech or None,
    }
    if tr := RE_TRANS.match(tech):
        t = tr.group("t").strip(" /")
        if t and not t.lower().startswith(("l ", "gg", "gm")):
            rec["translation"] = t
    if d := RE_DIMS.search(tech):
        rec["dims_mm"] = {"l": int(d.group(1)), "w": int(d.group(2)), "h": int(d.group(3))}
    for key, rx in (("total_kg", RE_GG), ("stack_kg", RE_GM)):
        if m := rx.search(tech):
            rec[key] = float(m.group(1).replace(".", "").replace(",", "."))
    if p := RE_PRICE.search(tech):
        rec["price_eur"] = float(p.group(1).replace(".", "").replace(",", "."))
    if i := RE_IMG.search(body):
        src = i.group("src").split("/upload/")[-1]
        rec["image"] = src.replace("_kl.", ".")          # prefer full size over _kl thumb
    return rec


def scrape_one(cl: httpx.Client, key: tuple[str, str], url: str) -> dict | None:
    r = _get(cl, url)
    if not r:
        return None
    return parse(r.content.decode(ENC, "replace"), key[0], key[1])


def fetch_images(records: list[dict], snapshots: dict[str, str]) -> int:
    IMG_DIR.mkdir(exist_ok=True)
    todo = [r for r in records if r.get("image")]
    got = 0
    with _client() as cl:
        def one(rec: dict) -> bool:
            fn = rec["image"]
            dest = IMG_DIR / fn
            if dest.exists() and dest.stat().st_size > 0:
                return True
            # only ~53 of the 199 photos were ever captured; where the full size is
            # missing, fall back to the "_kl" thumbnail rather than lose the machine.
            url = snapshots.get(fn) or snapshots.get(fn.replace(".", "_kl.", 1))
            if not url:
                return False
            r = _get(cl, url)
            if not r or not r.content or len(r.content) < 200:
                return False
            dest.write_bytes(r.content)
            return True

        with ThreadPoolExecutor(max_workers=4) as ex:
            got = sum(1 for ok in ex.map(one, todo) if ok)
    return got


def discover_images() -> dict[str, str]:
    """filename -> newest archived URL for /upload/ product photos."""
    best: dict[str, tuple[str, str]] = {}
    with _client() as cl:
        for dom in DOMAINS:
            r = _get(cl, f"{CDX}?url={dom}&matchType=domain&output=text"
                          f"&fl=timestamp,original&collapse=urlkey&limit=5000")
            if not r:
                continue
            for line in r.text.splitlines():
                parts = line.split()
                if len(parts) != 2 or "/upload/" not in parts[1]:
                    continue
                ts, url = parts
                fn = url.split("/upload/")[-1]
                if fn not in best or ts > best[fn][0]:
                    best[fn] = (ts, url)
    return {fn: WB.format(ts=v[0], url=v[1]) for fn, v in best.items()}


def main() -> None:
    print("discovering archived product pages…")
    pages = discover()
    print(f"  {len(pages)} product pages across "
          f"{len({l for _, l in pages})} lines")

    print("scraping…")
    records: list[dict] = []
    with _client() as cl:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for rec in ex.map(lambda kv: scrape_one(cl, kv[0], kv[1]), pages.items()):
                if rec:
                    records.append(rec)
    records.sort(key=lambda r: (r["line"], r["id"]))
    print(f"  parsed {len(records)}/{len(pages)}")

    print("discovering archived photos…")
    snaps = discover_images()
    n = fetch_images(records, snaps)
    print(f"  downloaded {n} photos into {IMG_DIR.name}/")

    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"wrote {OUT_JSON.name} ({len(records)} machines)")


if __name__ == "__main__":
    main()
