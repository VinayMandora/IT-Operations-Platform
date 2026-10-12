"""Create only a second fictional admin for two-person offboarding approval."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_engine
from app.models import User
from app.security import hash_password


def seed(db):
    if db.scalar(select(User).where(User.username == 'admin.reviewer')):
        return False
    db.add(User(username='admin.reviewer', full_name='Jordan Review',
                email='admin.reviewer@northstar.example', role='Admin', is_active=True,
                password_hash=hash_password('NorthstarReview!2026')))
    db.commit()
    return True


def main():
    with Session(get_engine()) as db:
        print('Created reviewer' if seed(db) else 'Reviewer already exists; no changes')
    print('LOCAL TEST ACCOUNT: admin.reviewer / NorthstarReview!2026')


if __name__ == '__main__':
    main()
