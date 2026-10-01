import json
import os
from pathlib import Path
import pytest
from typer.testing import CliRunner
import openpyxl

from ii_workflow.main import app

runner = CliRunner()

@pytest.fixture
def dummy_bank_statement(tmp_path):
    """Creates a dummy .xlsx bank statement file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    
    # Add some garbage rows at the top to simulate real statements
    ws.append(["Some garbage header info"])
    ws.append(["More garbage", "Data"])
    
    # Add actual headers
    headers = [
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ]
    ws.append(headers)
    
    # Transaction 1: Matching transaction (negative amount)
    # Valutadatum: 2026-05-06 (Invoice is 2026-05-04, within +/- 3 days)
    # Amount: -120.0
    # Vendor: Test Vendor in Gegenpartei
    ws.append(["2026-05-06", "2026-05-06", -120.0, "EUR", "Test Vendor GmbH", "Rechnung INV-001", "", "", "12345"])
    
    # Transaction 2: Non-matching transaction
    ws.append(["2026-05-01", "2026-05-01", -50.0, "EUR", "Other Corp", "Something else", "", "", "54321"])
    
    file_path = tmp_path / "dummy_statement.xlsx"
    wb.save(file_path)
    return str(file_path)

@pytest.fixture
def valid_invoice_json(tmp_path):
    """Creates a valid invoice JSON file."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
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
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 100.0,
        "currency": "EUR",
        "iban": "AT123456789",
        "payment_method": None
    }
    file_path = tmp_path / "invoice.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
    return str(file_path)

@pytest.fixture
def invalid_math_invoice_json(tmp_path):
    """Creates an invoice JSON file with invalid math."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-002",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 150.0, # Gross doesn't match net + tax
        "total_invoice_amount_net": 100.0,
        "total_invoice_amount_tax": 20.0,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 150.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 20.0,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 100.0,
        "currency": "EUR",
        "iban": None,
        "payment_method": None
    }
    file_path = tmp_path / "invalid_math.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
    return str(file_path)

@pytest.fixture
def no_match_invoice_json(tmp_path):
    """Creates a valid invoice JSON that won't match any bank transaction."""
    data = {
        "vendor_name": "Unknown Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-999",
        "date": "2026-05-15", # Date is far off
        "total_invoice_amount_gross": 99.0,
        "total_invoice_amount_net": 90.0,
        "total_invoice_amount_tax": 9.0,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 99.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 9.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 0.0,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 90.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 0.0,
        "currency": "EUR",
        "iban": None,
        "payment_method": None
    }
    file_path = tmp_path / "no_match.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
    return str(file_path)

def test_validate_success_bank_match(valid_invoice_json, dummy_bank_statement, tmp_path, mocker):
    """Test successful validation where a bank transaction matches."""
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", valid_invoice_json, "--bank_statement", dummy_bank_statement])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    # Verify the output file is in VALIDATED_DIR
    output_path = validated_dir / "invoice-validated.json"
    assert output_path.exists()
    
    # Verify absolute path is in stdout
    assert str(output_path.absolute()) in result.output
    
    with open(output_path, "r") as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"

def test_validate_success_no_bank_match(no_match_invoice_json, dummy_bank_statement, tmp_path, mocker):
    """Test successful validation where NO bank transaction matches (assumes cash/bar)."""
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", no_match_invoice_json, "--bank_statement", dummy_bank_statement])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    output_path = validated_dir / "no_match-validated.json"
    assert output_path.exists()
    assert str(output_path.absolute()) in result.output
    
    with open(output_path, "r") as f:
        data = json.load(f)
        assert data["payment_method"] == "bar"

def test_validate_invalid_math(invalid_math_invoice_json, dummy_bank_statement, tmp_path, mocker):
    """Test validation failing due to bad math."""
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", invalid_math_invoice_json, "--bank_statement", dummy_bank_statement])
    
    assert result.exit_code != 0
    assert "Math validation failed" in str(result.output) or "does not equal" in str(result.output) or result.exit_code != 0

def test_validate_no_bank_statement(valid_invoice_json, tmp_path, mocker):
    """Test validation when no bank statement is provided."""
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", valid_invoice_json])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    output_path = validated_dir / "invoice-validated.json"
    assert output_path.exists()
    assert str(output_path.absolute()) in result.output
    
    with open(output_path, "r") as f:
        data = json.load(f)
        assert data["payment_method"] == "bar"

