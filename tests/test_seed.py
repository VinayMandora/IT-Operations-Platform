"""Demonstration seed is repeatable and never deletes claims or IT records."""
from sqlalchemy import func, select
from app.models import Asset, Ticket, User
from scripts import seed_task2


def test_idempotent_task2_seed(monkeypatch, session_factory):
    db_engine = session_factory.kw['bind']
    monkeypatch.setattr(seed_task2, 'get_engine', lambda: db_engine)
    seed_task2.main()
    seed_task2.main()
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 5
        assert db.scalar(select(func.count()).select_from(Asset)) == 6
        assert db.scalar(select(func.count()).select_from(Ticket)) == 4
