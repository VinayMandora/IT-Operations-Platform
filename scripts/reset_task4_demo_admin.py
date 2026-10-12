"""One-time LOCAL Northstar training Admin password recovery.

Place at scripts/reset_task4_demo_admin.py and run from project root:
    python -m scripts.reset_task4_demo_admin

Requires access to the existing ClaimsITOpsDemo SQL Server database using the
current Windows account. Does not create users or change any account status.
"""

from __future__ import annotations

import json
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DB_NAME
from app.db import get_engine
from app.models import AuditEvent, User
from app.security import hash_password


def main() -> None:
    if DB_NAME != "ClaimsITOpsDemo":
        raise SystemExit("Refusing to run: DB_NAME must be ClaimsITOpsDemo.")

    print("LOCAL DEMO ONLY: recover the existing 'admin' password.")
    print("This will update one password hash and append one audit event.")
    if input("To proceed, type RESET admin: ").strip() != "RESET admin":
        raise SystemExit("Cancelled: database unchanged.")

    with Session(get_engine()) as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        if admin is None:
            raise SystemExit(
                "Admin account missing. Run python -m scripts.seed_task2 first.")
        if admin.role != "Admin" or not admin.is_active:
            raise SystemExit(
                "Existing 'admin' is not an active Admin. No change made. "
                "Inspect dbo.users and restore access through an authorised administrator."
            )

        new_password = getpass(
            "Enter a NEW demo Admin password (12-128 characters): ")
        if not 12 <= len(new_password) <= 128:
            raise SystemExit(
                "Password length must be 12-128 characters. Database unchanged.")
        if new_password != getpass("Confirm the new password: "):
            raise SystemExit("Passwords do not match. Database unchanged.")

        admin.password_hash = hash_password(new_password)
        db.add(AuditEvent(
            event_type="USER_UPDATED",
            actor_user_id=None,  # local maintenance, NOT an authenticated app user
            details_json=json.dumps({
                "action": "LOCAL_ADMIN_PASSWORD_RECOVERY",
                "username": "admin",
                "source": "local_windows_integrated_sql_connection",
                "password_recorded": False,
            }),
        ))
        db.commit()

    print("Admin password updated successfully; audit event recorded.")
    print("Run .\\scripts\\demo_task4.ps1 using the NEW password.")
    print("Delete scripts/reset_task4_demo_admin.py after local recovery.")


if __name__ == "__main__":
    main()
