import os
import json
import pytest
from pathlib import Path
from typer.testing import CliRunner
from ii_workflow.main import app
from google.genai import types

runner = CliRunner()

@pytest.fixture
def mock_genai_client(mocker):
    """Fixture to mock the Google GenAI client and speed up time.sleep."""
    mocker.patch("time.sleep", return_value=None)
    mock_client = mocker.patch("ii_workflow.ingest.Client")
    return mock_client

def test_ingest_batch_create_retry_success(mock_genai_client, tmp_path, mocker):
    """Test successful ingestion after two batch creation failures."""
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy content")
    
    ingested_dir = tmp_path / "ingested"
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path), 
        "INGESTED_DIR": str(ingested_dir),
        "GEMINI_API_KEY": "test-key"
    })
    
    # Mock Gemini components
    mock_job = mocker.Mock(state="COMPLETED", name="batches/test-job")
    mock_job.dest = mocker.Mock(file_name="files/output")
    
    # Mock file upload success
    mock_genai_client.return_value.files.upload.return_value = mocker.Mock(name="files/input")
    
    # Mock batch creation: Fail twice, then succeed
    mock_genai_client.return_value.batches.create.side_effect = [
        Exception("Transient API Error 1"),
        Exception("Transient API Error 2"),
        mock_job
    ]
    
    # Mock polling success
    mock_genai_client.return_value.batches.get.return_value = mock_job
    
    # Mock download success
    mock_data_dict = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
        "date": "2024-05-04",
        "total_invoice_amount_gross": 100.0,
        "total_invoice_amount_net": 80.0,
        "total_invoice_amount_tax": 20.0,
        "currency": "EUR"
    }
    response_jsonl = json.dumps({
        "response": {
            "candidates": [{"content": {"parts": [{"text": json.dumps(mock_data_dict)}]}}]
        }
    })
    mock_genai_client.return_value.files.download.return_value = response_jsonl.encode("utf-8")
    
    result = runner.invoke(app, ["ingest", str(invoice_file)])
    
    assert result.exit_code == 0
    assert mock_genai_client.return_value.batches.create.call_count == 3
    assert (ingested_dir / "test_invoice.json").exists()

def test_ingest_batch_create_retry_failure(mock_genai_client, tmp_path, mocker):
    """Test ingestion failure after all batch creation retries fail."""
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy content")
    
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path), 
        "INGESTED_DIR": str(tmp_path / "ingested"),
        "GEMINI_API_KEY": "test-key"
    })
    
    # Mock file upload success
    mock_genai_client.return_value.files.upload.return_value = mocker.Mock(name="files/input")
    
    # Mock batch creation: Fail 4 times (1 initial + 3 retries)
    mock_genai_client.return_value.batches.create.side_effect = Exception("Persistent API Error")
    
    result = runner.invoke(app, ["ingest", str(invoice_file)])
    
    assert result.exit_code != 0
    # Initial call + 3 retries = 4 calls total
    assert mock_genai_client.return_value.batches.create.call_count == 4

def test_ingest_polling_retry_success(mock_genai_client, tmp_path, mocker):
    """Test successful ingestion after a polling failure."""
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy content")
    
    ingested_dir = tmp_path / "ingested"
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path), 
        "INGESTED_DIR": str(ingested_dir),
        "GEMINI_API_KEY": "test-key"
    })
    
    mock_job = mocker.Mock(state="COMPLETED", name="batches/test-job")
    mock_job.dest = mocker.Mock(file_name="files/output")
    
    mock_genai_client.return_value.files.upload.return_value = mocker.Mock(name="files/input")
    mock_genai_client.return_value.batches.create.return_value = mock_job
    
    # Mock polling: Fail once, then return success
    mock_genai_client.return_value.batches.get.side_effect = [
        Exception("Polling Glitch"),
        mock_job
    ]
    
    mock_data_dict = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-001",
        "date": "2024-05-04",
        "total_invoice_amount_gross": 100.0,
        "total_invoice_amount_net": 80.0,
        "total_invoice_amount_tax": 20.0,
        "currency": "EUR"
    }
    response_jsonl = json.dumps({
        "response": {
            "candidates": [{"content": {"parts": [{"text": json.dumps(mock_data_dict)}]}}]
        }
    })
    mock_genai_client.return_value.files.download.return_value = response_jsonl.encode("utf-8")
    
    result = runner.invoke(app, ["ingest", str(invoice_file)])
    
    assert result.exit_code == 0
    assert mock_genai_client.return_value.batches.get.call_count == 2

def test_ingest_polling_retry_failure(mock_genai_client, tmp_path, mocker):
    """Test ingestion failure after all polling retries fail."""
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy content")
    
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path), 
        "INGESTED_DIR": str(tmp_path / "ingested"),
        "GEMINI_API_KEY": "test-key"
    })
    
    mock_job = mocker.Mock(state="RUNNING", name="batches/test-job")
    
    mock_genai_client.return_value.files.upload.return_value = mocker.Mock(name="files/input")
    mock_genai_client.return_value.batches.create.return_value = mock_job
    
    # Mock polling: Fail 4 times consecutively
    mock_genai_client.return_value.batches.get.side_effect = Exception("Persistent Polling Error")
    
    result = runner.invoke(app, ["ingest", str(invoice_file)])
    
    assert result.exit_code != 0
    assert mock_genai_client.return_value.batches.get.call_count == 4
