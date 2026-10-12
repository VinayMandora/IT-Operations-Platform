"""Apply idempotent migration batches to an existing SQL Server database."""
import re
from pathlib import Path
from sqlalchemy import inspect
from app.db import get_engine


def main():
    engine = get_engine()
    if engine.dialect.name != 'mssql':
        raise RuntimeError('Task 2 migration must run on Microsoft SQL Server')
    inspector = inspect(engine)
    if not {'claims', 'import_batches', 'audit_events'}.issubset(set(inspector.get_table_names())):
        raise RuntimeError('Task 1 schema missing: run scripts/01_create_database.sql and python -m scripts.init_schema first')
    text = (Path(__file__).parent / '03_task2_migration.sql').read_text(encoding='utf-8')
    batches = re.split(r'^\s*GO\s*$', text, flags=re.MULTILINE | re.IGNORECASE)
    with engine.connect() as conn:
        # Migration script owns its T-SQL transaction, not SQLAlchemy's default implicit transaction.
        conn = conn.execution_options(isolation_level='AUTOCOMMIT')
        for batch in batches:
            if batch.strip():
                conn.exec_driver_sql(batch)
    print('Task 2 SQL Server migration applied. Existing Task 1 data retained.')


if __name__ == '__main__':
    main()
