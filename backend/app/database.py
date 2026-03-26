import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://pharmacy:pharmacy_pass@localhost:5432/pharmacy_db"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLAlchemy 2.0+: DeclarativeBase вместо deprecated declarative_base()
class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency — сессия БД для FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
