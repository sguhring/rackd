"""rackd API — gyms, their machines, and set logging with per-machine history.

Run:  uvicorn main:app --reload   →   http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import base64
import re
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import Session, select

from database import get_session, init_db
from models import (Brand, Exercise, Gym, GymMachine, LibraryExercise, Machine,
                    Set, Workout)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="rackd", version="0.1.0", lifespan=lifespan)

# Dev: the static PWA is served from a different origin/port, so allow cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── response shapes ───────────────────────────────────────────────────────────

class GymOut(BaseModel):
    id: int
    name: str
    area: str | None
    machine_count: int
    brands: list[str]  # a few distinct brands on this floor, for badges


class MachineOut(BaseModel):
    gym_machine_id: int
    brand: str
    model: str
    machine_type: str | None
    muscle_label: str | None
    muscle_group: str | None
    image_url: str | None
    last: dict | None  # {"weight_kg", "reps", "sets", "logged_at"} or None


class LogSetIn(BaseModel):
    user_id: str
    workout_id: int | None = None
    gym_machine_id: int | None = None
    exercise_id: int | None = None
    weight_kg: Decimal
    reps: int


class CatalogExerciseOut(BaseModel):
    slug: str
    name: str
    muscle_group: str | None
    machine_count: int


class CatalogBrandOut(BaseModel):
    brand: str
    count: int


class CatalogMachineOut(BaseModel):
    machine_id: int
    brand: str
    model: str
    machine_type: str | None
    muscle_label: str | None
    image_url: str | None


class CatalogSearchOut(BaseModel):
    machine_id: int
    brand: str
    model: str
    machine_type: str | None
    muscle_label: str | None
    muscle_group: str | None
    image_url: str | None


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/catalog/exercises", response_model=list[CatalogExerciseOut])
def catalog_exercises(session: Session = Depends(get_session)):
    """Every movement that has at least one machine, with how many models exist."""
    out = []
    for ex in session.exec(select(Exercise).order_by(Exercise.name)).all():
        count = len(session.exec(
            select(Machine).where(Machine.exercise_id == ex.id)
        ).all())
        if count:
            out.append(CatalogExerciseOut(slug=ex.slug, name=ex.name,
                                          muscle_group=ex.muscle_group, machine_count=count))
    return out


@app.get("/catalog/brands", response_model=list[CatalogBrandOut])
def catalog_brands(exercise: str, session: Session = Depends(get_session)):
    """The brands (publishers) that make a machine for this movement, most models first."""
    ex = session.exec(select(Exercise).where(Exercise.slug == exercise)).first()
    if not ex:
        raise HTTPException(404, "exercise not found")
    counts: dict[str, int] = {}
    rows = session.exec(
        select(Brand.name)
        .where(Machine.exercise_id == ex.id)
        .where(Brand.id == Machine.brand_id)
    ).all()
    for name in rows:
        counts[name] = counts.get(name, 0) + 1
    return [CatalogBrandOut(brand=b, count=c)
            for b, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


@app.get("/catalog/machines", response_model=list[CatalogMachineOut])
def catalog_machines(exercise: str, brand: str | None = None,
                     session: Session = Depends(get_session)):
    """The specific models for a movement (optionally filtered to one brand)."""
    ex = session.exec(select(Exercise).where(Exercise.slug == exercise)).first()
    if not ex:
        raise HTTPException(404, "exercise not found")
    q = (select(Machine, Brand)
         .where(Machine.exercise_id == ex.id)
         .where(Brand.id == Machine.brand_id))
    if brand:
        q = q.where(Brand.name == brand)
    out = []
    for m, b in session.exec(q.order_by(Machine.model)).all():
        out.append(CatalogMachineOut(
            machine_id=m.id, brand=b.name, model=m.model,
            machine_type=m.machine_type, muscle_label=m.muscle_label,
            image_url=m.image_url))
    return out


class LibraryOut(BaseModel):
    name: str
    equipment: str | None
    muscle_group: str | None
    muscle_label: str | None
    image_url: str | None


@app.get("/library", response_model=list[LibraryOut])
def library(session: Session = Depends(get_session)):
    """The generic exercise library (free-exercise-db) — default builder options."""
    rows = session.exec(select(LibraryExercise).order_by(LibraryExercise.name)).all()
    return [LibraryOut(name=e.name, equipment=e.equipment, muscle_group=e.muscle_group,
                       muscle_label=e.muscle_label, image_url=e.image_url) for e in rows]


def _search_words(text: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9]+", " ", text.lower()).split() if w]


def _edit_distance(a: str, b: str, max_dist: int = 2) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            val = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            cur.append(val)
            best = min(best, val)
        if best > max_dist:
            return max_dist + 1
        prev = cur
    return prev[-1]


def _fuzzy_score(query_words: list[str], fields: list[str | None]) -> float:
    hay_words = _search_words(" ".join(f for f in fields if f))
    if not query_words or not hay_words:
        return 0
    total = 0
    for qw in query_words:
        best = 0
        for hw in hay_words:
            if hw == qw:
                best = max(best, 110)
            elif (len(qw) >= 2 and hw.startswith(qw)) or (len(hw) >= 3 and qw.startswith(hw)):
                best = max(best, 88)
            elif (len(qw) >= 3 and qw in hw) or (len(hw) >= 4 and hw in qw):
                best = max(best, 72)
            elif len(qw) >= 4:
                max_dist = 1 if len(qw) <= 4 else 2
                if _edit_distance(qw, hw, max_dist) <= max_dist:
                    best = max(best, 58 if len(qw) <= 4 else 66)
        if not best:
            return 0
        total += best
    return total / len(query_words)


@app.get("/catalog/search", response_model=list[CatalogSearchOut])
def catalog_search(q: str, limit: int = 30, session: Session = Depends(get_session)):
    """Free-text search across the whole catalog by model, brand or movement name."""
    q = q.strip()
    if len(q) < 2:
        return []
    q_words = _search_words(q)
    query = (select(Machine, Brand, Exercise)
             .where(Brand.id == Machine.brand_id)
             .join(Exercise, isouter=True))
    # every word must match somewhere (model / brand / movement) — so "nautilus row" works
    for word in q_words:
        like = f"%{word}%"
        query = query.where(or_(Machine.model.ilike(like), Brand.name.ilike(like),
                                Exercise.name.ilike(like)))
    rows = session.exec(query.order_by(Brand.name, Machine.model).limit(limit)).all()
    if len(rows) < limit:
        wide = session.exec((select(Machine, Brand, Exercise)
                             .where(Brand.id == Machine.brand_id)
                             .join(Exercise, isouter=True))).all()
        seen = {(m.id, b.id) for m, b, _ in rows}
        scored = []
        for m, b, ex in wide:
            if (m.id, b.id) in seen:
                continue
            score = _fuzzy_score(q_words, [b.name, m.model, m.machine_type,
                                           m.muscle_label, ex.name if ex else None])
            if score:
                scored.append((score, m, b, ex))
        scored.sort(key=lambda x: (-x[0], x[2].name, x[1].model))
        rows.extend((m, b, ex) for _, m, b, ex in scored[:max(0, limit - len(rows))])
    return [CatalogSearchOut(
        machine_id=m.id, brand=b.name, model=m.model, machine_type=m.machine_type,
        muscle_label=m.muscle_label, muscle_group=ex.muscle_group if ex else None,
        image_url=m.image_url) for m, b, ex in rows]


class CatalogRowOut(BaseModel):
    machine_id: int
    brand: str
    model: str
    machine_type: str | None
    muscle_label: str | None
    muscle_group: str | None   # push / pull / legs / core (the "body part" facet)
    exercise: str | None       # the movement this model maps to, if any
    source: str | None
    gyms: list[str]            # which gym floors carry this model
    has_image: bool


@app.get("/catalog/all", response_model=list[CatalogRowOut])
def catalog_all(session: Session = Depends(get_session)):
    """The whole machine catalog as one flat table — the data-explorer dashboard feed.

    Image bytes are NOT inlined (the catalog is ~9 MB of them); each row carries
    `has_image` and the client lazy-loads thumbnails from /catalog/machines/{id}/image.
    """
    gyms_by_machine: dict[int, list[str]] = {}
    for mid, gname in session.exec(
        select(GymMachine.machine_id, Gym.name).where(Gym.id == GymMachine.gym_id)
    ).all():
        gyms_by_machine.setdefault(mid, []).append(gname)

    rows = session.exec(
        select(Machine, Brand, Exercise)
        .where(Brand.id == Machine.brand_id)
        .join(Exercise, isouter=True)
        .order_by(Brand.name, Machine.model)
    ).all()
    return [CatalogRowOut(
        machine_id=m.id, brand=b.name, model=m.model,
        machine_type=m.machine_type, muscle_label=m.muscle_label,
        muscle_group=ex.muscle_group if ex else None,
        exercise=ex.name if ex else None, source=m.source,
        gyms=sorted(set(gyms_by_machine.get(m.id, []))),
        has_image=bool(m.image_url),
    ) for m, b, ex in rows]


@app.get("/catalog/machines/{machine_id}/image")
def machine_image(machine_id: int, session: Session = Depends(get_session)):
    """Serve one machine's render. Stored renders are base64 data URIs (decoded to
    bytes here so the browser can cache them); a few seeded rows hold an external
    URL, which we redirect to."""
    m = session.get(Machine, machine_id)
    if not m or not m.image_url:
        raise HTTPException(404, "no image")
    uri = m.image_url
    if uri.startswith("data:"):
        header, _, b64 = uri.partition(",")
        media = header[5:].split(";")[0] or "image/jpeg"
        return Response(content=base64.b64decode(b64), media_type=media,
                        headers={"Cache-Control": "public, max-age=86400"})
    return RedirectResponse(uri)


@app.get("/gyms", response_model=list[GymOut])
def list_gyms(session: Session = Depends(get_session)):
    out = []
    for gym in session.exec(select(Gym)).all():
        count = len(session.exec(
            select(GymMachine).where(GymMachine.gym_id == gym.id)
        ).all())
        brands = session.exec(
            select(Brand.name)
            .where(GymMachine.gym_id == gym.id)
            .where(Machine.id == GymMachine.machine_id)
            .where(Brand.id == Machine.brand_id)
            .distinct()
        ).all()
        out.append(GymOut(id=gym.id, name=gym.name, area=gym.area,
                          machine_count=count, brands=list(brands)[:3]))
    return out


@app.get("/gyms/{gym_id}/machines", response_model=list[MachineOut])
def gym_machines(gym_id: int, user_id: str | None = None,
                 session: Session = Depends(get_session)):
    """The machines on this gym's floor, each with the user's last session on it."""
    if not session.get(Gym, gym_id):
        raise HTTPException(404, "gym not found")

    rows = session.exec(
        select(GymMachine, Machine, Brand, Exercise)
        .where(GymMachine.gym_id == gym_id)
        .where(Machine.id == GymMachine.machine_id)
        .where(Brand.id == Machine.brand_id)
        .join(Exercise, isouter=True)
    ).all()

    out = []
    for gm, machine, brand, exercise in rows:
        out.append(MachineOut(
            gym_machine_id=gm.id,
            brand=brand.name,
            model=machine.model,
            machine_type=machine.machine_type,
            muscle_label=machine.muscle_label,
            muscle_group=exercise.muscle_group if exercise else None,
            image_url=machine.image_url,
            last=_last_on_machine(session, user_id, gm.id) if user_id else None,
        ))
    return out


@app.post("/sets")
def log_set(body: LogSetIn, session: Session = Depends(get_session)):
    """Log a set. Computes is_pr against this user's history on this machine."""
    if not body.gym_machine_id and not body.exercise_id:
        raise HTTPException(400, "gym_machine_id or exercise_id required")

    workout_id = body.workout_id
    if workout_id is None:
        w = Workout(user_id=body.user_id, started_at=datetime.utcnow())
        session.add(w)
        session.commit()
        session.refresh(w)
        workout_id = w.id

    is_pr = _is_pr(session, body)

    s = Set(
        workout_id=workout_id,
        user_id=body.user_id,
        gym_machine_id=body.gym_machine_id,
        exercise_id=body.exercise_id,
        weight_kg=body.weight_kg,
        reps=body.reps,
        is_pr=is_pr,
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return {"id": s.id, "workout_id": workout_id, "is_pr": is_pr}


# ── helpers ───────────────────────────────────────────────────────────────────

def _last_on_machine(session: Session, user_id: str, gym_machine_id: int) -> dict | None:
    """The user's most recent past session on a specific machine."""
    last = session.exec(
        select(Set)
        .where(Set.user_id == user_id, Set.gym_machine_id == gym_machine_id)
        .order_by(Set.logged_at.desc())
    ).first()
    if not last:
        return None
    same_day = session.exec(
        select(Set).where(
            Set.user_id == user_id,
            Set.gym_machine_id == gym_machine_id,
            Set.logged_at >= last.logged_at.replace(hour=0, minute=0, second=0, microsecond=0),
        )
    ).all()
    return {
        "weight_kg": float(last.weight_kg),
        "reps": last.reps,
        "sets": len(same_day),
        "logged_at": last.logged_at.isoformat(),
    }


def _is_pr(session: Session, body: LogSetIn) -> bool:
    """Beat the best previous weight (or weight-matched reps) on THIS machine only."""
    if not body.gym_machine_id:
        return False
    best = session.exec(
        select(Set)
        .where(Set.user_id == body.user_id, Set.gym_machine_id == body.gym_machine_id)
        .order_by(Set.weight_kg.desc(), Set.reps.desc())
    ).first()
    if not best:
        return False
    if body.weight_kg > best.weight_kg:
        return True
    return body.weight_kg == best.weight_kg and body.reps > best.reps
