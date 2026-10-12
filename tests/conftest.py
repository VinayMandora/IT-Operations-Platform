"""Isolated SQLite test database; real SQL Server verification is a separate smoke test."""
import os
os.environ.setdefault('APP_SECRET_KEY', 'TEST-ONLY-secret-key-very-long-and-never-used-on-server-123456789')

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base, User
from app.security import hash_password

ACCOUNTS = {
    'admin': ('Admin', 'NorthstarAdmin!2026'),
    'tech.owen': ('Technician', 'NorthstarTech!2026'),
    'tech.maya': ('Technician', 'NorthstarTech!2026'),
    'employee.ellie': ('Employee', 'NorthstarStaff!2026'),
    'employee.jamie': ('Employee', 'NorthstarStaff!2026'),
}


@pytest.fixture
def session_factory():
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def enable_fk(dbapi_connection, _connection_record):
        dbapi_connection.execute('PRAGMA foreign_keys=ON')

    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with maker() as db:
        for username, (role, password) in ACCOUNTS.items():
            db.add(User(username=username, full_name=username.title(),
                        email=username + '@northstar.example', role=role,
                        password_hash=hash_password(password), is_active=True))
        db.commit()
    yield maker
    engine.dispose()


@pytest.fixture
def client(session_factory):
    def override():
        with session_factory() as session:
            yield session
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def login_as(client, username='admin'):
    response = client.post('/api/auth/login', json={'username': username,
                             'password': ACCOUNTS[username][1]})
    assert response.status_code == 200, response.text
    return {'X-CSRF-Token': response.json()['csrf_token']}
