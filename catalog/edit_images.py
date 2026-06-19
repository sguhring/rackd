"""Edit each machine photo into a clean, consistent cutout for the app.

Downloads every machine's source photo, removes the background (rembg / U^2-Net),
trims + squares it, and saves a transparent PNG to web/pwa/img/<hash>.png. The app
overlays that cutout on a light tile (falling back to the line icon if it's missing),
so the catalog shows the real, recognizable machine in a uniform style.

    pip install rembg onnxruntime pillow httpx
    python edit_images.py            # resumable: skips files already done

Note: these are derivatives of the source product photos — fine for dev, but for a
commercial launch prefer owned/licensed imagery (see docs note / user-submitted photos).
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps
from rembg import new_session, remove

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "scraped_machines.json"
OUT = ROOT / "web" / "pwa" / "img"
UA = {"User-Agent": "Mozilla/5.0 (rackd image editor)"}
SIZE = 256


def img_hash(s: str) -> str:
    """Must match imgHash() in the PWA: djb2-xor over char codes, 32-bit."""
    h = 5381
    for ch in s:
        h = (((h * 33) & 0xFFFFFFFF) ^ ord(ch)) & 0xFFFFFFFF
    return format(h, "x")


def fetch(url: str) -> Image.Image:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:  # noqa: S310
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def edit(im: Image.Image, session) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    cut = remove(im, session=session)            # RGBA, background removed
    bbox = cut.getbbox()
    if bbox:
        cut = cut.crop(bbox)
    cut = ImageOps.contain(cut, (SIZE - 16, SIZE - 16))
    sq = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sq.alpha_composite(cut, ((SIZE - cut.width) // 2, (SIZE - cut.height) // 2))
    return sq


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    urls = sorted({r["image_url"] for r in rows if r.get("image_url")})
    session = new_session("u2netp")
    done = ok = fail = 0
    for i, url in enumerate(urls, 1):
        dest = OUT / f"{img_hash(url)}.png"
        if dest.exists():
            done += 1
            continue
        try:
            edit(fetch(url), session).save(dest)
            ok += 1
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"  ! {url[:70]} :: {type(e).__name__}", file=sys.stderr)
        if i % 25 == 0:
            print(f"  {i}/{len(urls)}  new={ok} skipped={done} failed={fail}", flush=True)
    print(f"done. {len(urls)} urls · new={ok} already={done} failed={fail} · -> {OUT}")


if __name__ == "__main__":
    run()
