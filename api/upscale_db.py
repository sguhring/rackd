"""Bake AI-upscaled renders into the DB `image_url`, in place.

Super-resolves each machine's render 4x (Real-ESRGAN — see upscale.py) and writes
the result back as a base64 JPEG data URI, so both the app and future Notion
exports use the sharper image instead of the ~250px source render.

Scoped to one catalog source at a time (default Watson). Idempotent: a render
that is already large enough (width >= ALREADY px) is assumed upscaled and
skipped, so re-running is safe and cheap.

    python upscale_db.py                        # watson-brochure
    python upscale_db.py --source prime-brochure
    python upscale_db.py --dry                  # report what would change, no writes
"""
from __future__ import annotations

import base64
import io
import sys

import fitz
from sqlmodel import Session, select

from database import engine
from export_notion import image_bytes        # resolves data: URIs and http renders
from models import Machine
from upscale import ensure_binary, upscale_jpeg

ALREADY = 700   # px width at/above which a render is treated as already-upscaled


def width_of(raw: bytes) -> int:
    try:
        return fitz.Pixmap(io.BytesIO(raw)).width
    except Exception:                          # noqa: BLE001 — unreadable image, treat as 0
        return 0


def run(source: str, dry: bool) -> None:
    with Session(engine) as s:
        machines = s.exec(
            select(Machine).where(Machine.source == source, Machine.image_url != None)  # noqa: E711
        ).all()
        print(f"{source}: {len(machines)} machines with an image_url.")
        if not dry:
            ensure_binary()

        up = skip = fail = 0
        for m in machines:
            got = image_bytes(m.image_url)
            if not got:
                skip += 1
                continue
            raw, _, _ = got
            if width_of(raw) >= ALREADY:        # already upscaled on a previous run
                skip += 1
                continue
            if dry:
                up += 1
                continue
            try:
                big = upscale_jpeg(raw)
            except Exception as e:              # noqa: BLE001 — model/subprocess hiccup, skip one
                print(f"  ! machine {m.id} ({m.model[:40]}) failed: {e}")
                fail += 1
                continue
            m.image_url = "data:image/jpeg;base64," + base64.b64encode(big).decode("ascii")
            s.add(m)
            up += 1
            if up % 20 == 0:
                s.commit()
                print(f"  {up} upscaled…")
        if not dry:
            s.commit()

        verb = "would upscale" if dry else "upscaled"
        print(f"\ndone — {verb} {up}, skipped {skip} (already big / no image)"
              f"{'' if not fail else f', {fail} failed'}.")


if __name__ == "__main__":
    source = sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv else "watson-brochure"
    run(source, dry="--dry" in sys.argv)
