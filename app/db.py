"""SQL Server engine and a request-scoped SQLAlchemy session."""
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.config import (
    DB_ENCRYPT,
    DB_NAME,
    DB_ODBC_DRIVER,
    DB_SERVER,
    DB_TRUST_SERVER_CERTIFICATE,
)

# URL.create safely encodes the ODBC connection string, including the backslash.
odbc_string = (
    f"DRIVER={{{DB_ODBC_DRIVER}}};"
    f"SERVER={DB_SERVER};DATABASE={DB_NAME};"
    "Trusted_Connection=yes;"
    f"Encrypt={DB_ENCRYPT};"
    f"TrustServerCertificate={DB_TRUST_SERVER_CERTIFICATE};"
)
@lru_cache(maxsize=1)
def get_engine():
    # Lazy construction keeps SQLite-based unit tests independent of pyodbc.
    return create_engine(
        URL.create("mssql+pyodbc", query={"odbc_connect": odbc_string}),
        pool_pre_ping=True,
    )


def get_db() -> Generator[Session, None, None]:
    """Provide a new session. Import service owns its transaction boundary."""
    with Session(get_engine()) as session:
        yield session
