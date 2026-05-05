import json
import os
import csv
from pathlib import Path
import pytest
from typer.testing import CliRunner

from ii_workflow.main import app

runner = CliRunner()

@pytest.fixture
def sample_validated_json(tmp_path):
    """Creates a sample validated JSON file."""
    validated_dir = tmp_path / "validated"
    validated_dir.mkdir(parents=True, exist_ok=True)
    
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-123",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 120.0,
        "total_invoice_amount_net": 100.0,
        "total_invoice_amount_tax": 20.0,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 120.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 20.0,
        "currency": "EUR",
        "iban": "AT123456789",
        "payment_method": "Bankkonto"
    }
    
    file_path = validated_dir / "invoice-validated.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
        
    return str(file_path)

@pytest.fixture
def different_validated_json(tmp_path):
    """Creates a different validated JSON file."""
    validated_dir = tmp_path / "validated"
    validated_dir.mkdir(parents=True, exist_ok=True)
    
    data = {
        "vendor_name": "Other Vendor",
        "purchase_category": "Hardware",
        "invoice_number": "INV-999",
        "date": "2026-05-05",
        "total_invoice_amount_gross": 500.0,
        "total_invoice_amount_net": 400.0,
        "total_invoice_amount_tax": 100.0,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 500.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 100.0,
        "currency": "EUR",
        "iban": None,
        "payment_method": "bar"
    }
    
    file_path = validated_dir / "invoice2-validated.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
        
    return str(file_path)

def test_record_new_csv(sample_validated_json, tmp_path, mocker):
    """Test successful creation of a new CSV file and appending the first record."""
    result_csv = tmp_path / "results.csv"
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(tmp_path / "validated"),
        "RESULT_COLUMNS": "vendor_name;invoice_number;date;total_invoice_amount_gross;payment_method"
    })
    
    # Use CWD patch for relative resolution of the CSV if needed, but here we pass absolute
    result = runner.invoke(app, ["record", sample_validated_json, "--result_csv", str(result_csv)])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    assert result_csv.exists()
    assert str(result_csv.absolute()) in result.output
    
    with open(result_csv, "r", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)
        
        assert len(rows) == 2 # Header + 1 row
        assert rows[0] == ["vendor_name", "invoice_number", "date", "total_invoice_amount_gross", "payment_method"]
        assert rows[1] == ["Test Vendor", "INV-123", "04.05.2026", "120,00", "Bankkonto"]

def test_record_existing_csv_no_duplicate(sample_validated_json, different_validated_json, tmp_path, mocker):
    """Test successful appending to an existing CSV file."""
    result_csv = tmp_path / "results.csv"
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(tmp_path / "validated"),
        "RESULT_COLUMNS": "vendor_name;invoice_number;date;total_invoice_amount_gross;payment_method"
    })
    
    # Run once
    runner.invoke(app, ["record", sample_validated_json, "--result_csv", str(result_csv)])
    
    # Run twice with different json
    result = runner.invoke(app, ["record", different_validated_json, "--result_csv", str(result_csv)])
    
    assert result.exit_code == 0
    
    with open(result_csv, "r", newline="") as f:
        reader = list(csv.reader(f, delimiter=";"))
        assert len(reader) == 3 # Header + 2 rows
        assert reader[2] == ["Other Vendor", "INV-999", "05.05.2026", "500,00", "bar"]

def test_record_existing_csv_with_duplicate(sample_validated_json, tmp_path, mocker):
    """Test attempting to append a duplicate record."""
    result_csv = tmp_path / "results.csv"
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(tmp_path / "validated"),
        "RESULT_COLUMNS": "vendor_name;invoice_number;date;total_invoice_amount_gross"
    })
    
    # First write
    runner.invoke(app, ["record", sample_validated_json, "--result_csv", str(result_csv)])
    
    # Second write with same JSON
    result = runner.invoke(app, ["record", sample_validated_json, "--result_csv", str(result_csv)])
    
    assert result.exit_code == 0 # Successful exit but duplicate
    
    with open(result_csv, "r", newline="") as f:
        reader = list(csv.reader(f, delimiter=";"))
        assert len(reader) == 2 # Header + 1 row (duplicate NOT added)

def test_record_relative_paths(sample_validated_json, tmp_path, mocker):
    """Test handling relative paths and default option."""
    validated_dir = tmp_path / "validated"
    # Change working directory for the test so relative path resolves
    cwd_patch = str(tmp_path)
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(validated_dir),
        "RESULT_COLUMNS": "vendor_name;invoice_number"
    })
    
    filename = Path(sample_validated_json).name
    
    # Run with relative filename and default CSV filename
    # Temporarily change current working directory for the runner
    old_cwd = os.getcwd()
    os.chdir(cwd_patch)
    try:
        result = runner.invoke(app, ["record", filename]) # defaults to invoices_record.csv
    finally:
        os.chdir(old_cwd)
        
    assert result.exit_code == 0, f"Output: {result.output}"
    
    default_csv = tmp_path / "invoices_record.csv"
    assert default_csv.exists()
    assert str(default_csv.absolute()) in result.output

def test_record_missing_columns_env_var(sample_validated_json, tmp_path, mocker):
    """Test error when RESULT_COLUMNS is missing."""
    result_csv = tmp_path / "results.csv"
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(tmp_path / "validated")
        # RESULT_COLUMNS is omitted
    })
    
    if "RESULT_COLUMNS" in os.environ:
        del os.environ["RESULT_COLUMNS"]
        
    result = runner.invoke(app, ["record", sample_validated_json, "--result_csv", str(result_csv)])
    
    assert result.exit_code != 0
    assert "RESULT_COLUMNS environment variable must be set" in str(result.output) or result.exit_code == 1
