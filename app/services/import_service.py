"""Atomic, SHA-256-idempotent claims import with per-row rejection records."""
import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditEvent, Claim, ImportBatch, RejectedRow
from app.services.validation import FailedRow, load_dataframe, validate_rows


class ImportConflictError(RuntimeError):
    """Another transaction inserted a conflicting ID concurrently."""


def batch_to_dict(batch: ImportBatch, replayed: bool = False) -> dict:
    return {
        "batch_id": batch.id,
        "filename": batch.filename,
        "sha256": batch.file_sha256,
        "status": batch.status,
        "total_rows": batch.total_rows,
        "imported_rows": batch.imported_rows,
        "rejected_rows": batch.rejected_rows,
        "replayed": replayed,
        "created_at_utc": batch.created_at.isoformat() + "Z",
    }


def import_claims(session: Session, filename: str, content: bytes) -> dict:
    """Validate outside the transaction, then commit claims/rejections/audit together."""
    # Filename is for display only, never used as a filesystem destination.
    safe_filename = Path(filename.replace("\\", "/")).name[:255]
    frame = load_dataframe(safe_filename, content)
    accepted, failed = validate_rows(frame)
    sha256 = hashlib.sha256(content).hexdigest()

    try:
        with session.begin():
            previous = session.scalar(select(ImportBatch).where(ImportBatch.file_sha256 == sha256))
            if previous is not None:
                return batch_to_dict(previous, replayed=True)

            input_ids = [row.values["claim_id"] for row in accepted]
            existing_ids: set[str] = set()
            # SQL Server has a 2,100-parameter limit; keep IN lists well below it.
            for start in range(0, len(input_ids), 500):
                chunk = input_ids[start:start + 500]
                existing_ids.update(session.scalars(select(Claim.claim_id).where(Claim.claim_id.in_(chunk))))

            new_rows = [row for row in accepted if row.values["claim_id"] not in existing_ids]
            for row in accepted:
                if row.values["claim_id"] in existing_ids:
                    failed.append(FailedRow(
                        row.source_row_number,
                        row.values["claim_id"],
                        "claim_id already exists in database",
                        {k: str(v) for k, v in row.values.items()},
                    ))

            batch = ImportBatch(
                filename=safe_filename,
                file_sha256=sha256,
                status="Completed",
                total_rows=len(frame),
                imported_rows=len(new_rows),
                rejected_rows=len(failed),
            )
            session.add(batch)
            session.flush()  # Get batch.id while retaining one atomic transaction.

            session.add_all(Claim(**row.values, import_batch_id=batch.id) for row in new_rows)
            session.add_all(
                RejectedRow(
                    import_batch_id=batch.id,
                    source_row_number=row.source_row_number,
                    claim_id=row.claim_id,
                    failure_reason=row.reason,
                    raw_data_json=json.dumps(row.raw, ensure_ascii=False, default=str),
                )
                for row in sorted(failed, key=lambda item: item.source_row_number)
            )
            session.add(AuditEvent(
                event_type="IMPORT_COMPLETED",
                import_batch_id=batch.id,
                details_json=json.dumps({
                    "filename": safe_filename,
                    "total_rows": len(frame),
                    "imported_rows": len(new_rows),
                    "rejected_rows": len(failed),
                }),
            ))
        return batch_to_dict(batch)
    except IntegrityError as exc:
        session.rollback()
        # A concurrent same-file upload could have won the unique SHA-256 race.
        previous = session.scalar(select(ImportBatch).where(ImportBatch.file_sha256 == sha256))
        if previous is not None:
            return batch_to_dict(previous, replayed=True)
        raise ImportConflictError("A concurrent import conflicted with existing claim IDs; retry upload") from exc
