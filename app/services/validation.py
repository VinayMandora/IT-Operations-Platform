"""Read a claims spreadsheet and normalise/validate each data row."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import re

import pandas as pd

from app.config import MAX_IMPORT_ROWS

HEADERS = (
    "claim_id", "policy_number", "claimant_name", "claim_type",
    "incident_date", "reported_date", "status", "amount_gbp",
    "postcode", "description",
)
CLAIM_TYPES = {name.casefold(): name for name in ("Motor", "Home", "Travel", "Business")}
STATUSES = {name.casefold(): name for name in ("Open", "In Progress", "Closed", "Declined")}
POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}$")


class FileValidationError(ValueError):
    """The supplied file cannot be parsed or has an invalid structure."""


@dataclass(frozen=True)
class AcceptedRow:
    source_row_number: int
    values: dict


@dataclass(frozen=True)
class FailedRow:
    source_row_number: int
    claim_id: str | None
    reason: str
    raw: dict


def clean_text(value: object) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return " ".join(str(value).split())


def parse_date(value: object) -> date:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.date()
    if isinstance(value, date):
        return value
    value = clean_text(value)
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError("must be a valid YYYY-MM-DD or DD/MM/YYYY date")


def parse_amount(value: object) -> Decimal:
    raw = clean_text(value).replace("£", "").replace(",", "")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("must be a valid GBP amount") from None
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("must contain no more than 2 decimal places")
    if amount < 0 or amount > Decimal("1000000"):
        raise ValueError("must be between £0 and £1,000,000")
    return amount.quantize(Decimal("0.01"))


def load_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    extension = Path(filename).suffix.lower()
    if extension not in (".xlsx", ".csv"):
        raise FileValidationError("Only .xlsx and .csv files are supported")
    try:
        if extension == ".xlsx":
            frame = pd.read_excel(BytesIO(content), sheet_name=0, dtype=object, engine="openpyxl", keep_default_na=False)
        else:
            frame = pd.read_csv(BytesIO(content), dtype=str, encoding="utf-8-sig", keep_default_na=False)
    except Exception as exc:
        # Convert file-parser diagnostics to a safe, consistent client response.
        raise FileValidationError(f"Could not read {extension} file: {type(exc).__name__}") from exc
    if frame.empty:
        raise FileValidationError("The file contains no data rows")
    if len(frame) > MAX_IMPORT_ROWS:
        raise FileValidationError(f"A file may contain at most {MAX_IMPORT_ROWS:,} rows")
    renamed = {column: re.sub(r"\W+", "_", clean_text(column).strip().lower()).strip("_") for column in frame.columns}
    normalised = list(renamed.values())
    if len(set(normalised)) != len(normalised):
        raise FileValidationError("File has duplicate column names after normalisation")
    frame = frame.rename(columns=renamed)
    missing = sorted(set(HEADERS) - set(frame.columns))
    if missing:
        raise FileValidationError("Missing required columns: " + ", ".join(missing))
    return frame[list(HEADERS)]


def validate_rows(frame: pd.DataFrame, today: date | None = None) -> tuple[list[AcceptedRow], list[FailedRow]]:
    today = today or date.today()
    seen_ids: set[str] = set()
    accepted: list[AcceptedRow] = []
    failed: list[FailedRow] = []

    for row_number, row in enumerate(frame.to_dict(orient="records"), start=2):
        raw = {key: clean_text(value)[:500] for key, value in row.items()}
        errors: list[str] = []
        claim_id = clean_text(row["claim_id"]).upper()
        if not re.fullmatch(r"NCL-\d{6}", claim_id):
            errors.append("claim_id must have format NCL-000001")
        elif claim_id in seen_ids:
            errors.append("duplicate claim_id within file")
        else:
            seen_ids.add(claim_id)

        policy = clean_text(row["policy_number"]).upper()
        if not re.fullmatch(r"POL-\d{6}", policy):
            errors.append("policy_number must have format POL-000001")

        claimant = clean_text(row["claimant_name"]).title()
        if not 1 <= len(claimant) <= 100:
            errors.append("claimant_name must be 1 to 100 characters")

        claim_type_text = clean_text(row["claim_type"])
        claim_type = CLAIM_TYPES.get(claim_type_text.casefold())
        if claim_type is None:
            errors.append("claim_type must be Motor, Home, Travel or Business")

        status_text = clean_text(row["status"])
        status = STATUSES.get(status_text.casefold())
        if status is None:
            errors.append("status must be Open, In Progress, Closed or Declined")

        incident = reported = None
        try:
            incident = parse_date(row["incident_date"])
            if not date(2000, 1, 1) <= incident <= today:
                errors.append("incident_date must be between 2000-01-01 and today")
        except ValueError as exc:
            errors.append("incident_date " + str(exc))
        try:
            reported = parse_date(row["reported_date"])
            if not date(2000, 1, 1) <= reported <= today:
                errors.append("reported_date must be between 2000-01-01 and today")
        except ValueError as exc:
            errors.append("reported_date " + str(exc))
        if incident is not None and reported is not None and incident > reported:
            errors.append("incident_date cannot be after reported_date")

        amount = None
        try:
            amount = parse_amount(row["amount_gbp"])
        except ValueError as exc:
            errors.append("amount_gbp " + str(exc))

        postcode_compact = re.sub(r"\s+", "", clean_text(row["postcode"])).upper()
        postcode = postcode_compact[:-3] + " " + postcode_compact[-3:] if len(postcode_compact) > 3 else postcode_compact
        if not POSTCODE_RE.fullmatch(postcode):
            errors.append("postcode is not a valid UK postcode format")

        description = clean_text(row["description"])
        if len(description) > 500:
            errors.append("description cannot exceed 500 characters")

        if errors:
            failed.append(FailedRow(row_number, claim_id or None, "; ".join(errors), raw))
        else:
            accepted.append(AcceptedRow(row_number, {
                "claim_id": claim_id, "policy_number": policy,
                "claimant_name": claimant, "claim_type": claim_type,
                "incident_date": incident, "reported_date": reported,
                "status": status, "amount_gbp": amount,
                "postcode": postcode, "description": description,
            }))
    return accepted, failed
