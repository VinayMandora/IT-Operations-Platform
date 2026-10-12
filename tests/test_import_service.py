"""Database atomicity, duplicates, idempotence, and audit coverage."""
import json

from sqlalchemy import func, select

from app.models import AuditEvent, Claim, ImportBatch, RejectedRow
from app.services.import_service import import_claims
from scripts.generate_sample_data import generate_rows


def one_csv(row, *, reverse=False):
    import csv
    from io import StringIO
    from app.services.validation import HEADERS
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def test_repeated_identical_upload_creates_one_batch(session_factory):
    data = one_csv(generate_rows()[0])
    with session_factory() as session:
        first = import_claims(session, "input.csv", data)
    with session_factory() as session:
        second = import_claims(session, "input.csv", data)
        assert first["imported_rows"] == 1
        assert second["replayed"] is True
        assert second["batch_id"] == first["batch_id"]
        assert session.scalar(select(func.count()).select_from(Claim)) == 1
        assert session.scalar(select(func.count()).select_from(ImportBatch)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_different_file_same_claim_id_rejected(session_factory):
    row = generate_rows()[0]
    data_one = one_csv(row)
    edited = row.copy()
    edited["description"] = "same ID, different file hash"
    data_two = one_csv(edited)
    with session_factory() as session:
        import_claims(session, "first.csv", data_one)
    with session_factory() as session:
        result = import_claims(session, "second.csv", data_two)
        assert result["imported_rows"] == 0
        assert result["rejected_rows"] == 1
        assert session.scalar(select(func.count()).select_from(Claim)) == 1
        rejected = session.scalar(select(RejectedRow))
        assert "already exists" in rejected.failure_reason
        assert json.loads(rejected.raw_data_json)["claim_id"] == "NCL-000001"


def test_real_xlsx_has_900_accepted_and_100_rejected(session_factory):
    from pathlib import Path
    data = (Path(__file__).resolve().parents[1] / "sample_data" / "northstar_claims_1000.xlsx").read_bytes()
    with session_factory() as session:
        result = import_claims(session, "northstar_claims_1000.xlsx", data)
        assert result["total_rows"] == 1000
        assert result["imported_rows"] == 900
        assert result["rejected_rows"] == 100
        assert session.scalar(select(func.count()).select_from(Claim)) == 900
        assert session.scalar(select(func.count()).select_from(RejectedRow)) == 100
