"""SQLModel models for rackd. Mirrors docs/schema.sql.

Core idea: a gym is a SUBSET of the global machine catalog (GymMachine join),
and sets reference a specific GymMachine so progression is tracked per machine.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel


class Brand(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    abbr: str | None = None
    color: str | None = None


class Exercise(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    name: str
    muscle_group: str | None = None
    equipment_category: str | None = None


class Machine(SQLModel, table=True):
    """A specific branded model in the global catalog."""
    id: int | None = Field(default=None, primary_key=True)
    brand_id: int = Field(foreign_key="brand.id", index=True)
    model: str
    machine_type: str | None = None  # mechanism: plate-loaded / selectorized / cable / ...
    exercise_id: int | None = Field(default=None, foreign_key="exercise.id")
    muscle_label: str | None = None
    image_url: str | None = None
    source: str | None = None


class Gym(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    area: str | None = None
    lat: float | None = None
    lng: float | None = None


class GymMachine(SQLModel, table=True):
    """Which catalog machines a gym actually has — the per-gym subset."""
    id: int | None = Field(default=None, primary_key=True)
    gym_id: int = Field(foreign_key="gym.id", index=True)
    machine_id: int = Field(foreign_key="machine.id")
    added_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Workout(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    name: str | None = None
    gym_id: int | None = Field(default=None, foreign_key="gym.id")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None


class Set(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workout_id: int = Field(foreign_key="workout.id", index=True)
    user_id: str = Field(index=True)
    gym_machine_id: int | None = Field(default=None, foreign_key="gymmachine.id")
    exercise_id: int | None = Field(default=None, foreign_key="exercise.id")
    weight_kg: Decimal
    reps: int
    is_pr: bool = False
    logged_at: datetime = Field(default_factory=datetime.utcnow)