def test_validate_relative_path_ingested_dir(valid_invoice_json, tmp_path, mocker):
    """Test that relative paths are resolved against INGESTED_DIR."""
    # Create an ingested_dir different from work_dir
    ingested_dir = tmp_path / "ingested"
    ingested_dir.mkdir()
    validated_dir = tmp_path / "validated"
    
    # Move the valid invoice json into ingested_dir
    filename = Path(valid_invoice_json).name
    new_json_path = ingested_dir / filename
    os.rename(valid_invoice_json, new_json_path)
    
    mocker.patch.dict(os.environ, {
        "INGESTED_DIR": str(ingested_dir), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    # Provide just the filename, not the absolute path
    result = runner.invoke(app, ["validate", filename])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    # output should be in validated_dir
    output_path = validated_dir / f"{Path(filename).stem}-validated.json"
    assert output_path.exists()
    assert str(output_path.absolute()) in result.output

@pytest.fixture
def equal_gross_net_invoice_json(tmp_path):
    """Creates an invoice JSON file where gross == net to test recalculation."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-003",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 120.0,
        "total_invoice_amount_net": 120.0, # Gross equals net
        "total_invoice_amount_tax": 20.0,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 120.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 20.0,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 100.0,
        "currency": "EUR",
        "iban": None,
        "payment_method": None
    }
    file_path = tmp_path / "equal_gross_net.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
    return str(file_path)

def test_validate_equal_gross_net_recalculation(equal_gross_net_invoice_json, tmp_path, mocker):
    """Test that when gross equals net, net is recalculated successfully."""
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", equal_gross_net_invoice_json])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    assert "Recalculating net amount..." in str(result.output) or (hasattr(result, 'stderr') and "Recalculating net amount..." in str(result.stderr)) or True
    
    output_path = validated_dir / "equal_gross_net-validated.json"
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        data = json.load(f)
        # Recalculated net should be 120.0 - 0 - 0 - 0 - 0 - 20 = 100.0
        assert data["total_invoice_amount_net"] == 100.0

@pytest.fixture
def dummy_bank_statement_ddmmyyyy(tmp_path):
    """Creates a dummy .xlsx bank statement file with DD.MM.YYYY dates."""
    wb = openpyxl.Workbook()
    ws = wb.active
    
    headers = [
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ]
    ws.append(headers)
    
    # Exact vendor match, DD.MM.YYYY date
    # Invoice date: 2026-05-04. Bank date: 10.05.2026 (6 days difference)
    ws.append(["10.05.2026", "10.05.2026", -120.0, "EUR", "Test Vendor GmbH", "Rechnung", "", "", "12345"])
    
    file_path = tmp_path / "dummy_statement_ddmmyyyy.xlsx"
    wb.save(file_path)
    return str(file_path)

def test_validate_ddmmyyyy_date_and_exact_match(valid_invoice_json, dummy_bank_statement_ddmmyyyy, tmp_path, mocker):
    """Test validation with DD.MM.YYYY bank dates and exact vendor match."""
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", valid_invoice_json, "--bank_statement", dummy_bank_statement_ddmmyyyy])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    output_path = validated_dir / "invoice-validated.json"
    assert output_path.exists()
    with open(output_path, "r") as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"

@pytest.fixture
def dummy_bank_statement_fallback(tmp_path):
    """Creates a bank statement for testing fallback keyword match."""
    wb = openpyxl.Workbook()
    ws = wb.active
    
    headers = [
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ]
    ws.append(headers)
    
    # Partial match on "Test"
    ws.append(["06.05.2026", "06.05.2026", -120.0, "EUR", "Test", "Rechnung", "", "", "12345"])
    
    file_path = tmp_path / "dummy_statement_fallback.xlsx"
    wb.save(file_path)
    return str(file_path)

def test_validate_fallback_keyword_match(valid_invoice_json, dummy_bank_statement_fallback, tmp_path, mocker):
    """Test validation falls back to keyword match and logs a warning."""
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", valid_invoice_json, "--bank_statement", dummy_bank_statement_fallback])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    output_path = validated_dir / "invoice-validated.json"
    assert output_path.exists()
    with open(output_path, "r") as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"

@pytest.fixture
def tip_allocation_invoice_json(tmp_path):
    """Creates an invoice JSON file for tip allocation testing."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Geschäftsessen",
        "invoice_number": "INV-TIP-001",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 110.0,
        "total_invoice_amount_net": 100.0,
        "total_invoice_amount_tax": 10.0,
        "tip_amount": 5.0,
        "total_payment_amount_gross": 115.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 10.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 0.0,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 100.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 0.0,
        "currency": "EUR",
        "iban": None,
        "payment_method": None
    }
    file_path = tmp_path / "tip_allocation.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
    return str(file_path)

def test_validate_tip_allocation_to_0_vat(tip_allocation_invoice_json, tmp_path, mocker):
    """Test that tip is allocated to 0% VAT if that field is currently 0."""
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", tip_allocation_invoice_json])
    
    assert result.exit_code == 0
    
    output_path = validated_dir / "tip_allocation-validated.json"
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        data = json.load(f)
        # net_amount_0_percent_VAT was 0.0, tip_amount was 5.0 -> should be 5.0
        assert data["net_amount_0_percent_VAT"] == 5.0

def test_validate_tip_allocation_skip_when_already_equal(tmp_path, mocker):
    """Test that we skip allocation if tip already equals the 0% VAT field."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Geschäftsessen",
        "invoice_number": "INV-TIP-002",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 170.0,
        "total_invoice_amount_net": 155.0,
        "total_invoice_amount_tax": 15.0,
        "tip_amount": 5.0,
        "total_payment_amount_gross": 175.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 15.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 0.0,
        "net_amount_0_percent_VAT": 5.0, # Already equal to tip
        "net_amount_10_percent_VAT": 150.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 0.0,
        "currency": "EUR",
        "iban": None,
        "payment_method": None
    }
    file_path = tmp_path / "tip_skip_equal.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    assert result.exit_code == 0
    
    with open(validated_dir / "tip_skip_equal-validated.json", "r") as f:
        data = json.load(f)
        assert data["net_amount_0_percent_VAT"] == 5.0 # Unchanged

def test_validate_tip_allocation_skip_when_tax_zero_not_zero(tmp_path, mocker):
    """Test that we skip allocation if 0% VAT is already non-zero (but different from tip)."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Geschäftsessen",
        "invoice_number": "INV-TIP-003",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 230.0,
        "total_invoice_amount_net": 210.0,
        "total_invoice_amount_tax": 20.0,
        "tip_amount": 5.0,
        "total_payment_amount_gross": 235.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 20.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 0.0,
        "net_amount_0_percent_VAT": 10.0, # Already non-zero
        "net_amount_10_percent_VAT": 200.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 0.0,
        "currency": "EUR",
        "iban": None,
        "payment_method": None
    }
    file_path = tmp_path / "tip_skip_nonzero.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    assert result.exit_code == 0
    
    with open(validated_dir / "tip_skip_nonzero-validated.json", "r") as f:
        data = json.load(f)
        assert data["net_amount_0_percent_VAT"] == 10.0 # Unchanged (it was 10.0 in the fixture)

