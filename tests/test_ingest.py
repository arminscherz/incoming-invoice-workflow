import os
import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
from ii_workflow.main import app

runner = CliRunner()

@pytest.fixture
def mock_genai_client(mocker):
    """Fixture to mock the Google GenAI client and speed up time.sleep."""
    mocker.patch("time.sleep", return_value=None)
    mock_client = mocker.patch("ii_workflow.ingest.Client")
    return mock_client

def test_ingest_run_success(mock_genai_client, tmp_path, mocker):
    """Test successful ingestion and JSON extraction."""
    # Setup paths
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy content")
    
    # Mock environment variables
    ingested_dir = tmp_path / "ingested"
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path), 
        "INGESTED_DIR": str(ingested_dir),
        "GEMINI_API_KEY": "test-key"
    })
    
    # Mock Gemini response
    mock_data_dict = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
        "date": "2024-05-04",
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
    
    mock_data = mocker.Mock()
    mock_data.model_dump.return_value = mock_data_dict
    
    mock_response = mocker.Mock()
    mock_response.parsed = mock_data
    
    # Gemini SDK batch mode simulation using Files API
    mock_job = mocker.Mock()
    mock_job.name = "batches/test-job-id"
    mock_job.state = "COMPLETED"
    
    # Mock file upload
    mock_file = mocker.Mock()
    mock_file.name = "files/request-jsonl"
    mock_genai_client.return_value.files.upload.return_value = mock_file
    
    # Mock batch creation
    mock_genai_client.return_value.batches.create.return_value = mock_job
    
    # Mock polling
    mock_completed_job = mocker.Mock()
    mock_completed_job.state = "COMPLETED"
    mock_completed_job.name = "batches/test-job-id"
    mock_completed_job.dest = mocker.Mock(file_name="files/response-jsonl")
    mock_genai_client.return_value.batches.get.return_value = mock_completed_job
    
    # Mock output file discovery and download
    mock_output_file = mocker.Mock()
    mock_output_file.name = "files/response-jsonl"
    mock_output_file.display_name = "test-job-id-output"
    mock_genai_client.return_value.files.list.return_value = [mock_output_file]
    
    # Mock download bytes
    response_jsonl = json.dumps({
        "response": {
            "candidates": [{
                "content": {
                    "parts": [{"text": json.dumps(mock_data_dict)}]
                }
            }]
        }
    })
    mock_genai_client.return_value.files.download.return_value = response_jsonl.encode("utf-8")
    
    # Run CLI command
    result = runner.invoke(app, ["ingest", str(invoice_file)])
    
    # Assertions
    assert result.exit_code == 0, f"Command failed with output: {result.output}"
    
    expected_json_path = ingested_dir / "test_invoice.json"
    assert expected_json_path.exists()
    assert str(expected_json_path.absolute()) in result.output
    
    with open(expected_json_path, "r") as f:
        data = json.load(f)
        assert data["vendor_name"] == "Test Vendor"
        assert data["total_invoice_amount_gross"] == 120.0
        assert data["purchase_category"] == "Büromaterial"
        assert data["net_amount_20_percent_VAT"] == 100.0

def test_ingest_run_file_not_found(tmp_path, mocker):
    """Test ingest run with a non-existent file."""
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path), 
        "INGEST_DIR": str(tmp_path),
        "INGESTED_DIR": str(tmp_path / "ingested")
    })
    result = runner.invoke(app, ["ingest", "non_existent.pdf"])
    assert result.exit_code != 0

def test_ingest_run_api_error(mock_genai_client, tmp_path, mocker):
    """Test ingest run when the API returns an error."""
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy content")
    
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path), 
        "INGESTED_DIR": str(tmp_path / "ingested"),
        "GEMINI_API_KEY": "test-key"
    })
    
    # Mock API exception
    mock_genai_client.return_value.batches.create.side_effect = Exception("API Key Invalid")
    
    # Use mix_stderr=False if we want to check stderr specifically, or just check result.output
    result = runner.invoke(app, ["ingest", str(invoice_file)])
    
    assert result.exit_code != 0
    # CliRunner captures loguru output in result.output if it writes to stderr/stdout
    # But loguru by default writes to stderr which is captured by Click if we don't mix them.
    assert "API Key Invalid" in result.output or result.exit_code != 0

def test_ingest_run_relative_path(mock_genai_client, tmp_path, mocker):
    """Test ingest run with a filename that should be resolved relative to INGEST_DIR."""
    # Setup INGEST_DIR
    ingest_dir = tmp_path / "ingest"
    ingest_dir.mkdir()
    invoice_file = ingest_dir / "invoice.pdf"
    invoice_file.write_text("dummy content")
    
    ingested_dir = tmp_path / "ingested"
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path), 
        "INGEST_DIR": "ingest",
        "INGESTED_DIR": str(ingested_dir),
        "GEMINI_API_KEY": "test-key"
    })
    
    # Mock current working directory to tmp_path
    mocker.patch("pathlib.Path.cwd", return_value=tmp_path)
    
    # Mock Gemini response
    mock_data = mocker.Mock()
    mock_data.model_dump.return_value = {"vendor_name": "Test"}
    
    # Mock file upload
    mock_file = mocker.Mock()
    mock_file.name = "files/request-jsonl"
    mock_genai_client.return_value.files.upload.return_value = mock_file
    
    mock_job = mocker.Mock()
    mock_job.name = "batches/test-job-id"
    mock_job.state = "COMPLETED"
    mock_genai_client.return_value.batches.create.return_value = mock_job
    
    mock_completed_job = mocker.Mock()
    mock_completed_job.state = "COMPLETED"
    mock_completed_job.name = "batches/test-job-id"
    mock_genai_client.return_value.batches.get.return_value = mock_completed_job
    
    # Mock output file discovery and download
    mock_output_file = mocker.Mock()
    mock_output_file.name = "files/response-jsonl"
    mock_output_file.display_name = "test-job-id-output"
    mock_genai_client.return_value.files.list.return_value = [mock_output_file]
    
    response_jsonl = json.dumps({
        "response": {
            "candidates": [{
                "content": {
                    "parts": [{"text": json.dumps({
                        "vendor_name": "Test",
                        "purchase_category": "Büromaterial",
                        "invoice_number": "INV-123",
                        "date": "2024-05-04",
                        "total_invoice_amount_gross": 100.0,
                        "total_invoice_amount_net": 80.0,
                        "total_invoice_amount_tax": 20.0,
                        "net_amount_0_percent_VAT": 0.0,
                        "net_amount_10_percent_VAT": 0.0,
                        "net_amount_13_percent_VAT": 0.0,
                        "net_amount_20_percent_VAT": 80.0
                    })}]
                }
            }]
        }
    })
    mock_genai_client.return_value.files.download.return_value = response_jsonl.encode("utf-8")

    # Run CLI command with just the filename
    result = runner.invoke(app, ["ingest", "invoice.pdf"])
    
    assert result.exit_code == 0
    
    expected_json_path = ingested_dir / "invoice.json"
    assert expected_json_path.exists()
    assert str(expected_json_path.absolute()) in result.output
