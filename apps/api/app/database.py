from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings
import os

import os
import re
import subprocess
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

DATABASE_URL = os.getenv("DATABASE_URL") or settings.database_url

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured")

# SQLAlchemy 2.x with psycopg 3: normalize to 'postgresql+psycopg://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

def _create_engine_with_fallback(url: str):
    eng = create_engine(url, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except OperationalError:
        # If localhost has a host-level port conflict on Windows, fallback to Docker WSL IP
        if "localhost" in url or "127.0.0.1" in url:
            try:
                res = subprocess.run(
                    ["wsl", "-d", "docker-desktop", "-u", "root", "/bin/sh", "-c", "ip addr show eth0"],
                    capture_output=True,
                    text=True,
                    timeout=8
                )
                match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", res.stdout)
                if match:
                    fallback_ip = match.group(1)
                    fallback_url = url.replace("localhost", fallback_ip).replace("127.0.0.1", fallback_ip)
                    fallback_eng = create_engine(fallback_url, pool_pre_ping=True)
                    with fallback_eng.connect() as conn:
                        conn.execute(text("SELECT 1"))
                    return fallback_eng
            except Exception:
                pass
        return eng

engine = _create_engine_with_fallback(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