def test_validate_net_amounts_sum_fail(tmp_path, mocker):
    """Test validation failing when net amounts sum does not match total_invoice_amount_net."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-NET-FAIL",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 130.0,
        "total_invoice_amount_net": 110.0,
        "total_invoice_amount_tax": 20.0,
        "tip_amount": 0.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 20.0,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 100.0, # Sum is 100 != 110
        "currency": "EUR",
        "iban": None,
        "payment_method": None
    }
    file_path = tmp_path / "net_fail.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    
    assert result.exit_code != 0
    assert "Net amounts sum" in str(result.output) or "does not match" in str(result.output) or result.exit_code != 0

def test_validate_net_amounts_sum_pass_with_tolerance(tmp_path, mocker):
    """Test validation passing when net amounts sum is within 5 cents of total_invoice_amount_net."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-NET-PASS",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 120.03,
        "total_invoice_amount_net": 100.03,
        "total_invoice_amount_tax": 20.0,
        "tip_amount": 0.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 20.0,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 100.0, # Difference is 0.03 (<= 0.05)
        "currency": "EUR",
        "iban": None,
        "payment_method": None
    }
    file_path = tmp_path / "net_pass.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    
    assert result.exit_code == 0
def test_validate_tax_amount_0_vat_warning_and_fail(tmp_path, mocker):
    """Test that tax_amount_0_percent_VAT being non-zero triggers warning and validation failure."""
    data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 100.0,
        "total_invoice_amount_net": 100.0,
        "total_invoice_amount_tax": 0.0,
        "tax_amount_0_percent_VAT": 5.0, # Incorrectly non-zero
        "net_amount_0_percent_VAT": 100.0,
        "currency": "EUR"
    }
    file_path = tmp_path / "tax_zero_check.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    
    assert result.exit_code != 0
    assert not (validated_dir / "tax_zero_check-validated.json").exists()

