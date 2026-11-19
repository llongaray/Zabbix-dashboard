"""Conexões PostgreSQL com URL estruturada e pool limitado."""
import os

from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import sessionmaker

Session = None


def build_database_url():
    """Preserva caracteres especiais da senha sem interpolação em URL."""
    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=5432,
        database=os.environ["POSTGRES_DB"],
    )


def init_database():
    global Session
    engine = create_engine(
        build_database_url(),
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,
    )
    Session = sessionmaker(bind=engine)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS settings "
            "(name TEXT PRIMARY KEY, value TEXT NOT NULL)"
        ))


def get_setting(name):
    with Session() as session:
        row = session.execute(
            text("SELECT value FROM settings WHERE name=:n"), {"n": name}
        ).first()
        return row[0] if row else None


def put_setting(name, value):
    with Session.begin() as session:
        session.execute(
            text("INSERT INTO settings(name,value) VALUES (:n,:v) "
                 "ON CONFLICT(name) DO UPDATE SET value=EXCLUDED.value"),
            {"n": name, "v": value},
        )
