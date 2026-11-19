"""Conexões PostgreSQL compartilhadas com pool limitado."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

Session = None


def init_database(url):
    global Session
    engine = create_engine(url, pool_size=3, max_overflow=2, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)"))


def get_setting(name):
    from app.db import Session
    with Session() as session:
        row = session.execute(text("SELECT value FROM settings WHERE name=:n"), {"n": name}).first()
        return row[0] if row else None


def put_setting(name, value):
    from app.db import Session
    with Session.begin() as session:
        session.execute(text("INSERT INTO settings(name,value) VALUES (:n,:v) ON CONFLICT(name) DO UPDATE SET value=EXCLUDED.value"), {"n":name,"v":value})
