"""Point each in-gym Hoist machine at its official image from hoistfitness.com.

Two clean collections feed this: selectorized (RS/CL renders) and plate-loaded
(RPL/CF renders). Each machine is mapped by hand to (collection, movement title)
so a plate-loaded machine gets a plate-loaded render, not a stack render.

Usage:  python hoist_images.py
"""
from __future__ import annotations

import json
import urllib.request

from sqlmodel import Session

from database import engine
from models import Machine

FEEDS = {
    "sel": "https://www.hoistfitness.com/collections/ccat-selectorized/products.json?limit=250",
    "pl":  "https://www.hoistfitness.com/collections/ccat-plate-loaded/products.json?limit=250",
}

# machine.id -> (collection, product title to borrow the image from)
MAP: dict[int, tuple[str, str]] = {
    749: ("sel", "Abdominals"),              # Abdominal Crunch
    750: ("sel", "Low Back"),                # Hyper Extension - back
    751: ("sel", "Leg Extension"),           # Leg Extension & Leg Curl combo
    752: ("sel", "Lateral Raise"),           # HD Lateral Raise
    754: ("sel", "Glute Master"),            # HD Multi Hip & Glute
    755: ("sel", "Lat Pulldown"),            # Lat Pulldown & Mid Row combo
    761: ("sel", "Inner / Outer Thigh"),     # Abductor & Adductor combo
    765: ("sel", "Seated Dip"),              # RS-1101 Seated Dip
    766: ("sel", "Biceps Curl"),             # RS-1102 Biceps Curl
    768: ("sel", "Pec Fly"),                 # RS-1302 Converging Pec Fly
    771: ("sel", "Leg Press"),               # RS-1403 Leg Press
    776: ("sel", "Chin/Dip Assist"),         # VKR Dip & Leg Raise (closest)
    # plate-loaded machines -> plate-loaded renders (760 & 764 are exact code matches)
    756: ("pl", "Commercial Incline Leverage Row"),  # Chest Supported T Bar Row
    758: ("pl", "Shoulder Press"),                   # ISO Lateral Plate Loaded Shoulder Press
    760: ("pl", "Standing Calf Raise"),              # RPL-5405 Standing Calf Raise
    762: ("pl", "Chest Press"),                      # ISO Lateral Plate Loaded Chest Press
    764: ("pl", "Hack Squat/Dead Lift/Shrug"),       # Plate Loaded Hack Squat combo
}


def load_feed(url: str) -> dict[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    products = json.load(urllib.request.urlopen(req, timeout=30))["products"]
    table: dict[str, str] = {}
    for p in products:
        imgs = p.get("images") or []
        if imgs:
            table.setdefault(p["title"].strip(), imgs[0]["src"])
    return table


def run() -> None:
    feeds = {k: load_feed(u) for k, u in FEEDS.items()}
    print("feeds: " + ", ".join(f"{k}={len(v)}" for k, v in feeds.items()))

    with Session(engine) as s:
        hit = 0
        for mid, (coll, title) in MAP.items():
            src = feeds[coll].get(title)
            machine = s.get(Machine, mid)
            if not src or not machine:
                print(f"  [skip] id={mid} {coll}:{title!r} src={bool(src)}")
                continue
            machine.image_url = src
            s.add(machine)
            hit += 1
            print(f"  [ok] {mid} {machine.model[:32]:34} <- {coll}:{title}")
        s.commit()
    print(f"done. {hit}/{len(MAP)} Hoist machines updated.")


if __name__ == "__main__":
    run()