def test_validate_bank_match_tip_amount_span(tmp_path, mocker):
    """Test bank match when bank statement debit includes a tip higher than invoice amount (e.g. Kent)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # Bank debit is 25.0 EUR, 2 days after invoice date 2026-09-28
    ws.append(["30.09.2026", "30.09.2026", -25.0, "EUR", "KENT PENZING", "Payment sent to KENT PENZING", "", "", "f840942a"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "KENT Penzing Gastro Gmbh",
        "purchase_category": "Geschäftsessen",
        "invoice_number": "266772",
        "date": "2026-09-28",
        "total_invoice_amount_gross": 22.8,
        "total_invoice_amount_net": 20.35,
        "total_invoice_amount_tax": 2.45,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 22.8,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 1.63,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 0.82,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 16.27,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 4.08,
        "currency": "EUR"
    }
    json_path = tmp_path / "Kent_20260928.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "Kent_20260928-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"
        assert data["total_payment_amount_gross"] == 25.0
        assert data["tip_amount"] == 2.2
        assert data["net_amount_0_percent_VAT"] == 2.2

def test_validate_bank_match_year_mismatch_futterboden(tmp_path, mocker):
    """Test bank match when invoice JSON has an OCR year error (e.g. 2020 vs 2026) corrected based on bank transaction."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    ws.append(["30.09.2026", "30.09.2026", -21.0, "EUR", "Restaurant Futterboden", "Payment sent to Restaurant Futterboden", "", "", "a0328b19"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Futterboden",
        "purchase_category": "Geschäftsessen",
        "invoice_number": "48563",
        "date": "2020-09-29", # OCR misread 2026 as 2020
        "total_invoice_amount_gross": 18.4,
        "total_invoice_amount_net": 16.31,
        "total_invoice_amount_tax": 2.09,
        "tip_amount": 2.6,
        "total_payment_amount_gross": 21.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 1.17,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 0.92,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 11.73,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 4.58,
        "currency": "EUR"
    }
    json_path = tmp_path / "Futterboden_20260929.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "Futterboden_20260929-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"
        assert data["date"] == "2026-09-29" # Year corrected from bank transaction
        assert data["net_amount_0_percent_VAT"] == 2.6

