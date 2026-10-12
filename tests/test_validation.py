"""Parsing, normalisation and row-rejection tests."""
from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from app.services.validation import FileValidationError, load_dataframe, validate_rows
from scripts.generate_sample_data import generate_rows


def test_thousand_rows_have_expected_rejection_breakdown():
    accepted, failed = validate_rows(pd.DataFrame(generate_rows()))
    assert len(accepted) == 900
    assert len(failed) == 100
    assert "duplicate" in failed[0].reason
    assert accepted[6].values["claimant_name"] == "Test Claimant 0007"


def test_invalid_date_and_negative_amount_rejected():
    row = generate_rows()[0]
    row["reported_date"] = "31/02/2025"
    row["amount_gbp"] = "-4.00"
    accepted, failed = validate_rows(pd.DataFrame([row]))
    assert not accepted
    assert "reported_date" in failed[0].reason
    assert "amount_gbp" in failed[0].reason


def test_future_date_is_rejected():
    row = generate_rows()[0]
    row["incident_date"] = date(2099, 1, 1)
    accepted, failed = validate_rows(pd.DataFrame([row]), today=date(2026, 10, 12))
    assert not accepted
    assert "today" in failed[0].reason


def test_csv_has_normalised_headers_and_clean_values():
    frame = pd.DataFrame([generate_rows()[0]])
    frame.columns = [name.replace("_", " ").upper() for name in frame.columns]
    loaded = load_dataframe("demo.csv", frame.to_csv(index=False).encode("utf-8"))
    accepted, failed = validate_rows(loaded)
    assert len(accepted) == 1
    assert len(failed) == 0


def test_missing_columns_raise_error():
    with pytest.raises(FileValidationError, match="Missing required columns"):
        load_dataframe("demo.csv", b"claim_id\nNCL-000001\n")


def test_wrong_extension_rejected():
    with pytest.raises(FileValidationError, match="Only"):
        load_dataframe("claims.txt", b"hello")
