"""Overlay free Everkinetic line-art illustrations onto matching library exercises.

Source: github.com/chaosbastler/opentraining-exercises (Everkinetic drawings),
licensed CC BY-SA 3.0 — attribute "Everkinetic" wherever these are shown.

Each exercise has a "-1" (start) and "-2" (end) pose as .png (~195 exercises) and
some as .svg (~71). We take the start pose, prefer svg, and match to our library
exercises by a loose normalised name (plural-tolerant). Unmatched exercises keep
their free-exercise-db photo.

    python everkinetic_images.py
"""
from __future__ import annotations

import json
import re
import urllib.request

from sqlmodel import Session, select

from database import engine
from models import LibraryExercise

REPO = "chaosbastler/opentraining-exercises"
RAW = f"https://raw.githubusercontent.com/{REPO}/master/"


STOP = {"with", "on", "the", "a", "to", "and", "of", "in", "your", "ball",
        "stability", "medium", "wide", "close", "grip", "version"}


def _tokens(name: str) -> frozenset[str]:
    """Stemmed, stop-word-free word set: 'Barbell Upright Rows' -> {barbel,upright,row}."""
    out = set()
    for w in re.split(r"[^a-z0-9]+", name.lower()):
        if not w or w in STOP:
            continue
        if w.endswith("es") and len(w) > 4:
            w = w[:-2]
        elif w.endswith("s") and len(w) > 3:
            w = w[:-1]
        out.add(w)
    return frozenset(out)


def fetch_index() -> list[tuple[frozenset[str], str]]:
    """(token set, start-pose image url) per Everkinetic exercise, svg preferred."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/git/trees/master?recursive=1",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"},
    )
    tree = json.load(urllib.request.urlopen(req, timeout=30))["tree"]

    svg: dict[frozenset[str], str] = {}
    png: dict[frozenset[str], str] = {}
    for node in tree:
        m = re.fullmatch(r"(?:svg/)?(.+?)-1\.(svg|png)", node["path"])
        if not m:
            continue
        base, ext = m.group(1).replace("-", " "), m.group(2)
        (svg if ext == "svg" else png)[_tokens(base)] = RAW + node["path"]

    merged = dict(png)
    merged.update(svg)            # svg wins on overlap (crisper)
    return list(merged.items())


def _best(lib_toks: frozenset[str], index) -> str | None:
    """Most specific Everkinetic entry whose tokens fit this library exercise."""
    best, best_len = None, 1
    for toks, url in index:
        if len(toks) >= 2 and toks <= lib_toks and len(toks) > best_len:
            best, best_len = url, len(toks)
        elif toks == lib_toks:                      # exact (handles 1-word names)
            return url
    return best


def run() -> None:
    index = fetch_index()
    print(f"Everkinetic illustrations: {len(index)} exercises")

    with Session(engine) as s:
        rows = s.exec(select(LibraryExercise)).all()
        hits = 0
        for ex in rows:
            url = _best(_tokens(ex.name), index)
            if url:
                ex.image_url = url
                s.add(ex)
                hits += 1
        s.commit()
        print(f"matched {hits}/{len(rows)} library exercises "
              f"({len(rows) - hits} keep their photo).")


if __name__ == "__main__":
    run()
