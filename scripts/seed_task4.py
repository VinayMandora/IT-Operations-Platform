"""Idempotent workflow + communication template seed; never overwrites edits."""
from sqlalchemy.orm import Session
from app.db import get_engine
from app.services.claims_workflow import seed_rules
from app.services.claim_templates import seed_templates


def seed(db):
    seed_rules(db)
    seed_templates(db)


def main():
    with Session(get_engine()) as db:
        seed(db)
    print('Task 4: four workflow rules and four editable templates available (idempotent).')


if __name__ == '__main__':
    main()
