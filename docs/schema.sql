-- rackd schema (Postgres)
-- Core idea: a gym is a SUBSET of the global machine catalog, joined via gym_machines.
-- Progression is tracked per gym_machine (a specific machine instance), never across models.

-- ── global catalog ────────────────────────────────────────────────────────────

CREATE TABLE brands (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,          -- 'Hammer Strength', 'Technogym'
    abbr        TEXT,                          -- 'HS', 'TG' (badge)
    color       TEXT                           -- brand badge hex
);

-- the movement layer (seeded from ExerciseDB / free-exercise-db)
CREATE TABLE exercises (
    id          SERIAL PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,          -- 'chest-press'
    name        TEXT NOT NULL,                 -- 'Chest Press'
    muscle_group TEXT,                         -- 'push' | 'pull' | 'legs' | ...
    primary_muscles TEXT[],
    equipment_category TEXT                    -- 'leverage machine', 'cable', 'barbell'
);

-- a specific branded machine MODEL in the global catalog
CREATE TABLE machines (
    id          SERIAL PRIMARY KEY,
    brand_id    INTEGER NOT NULL REFERENCES brands(id),
    model       TEXT NOT NULL,                 -- 'Iso-Lateral Chest Press'
    exercise_id INTEGER REFERENCES exercises(id),
    muscle_label TEXT,                         -- 'chest · front delts' (display)
    image_url   TEXT,
    source      TEXT,                          -- where this row was scraped from
    UNIQUE (brand_id, model)
);

-- ── gyms ──────────────────────────────────────────────────────────────────────

CREATE TABLE gyms (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    area        TEXT,                          -- 'Benfica · Lisboa'
    lat         DOUBLE PRECISION,
    lng         DOUBLE PRECISION
);

-- the subset: which catalog machines this gym actually has on its floor
CREATE TABLE gym_machines (
    id          SERIAL PRIMARY KEY,
    gym_id      INTEGER NOT NULL REFERENCES gyms(id) ON DELETE CASCADE,
    machine_id  INTEGER NOT NULL REFERENCES machines(id),
    added_by    TEXT,                          -- user id who mapped it (crowdsourcing)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (gym_id, machine_id)
);

-- ── workouts & logging ────────────────────────────────────────────────────────

CREATE TABLE workouts (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT,                          -- 'push day' (custom) or null (free session)
    gym_id      INTEGER REFERENCES gyms(id),   -- null for gym-agnostic custom workouts
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE sets (
    id            BIGSERIAL PRIMARY KEY,
    workout_id    INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    -- exactly one of these identifies what was trained:
    gym_machine_id INTEGER REFERENCES gym_machines(id),  -- a specific machine instance
    exercise_id    INTEGER REFERENCES exercises(id),     -- generic / free-weight move
    weight_kg     NUMERIC(6,2) NOT NULL,
    reps          INTEGER NOT NULL,
    is_pr         BOOLEAN NOT NULL DEFAULT FALSE,
    logged_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- "last time on THIS machine" and PR detection both read from here:
CREATE INDEX idx_sets_user_machine ON sets (user_id, gym_machine_id, logged_at DESC);
CREATE INDEX idx_sets_user_exercise ON sets (user_id, exercise_id, logged_at DESC);
CREATE INDEX idx_gym_machines_gym ON gym_machines (gym_id);
