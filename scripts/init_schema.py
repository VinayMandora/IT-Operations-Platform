"""Create application tables in the database created by the SSMS script."""
from app.db import get_engine
from app.models import Base


def main() -> None:
    Base.metadata.create_all(bind=get_engine())
    print(f"SQLAlchemy schema ready in ClaimsITOpsDemo: {len(Base.metadata.tables)} Task 1–5 tables available")


if __name__ == "__main__":
    main()
