"""Run incremental Task 5 SQL Server migration, never drop or recreate prior tables."""
import re
from pathlib import Path
from sqlalchemy import inspect
from app.db import get_engine


def main():
    engine = get_engine()
    if engine.dialect.name != 'mssql':
        raise RuntimeError('Task 5 migration requires Microsoft SQL Server')
    tables = set(inspect(engine).get_table_names())
    if not {'claims','tickets','users','assets','audit_events','claim_crm_states'}.issubset(tables):
        raise RuntimeError('Apply Tasks 1–4 before Task 5; no data has been modified')
    sql = Path(__file__).with_name('09_task5_migration.sql').read_text(encoding='utf-8')
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level='AUTOCOMMIT')
        for batch in re.split(r'^\s*GO\s*$', sql, flags=re.I|re.M):
            if batch.strip():
                connection.exec_driver_sql(batch)
    print('Task 5 migration complete; Tasks 1–4 preserved.')


if __name__ == '__main__':
    main()
