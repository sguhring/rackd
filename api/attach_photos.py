"""Attach local product photos to their matching catalog machine.

Each photo is base64-inlined as a data: URI into machine.image_url (overwriting
the scraped URL). If a matched machine isn't in any gym, it's added to one so the
app — which only shows a gym's machines — can display it.

Usage:  python attach_photos.py
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from sqlmodel import Session, select

from database import engine
from models import GymMachine, Machine

PHOTOS = Path(__file__).resolve().parent.parent / "tools" / "photo3d" / "in"

# photo file -> the catalog machine.id it depicts (confirmed by eye + brand/model)
MATCHES: dict[str, int] = {
    "0_Hammer.jpg": 595,   # Hammer Strength · ISO Lateral Plate Loaded 10 Degree Fly
    "1_Gymleco.jpg": 303,  # Gymleco · 010 Seated Row
    "2_Cybex.jpg": 48,     # Cybex · 45 Degree Linear Leg Press
    "3_Life.jpg": 876,     # Life Fitness · Insignia Series Shoulder Press (not in any gym)
    "4_Hoist.jpg": 752,    # Hoist · HD Lateral Raise
}

# gym to drop a matched-but-orphaned machine into, so it's visible in the app
FALLBACK_GYM_ID = 1  # Iron Works


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def run() -> None:
    with Session(engine) as s:
        for fname, machine_id in MATCHES.items():
            path = PHOTOS / fname
            if not path.exists():
                print(f"  [skip] missing photo: {path}")
                continue
            machine = s.get(Machine, machine_id)
            if not machine:
                print(f"  [skip] no machine id={machine_id} for {fname}")
                continue

            machine.image_url = data_uri(path)
            s.add(machine)

            in_gym = s.exec(
                select(GymMachine).where(GymMachine.machine_id == machine_id)
            ).first()
            note = ""
            if not in_gym:
                s.add(GymMachine(gym_id=FALLBACK_GYM_ID, machine_id=machine_id,
                                 added_by="photo"))
                note = f"  (added to gym {FALLBACK_GYM_ID} — was in no gym)"

            kb = path.stat().st_size // 1024
            print(f"  [ok] {fname:16} -> machine {machine_id} {machine.model!r} "
                  f"[{kb} KB]{note}")
        s.commit()
    print("done.")


if __name__ == "__main__":
    run()
