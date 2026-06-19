"""Shared brand vocabulary + model-name cleaning, used by every scraper.

Reseller listings name the same brand many ways ('Freemotion', 'Free Motion',
'FreeMotion') and bury the model in marketing noise ('… – Like New', '(Remanufactured)',
HTML entities). This module canonicalises brands and strips that noise so the catalog
dedupes cleanly across sources.
"""
from __future__ import annotations

import html
import re

# Canonical brand -> the aliases that may appear in a title or category (lowercased).
# Order within a value doesn't matter; matching tries the LONGEST alias first so
# 'star trac' wins over a bare 'star'. Extend freely as new brands show up.
_BRAND_ALIASES: dict[str, list[str]] = {
    "Life Fitness": ["life fitness"],
    "Hammer Strength": ["hammer strength"],
    "Cybex": ["cybex"],
    "Precor": ["precor"],
    "Matrix": ["matrix", "matrix fitness"],
    "Technogym": ["technogym"],
    "Nautilus": ["nautilus"],
    "Hoist": ["hoist", "hoist fitness"],
    "Star Trac": ["star trac", "startrac", "star-trac"],
    "StairMaster": ["stairmaster", "stair master"],
    "Body-Solid": ["body-solid", "body solid", "bodysolid"],
    "FreeMotion": ["freemotion", "free motion"],
    "Atlantis": ["atlantis"],
    "Paramount": ["paramount"],
    "MedX": ["medx"],
    "Magnum": ["magnum", "magnum fitness"],
    "Legend Fitness": ["legend fitness", "legend"],
    "Body Masters": ["body masters", "bodymasters"],
    "Icarian": ["icarian"],
    "Vectra": ["vectra"],
    "True Fitness": ["true fitness"],
    "TuffStuff": ["tuffstuff", "tuff stuff"],
    "Keiser": ["keiser"],
    "SportsArt": ["sportsart", "sports art"],
    "Flex Fitness": ["flex fitness"],
    "Muscle D": ["muscle d", "muscle-d"],
    "Arsenal Strength": ["arsenal strength", "arsenal"],
    "Prime Fitness": ["prime fitness"],
    "Panatta": ["panatta"],
    "Gym80": ["gym80", "gym 80"],
    "Watson": ["watson"],
    "Rogers Athletic": ["rogers athletic", "rogers athletics", "roger's athletics",
                        "roger's athletic"],
    "Drax": ["drax fitness", "drax"],
    "Younix": ["younix"],
    "Inspire": ["inspire fitness", "inspire"],
    "BH Fitness": ["bh fitness"],
    # additional brands surfaced from the reseller marketplaces
    "Promaxima": ["promaxima"],
    "Polaris": ["polaris"],
    "Quantum Fitness": ["quantum fitness", "quantum"],
    "Samson": ["samson", "samson equipment"],
    "Dynabody": ["dynabody"],
    "Panatta": ["panatta", "panetta"],
    "TKO": ["tko"],
    "Westside": ["westside"],
    "PowerLift": ["powerlift", "power lift"],
    "Yukon": ["yukon", "yukon fitness"],
    "BodyKore": ["bodykore"],
    "Force USA": ["force usa"],
    "Titan": ["titan fitness", "titan"],
    "Bodycraft": ["bodycraft"],
    "Pendulum": ["pendulum"],
}

# (alias, canonical) sorted longest-alias-first so specific names win.
_ALIAS_INDEX: list[tuple[str, str]] = sorted(
    ((a, canon) for canon, aliases in _BRAND_ALIASES.items() for a in aliases),
    key=lambda t: -len(t[0]),
)


def _norm(s: str) -> str:
    return html.unescape(s or "").replace("’", "'").replace("‘", "'").lower().strip()


def canon_brand(raw: str) -> str:
    n = _norm(raw)
    for alias, canon in _ALIAS_INDEX:
        if n == alias:
            return canon
    return html.unescape(raw or "").strip()


def extract_brand(name: str, categories: list[str] | None = None) -> str | None:
    """Return the canonical brand, or None if no KNOWN brand can be attributed.

    Tries a known alias at the start of the product name (most reliable), then a known
    alias among the categories (resellers like Primo file products under a brand
    category). Returns None rather than guessing — a wrong/garbage brand pollutes the
    catalog worse than a skipped row."""
    n = _norm(name)
    for alias, canon in _ALIAS_INDEX:           # name prefix
        if n.startswith(alias):
            return canon
    for cat in categories or []:                 # brand-as-category
        cn = _norm(cat)
        for alias, canon in _ALIAS_INDEX:
            if cn == alias or cn == f"{alias} fitness":
                return canon
    return None


# --- strength-vs-cardio classification ------------------------------------
# Substring signals matched across a product's type/tags/categories (lowercased).
# A cardio signal drops it (treadmills/bikes/rowers aren't per-machine load tracking);
# otherwise a strength signal keeps it.
STRENGTH_SIGNALS = ("strength training", "strength machine", "strength machines",
                    "selectorized", "pin loaded", "plate loaded", "plate-loaded",
                    "leverage", "gym system", "multi stack", "machine")
CARDIO_SIGNALS = ("cardio", "treadmill", "elliptical", "exercise bike", "recumbent",
                  "upright bike", "spin bike", "rower", "rowing", "stair", "climbmill",
                  "ascent trainer", "arc trainer", "crosstrainer", "cross trainer")
# things resellers file under strength that aren't a single trackable machine
NON_MACHINE_SIGNALS = ("free weight", "dumbbell", "barbell", "kettlebell", "weight plate",
                       "bumper", "olympic bench", "flat bench", "adjustable bench",
                       "flooring", "locker", "accessor", "attachment", "apparel",
                       "circuit", "package", "unit total body")


def is_strength_machine(*texts: str) -> bool:
    """True if the combined text looks like a trackable strength machine."""
    hay = " ".join(t.lower() for t in texts if t)
    if any(c in hay for c in CARDIO_SIGNALS):
        return False
    if any(n in hay for n in NON_MACHINE_SIGNALS):
        return False
    return any(s in hay for s in STRENGTH_SIGNALS)


# --- model-name cleaning --------------------------------------------------
_CONSOLE = re.compile(r"\s*w/.*?console", re.I)
# marketing / condition noise that resellers append, removed anywhere in the title
_NOISE = re.compile(
    r"\b(remanufactured|refurbished|fully refurbished|reconditioned|like new|brand new|"
    r"newest models?|latest models?|current models?|full commercial models?|"
    r"commercial models?|floor models?|open box|demo|clearance|on sale|in stock|"
    r"excellent condition|great condition|good condition|super clean|heavy stacks?|"
    r"fast lead time|various configurations possible|matching pair|beautiful|premium|"
    r"outlet|used|new)\b", re.I)
_PARENS = re.compile(r"\s*\((kg|lb|lbs|each|pair)\)", re.I)
_EMPTY_PARENS = re.compile(r"\s*\(\s*\)")


def clean_model(title: str, brand: str | None = None) -> str:
    s = html.unescape(title or "")
    if brand and s.lower().startswith(brand.lower()):
        s = s[len(brand):]
    s = _CONSOLE.sub("", s)
    s = _NOISE.sub("", s)
    s = _PARENS.sub("", s)
    s = _EMPTY_PARENS.sub("", s)        # '(Remanufactured)' -> '()' -> removed
    # collapse separators left behind by removed phrases
    s = re.sub(r"\s*[–—]\s*", " - ", s)
    s = re.sub(r"(\s*-\s*)+$", "", s)   # trailing dangling separators
    s = re.sub(r"(\s*-\s*){2,}", " - ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -–—\t")
    return s
