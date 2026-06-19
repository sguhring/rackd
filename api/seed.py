"""Load catalog/seed_data.json into the database.

Usage:  python seed.py
"""
import json
from pathlib import Path

from sqlmodel import Session, select

from database import engine, init_db
from models import Brand, Exercise, Gym, GymMachine, Machine

SEED = Path(__file__).resolve().parent.parent / "catalog" / "seed_data.json"


def run() -> None:
    init_db()
    data = json.loads(SEED.read_text())

    with Session(engine) as s:
        if s.exec(select(Brand)).first():
            print("DB already seeded — skipping.")
            return

        brands = {b["name"]: Brand(**b) for b in data["brands"]}
        for b in brands.values():
            s.add(b)
        s.commit()
        for b in brands.values():
            s.refresh(b)

        exercises = {e["slug"]: Exercise(**e) for e in data["exercises"]}
        for e in exercises.values():
            s.add(e)
        s.commit()
        for e in exercises.values():
            s.refresh(e)

        # machines keyed by "Brand Model" so gyms can reference them by full name
        machines: dict[str, Machine] = {}
        for m in data["machines"]:
            ex = exercises.get(m["exercise"])
            machine = Machine(
                brand_id=brands[m["brand"]].id,
                model=m["model"],
                exercise_id=ex.id if ex else None,
                muscle_label=m.get("muscle_label"),
                source="seed",
            )
            s.add(machine)
            machines[f"{m['brand']} {m['model']}"] = machine
        s.commit()
        for m in machines.values():
            s.refresh(m)

        for g in data["gyms"]:
            gym = Gym(name=g["name"], area=g.get("area"))
            s.add(gym)
            s.commit()
            s.refresh(gym)
            for full_name in g["machines"]:
                machine = machines.get(full_name)
                if not machine:
                    print(f"  ! unknown machine in gym {gym.name}: {full_name}")
                    continue
                s.add(GymMachine(gym_id=gym.id, machine_id=machine.id, added_by="seed"))
            s.commit()

        print(f"Seeded {len(brands)} brands, {len(exercises)} exercises, "
              f"{len(machines)} machines, {len(data['gyms'])} gyms.")


if __name__ == "__main__":
    run()
