"""rackd API — gyms, their machines, and set logging with per-machine history.

Run:  uvicorn main:app --reload   →   http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session, init_db
from models import Brand, Exercise, Gym, GymMachine, Machine, Set, Workout

app = FastAPI(title="rackd", version="0.1.0")

# Dev: the static PWA is served from a different origin/port, so allow cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


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
