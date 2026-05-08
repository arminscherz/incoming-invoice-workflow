import os
import json
import pytest
from pathlib import Path
from typer.testing import CliRunner
from ii_workflow.main import app

runner = CliRunner()

@pytest.fixture
def mock_gdrive_service(mocker):
    """Fixture to mock Google Drive API service."""
    mock_build = mocker.patch("googleapiclient.discovery.build")
    mock_service = mock_build.return_value
    return mock_service

@pytest.fixture
def mock_genai_client(mocker):
    """Fixture to mock Gemini client."""
    mocker.patch("time.sleep", return_value=None)
    mock_client = mocker.patch("ii_workflow.ingest.Client")
    return mock_client

def test_ingest_with_gdrive_link_success(mock_genai_client, mock_gdrive_service, tmp_path, mocker):
    """Test ingestion with successful Google Drive link lookup."""
    # 1. Setup paths
    invoice_file = tmp_path / "test_invoice.pdf"
    invoice_file.write_text("dummy")
    
    ingested_dir = tmp_path / "ingested"
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path),
        "INGESTED_DIR": str(ingested_dir),
        "GEMINI_API_KEY": "test-key",
        "GDRIVE_OAUTH_CLIENT_ID": "test-id",
        "GDRIVE_OAUTH_CLIENT_KEY": "test-key"
    })
    
    # 2. Mock Gemini extraction
    mock_data_dict = {
        "vendor_name": "Test Vendor",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-100",
        "date": "2024-05-08",
        "total_invoice_amount_gross": 50.0,
        "total_invoice_amount_net": 40.0,
        "total_invoice_amount_tax": 10.0,
        "net_amount_20_percent_VAT": 40.0
    }
    
    # Mocking the batch download logic
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
    
    # Mock batch job success
    mock_job = mocker.Mock()
    mock_job.state = "COMPLETED"
    mock_job.dest = mocker.Mock(file_name="files/output")
    mock_genai_client.return_value.batches.create.return_value = mock_job
    mock_genai_client.return_value.batches.get.return_value = mock_job
    
    # 3. Mock Google Drive lookup
    # First call: Folder lookup, Second call: File lookup
    mock_folder_list = {"files": [{"id": "folder-id-abc", "name": "Eingang"}]}
    mock_file_list = {
        "files": [
            {
                "id": "gdrive-file-id-123",
                "name": "test_invoice.pdf",
                "webViewLink": "https://drive.google.com/file/d/gdrive-file-id-123/view"
            }
        ]
    }
    mock_gdrive_service.files().list().execute.side_effect = [mock_folder_list, mock_file_list]
    
    # 4. Mock OAuth flow to avoid browser opening
    mocker.patch("ii_workflow.ingest.get_gdrive_service", return_value=mock_gdrive_service)

    # 5. Run ingest command
    result = runner.invoke(app, ["ingest", str(invoice_file)])
    
    # 6. Assertions
    assert result.exit_code == 0
    
    expected_json_path = ingested_dir / "test_invoice.json"
    assert expected_json_path.exists()
    
    with open(expected_json_path, "r") as f:
        data = json.load(f)
        assert data["gdrive_link"] == "https://drive.google.com/file/d/gdrive-file-id-123/view"

def test_ingest_gdrive_link_not_found(mock_genai_client, mock_gdrive_service, tmp_path, mocker):
    """Test ingestion when file is not found on Google Drive."""
    invoice_file = tmp_path / "not_on_drive.pdf"
    invoice_file.write_text("dummy")
    
    ingested_dir = tmp_path / "ingested"
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path),
        "INGESTED_DIR": str(ingested_dir),
        "GEMINI_API_KEY": "test-key",
        "GDRIVE_OAUTH_CLIENT_ID": "test-id",
        "GDRIVE_OAUTH_CLIENT_KEY": "test-key"
    })
    
    # Gemini mock (simplified)
    mock_job = mocker.Mock(state="COMPLETED", dest=mocker.Mock(file_name="files/output"))
    mock_genai_client.return_value.batches.create.return_value = mock_job
    mock_genai_client.return_value.batches.get.return_value = mock_job
    mock_genai_client.return_value.files.download.return_value = json.dumps({
        "response": {"candidates": [{"content": {"parts": [{"text": json.dumps({"vendor_name": "X", "invoice_number": "1", "date": "2024-01-01", "total_invoice_amount_gross": 0, "total_invoice_amount_net": 0, "total_invoice_amount_tax": 0, "purchase_category": "X"})}]}}]}
    }).encode("utf-8")

    # Mock GDrive: Folder found, but file not found
    mock_folder_list = {"files": [{"id": "folder-id-abc", "name": "Eingang"}]}
    mock_gdrive_service.files().list().execute.side_effect = [mock_folder_list, {"files": []}]
    mocker.patch("ii_workflow.ingest.get_gdrive_service", return_value=mock_gdrive_service)

    result = runner.invoke(app, ["ingest", str(invoice_file)])
    
    assert result.exit_code == 0
    
    with open(ingested_dir / "not_on_drive.json", "r") as f:
        data = json.load(f)
        assert data.get("gdrive_link") is None

def test_record_with_gdrive_link(tmp_path, mocker):
    """Test that the record command includes gdrive_link in the CSV."""
    # 1. Setup paths
    json_dir = tmp_path / "ingested"
    json_dir.mkdir()
    json_file = json_dir / "invoice.json"
    
    csv_path = tmp_path / "record.csv"
    
    # 2. Create JSON with gdrive_link
    mock_data = {
        "vendor_name": "Test Vendor",
        "invoice_number": "INV-123",
        "date": "2024-05-08",
        "purchase_category": "Büromaterial",
        "total_invoice_amount_gross": 100.0,
        "total_invoice_amount_net": 80.0,
        "total_invoice_amount_tax": 20.0,
        "gdrive_link": "https://drive.google.com/test-link"
    }
    json_file.write_text(json.dumps(mock_data))
    
    # 3. Mock environment
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(json_dir),
        "RESULT_COLUMNS": "vendor_name;invoice_number;date;gdrive_link"
    })
    
    # 4. Run record command
    result = runner.invoke(app, ["record", str(json_file), "--result_csv", str(csv_path)])
    
    # 5. Assertions
    assert result.exit_code == 0
    assert csv_path.exists()
    
    with open(csv_path, "r") as f:
        content = f.read()
        assert "gdrive_link" in content
        assert "https://drive.google.com/test-link" in content
