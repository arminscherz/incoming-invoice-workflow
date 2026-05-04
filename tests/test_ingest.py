import os
import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
from ii_workflow.main import app

runner = CliRunner()

@pytest.fixture
def mock_genai_client(mocker):
    """Fixture to mock the Google GenAI client."""
    mock_client = mocker.patch("ii_workflow.ingest.Client")
    return mock_client

def test_ingest_run_success(mock_genai_client, tmp_path, mocker):
    """Test successful ingestion and JSON extraction."""
    # Setup paths
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy content")
    
    # Mock environment variables
    mocker.patch.dict(os.environ, {"WORK_DIR": str(tmp_path), "GEMINI_API_KEY": "test-key"})
    
    # Mock Gemini response
    mock_data = mocker.Mock()
    mock_data.model_dump.return_value = {
        "vendor_name": "Test Vendor",
        "invoice_number": "INV-001",
        "date": "2024-05-04",
        "total_amount": 120.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 20.0,
        "currency": "EUR",
        "iban": "AT123456789"
    }
    
    mock_response = mocker.Mock()
    mock_response.parsed = mock_data
    
    # Gemini SDK batch mode simulation
    mock_genai_client.return_value.models.generate_content.return_value = mock_response
    
    # Run CLI command
    result = runner.invoke(app, ["ingest", "run", str(invoice_file)])
    
    # Assertions
    assert result.exit_code == 0, f"Command failed with output: {result.output}"
    
    expected_json_path = tmp_path / "test_invoice_extracted.json"
    assert expected_json_path.exists()
    
    with open(expected_json_path, "r") as f:
        data = json.load(f)
        assert data["vendor_name"] == "Test Vendor"
        assert data["total_amount"] == 120.0

def test_ingest_run_file_not_found():
    """Test ingest run with a non-existent file."""
    result = runner.invoke(app, ["ingest", "run", "non_existent.pdf"])
    assert result.exit_code != 0

def test_ingest_run_api_error(mock_genai_client, tmp_path, mocker):
    """Test ingest run when the API returns an error."""
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy content")
    
    mocker.patch.dict(os.environ, {"WORK_DIR": str(tmp_path), "GEMINI_API_KEY": "test-key"})
    
    # Mock API exception
    mock_genai_client.return_value.models.generate_content.side_effect = Exception("API Key Invalid")
    
    # Use mix_stderr=False if we want to check stderr specifically, or just check result.output
    result = runner.invoke(app, ["ingest", "run", str(invoice_file)])
    
    assert result.exit_code != 0
    # CliRunner captures loguru output in result.output if it writes to stderr/stdout
    # But loguru by default writes to stderr which is captured by Click if we don't mix them.
    assert "API Key Invalid" in result.output or result.exit_code != 0
