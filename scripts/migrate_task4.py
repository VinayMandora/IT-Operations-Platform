"""Safe SQL Server migration using existing Task 1 connection."""
import re
from pathlib import Path
from sqlalchemy import inspect
from app.db import get_engine


def main():
    engine = get_engine()
    if engine.dialect.name != 'mssql':
        raise RuntimeError('Task 4 migration requires Microsoft SQL Server')
    tables = set(inspect(engine).get_table_names())
    if not {'claims','audit_events','tickets','users','employees'}.issubset(tables):
        raise RuntimeError('Tasks 1–3 tables are missing; apply earlier migrations first')
    script = (Path(__file__).with_name('07_task4_migration.sql')).read_text(encoding='utf-8')
    batches = re.split(r'^\s*GO\s*$', script, flags=re.IGNORECASE | re.MULTILINE)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level='AUTOCOMMIT')
        for batch in batches:
            if batch.strip():
                conn.exec_driver_sql(batch)
    print('Task 4 migration complete; existing data preserved.')


if __name__ == '__main__':
    main()
