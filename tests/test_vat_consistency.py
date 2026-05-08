import json
import os
import pytest
from typer.testing import CliRunner
from ii_workflow.main import app

runner = CliRunner()

@pytest.fixture
def base_invoice_data():
    return {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-VAT-TEST",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 120.0,
        "total_invoice_amount_net": 100.0,
        "total_invoice_amount_tax": 20.0,
        "tip_amount": 0.0,
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

def test_validate_vat_consistency_pass(base_invoice_data, tmp_path, mocker):
    """Test that valid VAT amounts pass validation."""
    file_path = tmp_path / "vat_pass.json"
    with open(file_path, "w") as f:
        json.dump(base_invoice_data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    assert result.exit_code == 0

def test_validate_vat_consistency_fail_10_percent(base_invoice_data, tmp_path, mocker, caplog):
    """Test that inconsistent 10% VAT fails validation."""
    base_invoice_data["net_amount_10_percent_VAT"] = 100.0
    base_invoice_data["tax_amount_10_percent_VAT"] = 5.0  # Should be 10.0
    base_invoice_data["total_invoice_amount_net"] = 100.0
    base_invoice_data["total_invoice_amount_tax"] = 5.0
    base_invoice_data["total_invoice_amount_gross"] = 105.0
    base_invoice_data["tax_amount_20_percent_VAT"] = 0.0
    base_invoice_data["net_amount_20_percent_VAT"] = 0.0
    
    file_path = tmp_path / "vat_fail_10.json"
    with open(file_path, "w") as f:
        json.dump(base_invoice_data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    assert result.exit_code != 0
    # Loguru output might not be in result.output, but we can check the exit code
    # and maybe rely on the fact that we saw the error in the logs.
    # To be sure, we can check caplog if we configure loguru to use standard logging.
    # But for now, the exit code + the fact it's an error is enough.

def test_validate_vat_consistency_fail_13_percent(base_invoice_data, tmp_path, mocker):
    """Test that inconsistent 13% VAT fails validation."""
    base_invoice_data["net_amount_13_percent_VAT"] = 100.0
    base_invoice_data["tax_amount_13_percent_VAT"] = 10.0  # Should be 13.0
    base_invoice_data["total_invoice_amount_net"] = 100.0
    base_invoice_data["total_invoice_amount_tax"] = 10.0
    base_invoice_data["total_invoice_amount_gross"] = 110.0
    base_invoice_data["tax_amount_20_percent_VAT"] = 0.0
    base_invoice_data["net_amount_20_percent_VAT"] = 0.0
    
    file_path = tmp_path / "vat_fail_13.json"
    with open(file_path, "w") as f:
        json.dump(base_invoice_data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    assert result.exit_code != 0

def test_validate_vat_consistency_fail_20_percent(base_invoice_data, tmp_path, mocker):
    """Test that inconsistent 20% VAT fails validation."""
    base_invoice_data["net_amount_20_percent_VAT"] = 100.0
    base_invoice_data["tax_amount_20_percent_VAT"] = 18.0  # Should be 20.0
    base_invoice_data["total_invoice_amount_net"] = 100.0
    base_invoice_data["total_invoice_amount_tax"] = 18.0
    base_invoice_data["total_invoice_amount_gross"] = 118.0
    
    file_path = tmp_path / "vat_fail_20.json"
    with open(file_path, "w") as f:
        json.dump(base_invoice_data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    assert result.exit_code != 0

def test_validate_vat_consistency_pass_with_small_rounding(base_invoice_data, tmp_path, mocker):
    """Test that small rounding differences (<= 2 cents) still pass."""
    base_invoice_data["net_amount_20_percent_VAT"] = 100.0
    base_invoice_data["tax_amount_20_percent_VAT"] = 20.01  # 1 cent off
    base_invoice_data["total_invoice_amount_net"] = 100.0
    base_invoice_data["total_invoice_amount_tax"] = 20.01
    base_invoice_data["total_invoice_amount_gross"] = 120.01
    
    file_path = tmp_path / "vat_pass_rounding.json"
    with open(file_path, "w") as f:
        json.dump(base_invoice_data, f)
        
    validated_dir = tmp_path / "validated"
    mocker.patch.dict(os.environ, {
        "INGEST_DIR": str(tmp_path), 
        "WORK_DIR": str(tmp_path),
        "VALIDATED_DIR": str(validated_dir)
    })
    
    result = runner.invoke(app, ["validate", str(file_path)])
    assert result.exit_code == 0
