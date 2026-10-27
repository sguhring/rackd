"""Database engine. Defaults to local SQLite; set DATABASE_URL for Postgres."""
import os

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./rackd.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    # `import models` so SQLModel sees the table classes before create_all.
    import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    if engine.url.get_backend_name() == "sqlite":
        with engine.begin() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("set")}
            if "setup_name" not in columns:
                connection.execute(text("ALTER TABLE set ADD COLUMN setup_name VARCHAR NOT NULL DEFAULT 'standard'"))
            if "setup_note" not in columns:
                connection.execute(text("ALTER TABLE set ADD COLUMN setup_note VARCHAR"))


def get_session():
    with Session(engine) as session:
        yield session