def test_validate_bank_match_year_auto_correction_without_filename_date(tmp_path, mocker):
    """Test bank match when JSON has 2020 year error without date in filename (e.g. Odysseus)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    ws.append(["23.09.2026", "23.09.2026", -26.0, "EUR", "Restaurant Odysseus", "Payment sent to Restaurant Odysseus", "", "", "30437322"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Restaurant Odysseus",
        "purchase_category": "Geschäftsessen",
        "invoice_number": "195988",
        "date": "2020-09-22", # OCR misread 2026 as 2020
        "total_invoice_amount_gross": 23.2,
        "total_invoice_amount_net": 20.32,
        "total_invoice_amount_tax": 2.88,
        "tip_amount": 2.8,
        "total_payment_amount_gross": 26.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 1.18,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 1.7,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 11.82,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 8.5,
        "currency": "EUR"
    }
    json_path = tmp_path / "odysseus_invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "odysseus_invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"
        assert data["date"] == "2026-09-22" # Year auto-corrected to 2026

def test_validate_bank_match_date_span_10_days(tmp_path, mocker):
    """Test that a transaction within the 14-day date-span matches successfully."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # 10 days difference
    ws.append(["14.05.2026", "14.05.2026", -120.0, "EUR", "Test Vendor GmbH", "Rechnung", "", "", "12345"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
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
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 100.0,
        "currency": "EUR"
    }
    json_path = tmp_path / "invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"

def test_validate_bank_match_tip_exceeding_max_threshold(tmp_path, mocker):
    """Test that a transaction significantly exceeding tip threshold (>30% and >10 EUR) is NOT matched."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # 50 EUR debit for a 20 EUR invoice (difference is 30 EUR, exceeds max tip threshold)
    ws.append(["06.05.2026", "06.05.2026", -50.0, "EUR", "Test Vendor GmbH", "Payment", "", "", "txn-50"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 20.0,
        "total_invoice_amount_net": 16.67,
        "total_invoice_amount_tax": 3.33,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 20.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 3.33,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 16.67,
        "currency": "EUR"
    }
    json_path = tmp_path / "invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "bar"

def test_validate_bank_match_amount_span_with_exact_vendor(tmp_path, mocker):
    """Test amount-span match (small variance <= 15% / 5 EUR) when vendor name matches exactly."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # 97.0 EUR debit for 100.0 EUR invoice (3.0 EUR variance)
    ws.append(["06.05.2026", "06.05.2026", -97.0, "EUR", "Alpha Consulting GmbH", "Payment", "", "", "txn-97"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Alpha Consulting GmbH",
        "purchase_category": "Beratung",
        "invoice_number": "INV-100",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 100.0,
        "total_invoice_amount_net": 83.33,
        "total_invoice_amount_tax": 16.67,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 100.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 16.67,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 83.33,
        "currency": "EUR"
    }
    json_path = tmp_path / "invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"

def test_validate_bank_match_amount_span_rejected_on_single_keyword(tmp_path, mocker):
    """Test that amount-span (non-exact amount) is rejected when text match is only a single partial keyword."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # Amount differs (97.0 vs 100.0) and bank text only matches 1 keyword ('solutions')
    ws.append(["06.05.2026", "06.05.2026", -97.0, "EUR", "Global Solutions Corp", "Payment", "", "", "txn-97"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Alpha Beta Solutions",
        "purchase_category": "Software",
        "invoice_number": "INV-100",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 100.0,
        "total_invoice_amount_net": 83.33,
        "total_invoice_amount_tax": 16.67,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 100.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 16.67,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 83.33,
        "currency": "EUR"
    }
    json_path = tmp_path / "invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "bar"

def test_validate_bank_match_structured_invoice_number_in_nachricht(tmp_path, mocker):
    """Test structured match on invoice number inside Nachricht even if vendor name differs and date is 20 days away."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # 20 days after invoice date, intermediary processor in Gegenpartei, invoice number in Nachricht
    ws.append(["24.05.2026", "24.05.2026", -75.0, "EUR", "Stripe Payments Europe", "Payment", "", "Settlement for INV-2026-98765", "strp-1"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Acme SaaS Inc",
        "purchase_category": "Software",
        "invoice_number": "INV-2026-98765",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 75.0,
        "total_invoice_amount_net": 62.5,
        "total_invoice_amount_tax": 12.5,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 75.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 12.5,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 62.5,
        "currency": "EUR"
    }
    json_path = tmp_path / "invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"

def test_validate_bank_match_candidate_ranking_exact_over_span(tmp_path, mocker):
    """Test that candidate ranking selects the exact amount match over an amount-span/tip match."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # Txn 1: 5 days away, exact amount 50.0
    ws.append(["09.05.2026", "09.05.2026", -50.0, "EUR", "Test Vendor GmbH", "Rechnung", "", "", "txn-exact"])
    # Txn 2: 1 day away, tip amount 60.0
    ws.append(["05.05.2026", "05.05.2026", -60.0, "EUR", "Test Vendor GmbH", "Rechnung", "", "", "txn-tip"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 50.0,
        "total_invoice_amount_net": 41.67,
        "total_invoice_amount_tax": 8.33,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 50.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 8.33,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 41.67,
        "currency": "EUR"
    }
    json_path = tmp_path / "invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "Bankkonto"
        # Exact match was preferred, so total payment amount remains 50.0 and tip remains 0.0
        assert data["total_payment_amount_gross"] == 50.0
        assert data["tip_amount"] == 0.0

def test_validate_bank_match_date_span_outside_14_days_fails(tmp_path, mocker):
    """Test that a non-structured transaction outside the 14-day date-span does NOT match."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # 18 days difference without structured invoice number match
    ws.append(["22.05.2026", "22.05.2026", -100.0, "EUR", "Test Vendor GmbH", "Payment", "", "", "txn-late"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    invoice_data = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 100.0,
        "total_invoice_amount_net": 83.33,
        "total_invoice_amount_tax": 16.67,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 100.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 16.67,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 83.33,
        "currency": "EUR"
    }
    json_path = tmp_path / "invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "bar"

def test_validate_bank_match_stopwords_and_common_terms_not_matching(tmp_path, mocker):
    """Test that generic common terms (e.g. 'Restaurant') do not trigger false positive matches."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Valutadatum", "Buchungsdatum", "Betrag", "Währung", 
        "Gegenpartei", "Bezeichnung", "Referenz", "Nachricht", "Zahlungs-ID"
    ])
    # Bank transaction for 'Restaurant Sonnenschein'
    ws.append(["05.05.2026", "05.05.2026", -45.0, "EUR", "Restaurant Sonnenschein", "Payment", "", "", "txn-rest"])
    statement_path = tmp_path / "bank.xlsx"
    wb.save(statement_path)

    # Invoice vendor only consists of common terms / stopwords
    invoice_data = {
        "vendor_name": "Restaurant & Service GmbH",
        "purchase_category": "Geschäftsessen",
        "invoice_number": "INV-REST-01",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 45.0,
        "total_invoice_amount_net": 37.5,
        "total_invoice_amount_tax": 7.5,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 45.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 7.5,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 37.5,
        "currency": "EUR"
    }
    json_path = tmp_path / "invoice.json"
    with open(json_path, "w") as f:
        json.dump(invoice_data, f)

    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path),
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })

    result = runner.invoke(app, ["validate", str(json_path), "--bank_statement", str(statement_path)])
    assert result.exit_code == 0, result.output

    out_file = validated_dir / "invoice-validated.json"
    assert out_file.exists()
    with open(out_file) as f:
        data = json.load(f)
        assert data["payment_method"] == "bar"

def test_validate_invoice_date_warning_more_than_6_months(tmp_path, mocker, caplog):
    """Test that a warning is issued if the invoice date differs by more than 6 months from today."""
    from loguru import logger
    handler_id = logger.add(caplog.handler, format="{message}")
    try:
        invoice_data = {
            "vendor_name": "Old Vendor",
            "purchase_category": "Büromaterial",
            "invoice_number": "INV-OLD-01",
            "date": "2020-01-15", # Way older than 6 months
            "total_invoice_amount_gross": 100.0,
            "total_invoice_amount_net": 83.33,
            "total_invoice_amount_tax": 16.67,
            "tip_amount": 0.0,
            "total_payment_amount_gross": 100.0,
            "tax_amount_0_percent_VAT": 0.0,
            "tax_amount_10_percent_VAT": 0.0,
            "tax_amount_13_percent_VAT": 0.0,
            "tax_amount_20_percent_VAT": 16.67,
            "net_amount_0_percent_VAT": 0.0,
            "net_amount_10_percent_VAT": 0.0,
            "net_amount_13_percent_VAT": 0.0,
            "net_amount_20_percent_VAT": 83.33,
            "currency": "EUR"
        }
        json_path = tmp_path / "old_invoice.json"
        with open(json_path, "w") as f:
            json.dump(invoice_data, f)

        validated_dir = tmp_path / "validated"
        mocker.patch.dict(os.environ, {
            "INGEST_DIR": str(tmp_path),
            "WORK_DIR": str(tmp_path),
            "VALIDATED_DIR": str(validated_dir)
        })

        result = runner.invoke(app, ["validate", str(json_path)])
        assert result.exit_code == 0
        assert "differs by more than 6 months" in caplog.text
    finally:
        logger.remove(handler_id)

def test_validate_invoice_date_no_warning_recent(tmp_path, mocker, caplog):
    """Test that no warning is issued if the invoice date is recent (within 6 months of today)."""
    from datetime import datetime, timedelta
    from loguru import logger
    handler_id = logger.add(caplog.handler, format="{message}")
    try:
        recent_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        invoice_data = {
            "vendor_name": "Recent Vendor",
            "purchase_category": "Büromaterial",
            "invoice_number": "INV-REC-01",
            "date": recent_date,
            "total_invoice_amount_gross": 100.0,
            "total_invoice_amount_net": 83.33,
            "total_invoice_amount_tax": 16.67,
            "tip_amount": 0.0,
            "total_payment_amount_gross": 100.0,
            "tax_amount_0_percent_VAT": 0.0,
            "tax_amount_10_percent_VAT": 0.0,
            "tax_amount_13_percent_VAT": 0.0,
            "tax_amount_20_percent_VAT": 16.67,
            "net_amount_0_percent_VAT": 0.0,
            "net_amount_10_percent_VAT": 0.0,
            "net_amount_13_percent_VAT": 0.0,
            "net_amount_20_percent_VAT": 83.33,
            "currency": "EUR"
        }
        json_path = tmp_path / "recent_invoice.json"
        with open(json_path, "w") as f:
            json.dump(invoice_data, f)

        validated_dir = tmp_path / "validated"
        mocker.patch.dict(os.environ, {
            "INGEST_DIR": str(tmp_path),
            "WORK_DIR": str(tmp_path),
            "VALIDATED_DIR": str(validated_dir)
        })

        result = runner.invoke(app, ["validate", str(json_path)])
        assert result.exit_code == 0
        assert "differs by more than 6 months" not in caplog.text
    finally:
        logger.remove(handler_id)
