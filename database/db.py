from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings


connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=connect_args,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def habilitar_chaves_estrangeiras(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
            if settings.sqlite_wal:
                cursor.execute("PRAGMA journal_mode=WAL")
                if cursor.fetchone()[0].lower() != "wal":
                    raise RuntimeError("SQLite nao conseguiu ativar WAL")
        finally:
            cursor.close()

SessionLocal = sessionmaker(autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()