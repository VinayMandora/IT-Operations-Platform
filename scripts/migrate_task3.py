"""Run SQL Server-only migration without recreating existing tables."""
import re
from pathlib import Path
from sqlalchemy import inspect
from app.db import get_engine


def main():
    engine = get_engine()
    if engine.dialect.name != 'mssql':
        raise RuntimeError('This migration requires Microsoft SQL Server')
    tables = set(inspect(engine).get_table_names())
    if not {'claims','tickets','assets','users','audit_events'}.issubset(tables):
        raise RuntimeError('Task 2 schema missing; stop and migrate Task 1/2 first')
    source = (Path(__file__).with_name('05_task3_migration.sql')).read_text(encoding='utf-8')
    batches = re.split(r'^\s*GO\s*$', source, flags=re.IGNORECASE | re.MULTILINE)
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level='AUTOCOMMIT')
        for batch in batches:
            if batch.strip():
                connection.exec_driver_sql(batch)
    print('Task 3 SQL migration applied; existing claims, tickets and assets retained.')


if __name__ == '__main__':
    main()
