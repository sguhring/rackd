"""Assemble tools/cap/dist/ — the files the phone app actually needs — from www/.

    python tools/cap/stage.py

www/ is the dev tree: it also holds the curate/classify pages, contact sheets and
every source photo the catalog pipeline writes under img/<brand>/ (≈120 MB the app
never opens). Capacitor packages webDir wholesale, so build.ps1 stages a lean copy
here first and capacitor.config.json points at dist/ instead of www/.

What goes in:
  - the app shell (index.html, icons.js, sw.js, manifest, icons, starter_machines.json)
  - catalog/ (catalog.json + per-machine thumbnails from api/export_bundle.py)
  - img/<hash>.png cutouts that are still referenced — the hash of a marketplace
    image URL still present in the DB or starter_machines.json (imgHash in index.html)
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

CAP = Path(__file__).resolve().parent
ROOT = CAP.parent.parent
WWW, DIST = CAP / "www", CAP / "dist"
DB = ROOT / "api" / "rackd.db"
SHELL = ["index.html", "icons.js", "sw.js", "manifest.webmanifest", "icon-192.png", "icon-512.png",
         "icon-512-maskable.png", "starter_machines.json"]


def img_hash(s: str) -> str:
    """Port of imgHash() in index.html: djb2 xor variant, unsigned 32-bit, hex."""
    h = 5381
    for c in s:
        h = ((h * 33) & 0xFFFFFFFF) ^ ord(c)
    return format(h & 0xFFFFFFFF, "x")


def referenced_hashes() -> set[str]:
    urls: set[str] = set()
    con = sqlite3.connect(DB)
    urls.update(u for (u,) in con.execute("select image_url from machine where image_url like 'http%'"))
    urls.update(u for (u,) in con.execute("select image_url from libraryexercise where image_url like 'http%'"))
    starter = (WWW / "starter_machines.json").read_text(encoding="utf-8")
    urls.update(re.findall(r'"img":\s*"(http[^"]+)"', starter))
    return {img_hash(u) for u in urls}


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    for name in SHELL:
        shutil.copy2(WWW / name, DIST / name)
    shutil.copytree(WWW / "catalog", DIST / "catalog")
    keep = referenced_hashes()
    (DIST / "img").mkdir()
    n = 0
    for p in (WWW / "img").glob("*.png"):
        if p.stem in keep:
            shutil.copy2(p, DIST / "img" / p.name)
            n += 1
    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"dist: shell + catalog + {n} cutouts, {total / 1048576:.1f} MB")


if __name__ == "__main__":
    main()
