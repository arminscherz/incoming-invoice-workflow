import os
import shutil
from pathlib import Path
import pytest
from typer.testing import CliRunner
import typer

from ii_workflow.main import app

runner = CliRunner()

@pytest.fixture
def process_dirs(tmp_path):
    """Sets up the required directories for the process orchestrator."""
    dirs = {
        "INGEST_DIR": tmp_path / "ingest",
        "INGESTED_DIR": tmp_path / "ingested",
        "VALIDATED_DIR": tmp_path / "validated",
        "JSON_ARCHIVE_DIR": tmp_path / "json_archive",
        "SCAN_ARCHIVE_DIR": tmp_path / "scan_archive",
        "ERROR_DIR": tmp_path / "error"
    }
    
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
        
    return dirs

@pytest.fixture
def mock_pipeline(mocker):
    """Mocks the underlying step functions."""
    mock_ingest = mocker.patch("ii_workflow.process.ingest_run")
    mock_validate = mocker.patch("ii_workflow.process.validate_run")
    mock_record = mocker.patch("ii_workflow.process.record_run")
    return mock_ingest, mock_validate, mock_record

def test_process_success(process_dirs, mock_pipeline, mocker):
    """Test full successful run on a valid file."""
    # Setup files
    ingest_dir = process_dirs["INGEST_DIR"]
    invoice_file = ingest_dir / "invoice.pdf"
    invoice_file.write_text("dummy")
    
    bank_stmt = ingest_dir / "bank.xlsx"
    bank_stmt.write_text("dummy")
    
    env_vars = {k: str(v) for k, v in process_dirs.items()}
    env_vars["WORK_DIR"] = str(ingest_dir.parent)
    mocker.patch.dict(os.environ, env_vars)
    
    mock_ingest, mock_validate, mock_record = mock_pipeline
    
    # Simulate ingest creating the output json
    def ingest_side_effect(path):
        json_path = process_dirs["INGESTED_DIR"] / f"{Path(path).stem}.json"
        json_path.write_text("{}")
    mock_ingest.side_effect = ingest_side_effect
    
    # Simulate validate creating the validated json
    def validate_side_effect(json_path, bank_statement=None):
        out_path = process_dirs["VALIDATED_DIR"] / f"{Path(json_path).stem}-validated.json"
        out_path.write_text("{}")
    mock_validate.side_effect = validate_side_effect
    
    result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    mock_ingest.assert_called_once()
    mock_validate.assert_called_once()
    mock_record.assert_called_once()
    
    # Check archiving
    assert not invoice_file.exists()
    assert (process_dirs["SCAN_ARCHIVE_DIR"] / "invoice.pdf").exists()
    assert (process_dirs["JSON_ARCHIVE_DIR"] / "invoice.json").exists()
    assert (process_dirs["JSON_ARCHIVE_DIR"] / "invoice-validated.json").exists()
    
    # Bank statement shouldn't be moved by the invoice loop
    assert bank_stmt.exists()

def test_process_ingest_failure(process_dirs, mock_pipeline, mocker):
    """Test ingest failure moves scan to ERROR_DIR."""
    ingest_dir = process_dirs["INGEST_DIR"]
    invoice_file = ingest_dir / "bad_invoice.pdf"
    invoice_file.write_text("dummy")
    
    env_vars = {k: str(v) for k, v in process_dirs.items()}
    env_vars["WORK_DIR"] = str(ingest_dir.parent)
    mocker.patch.dict(os.environ, env_vars)
    
    mock_ingest, mock_validate, mock_record = mock_pipeline
    mock_ingest.side_effect = typer.Exit(code=1)
    
    result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0 # Process completes without crashing
    
    assert not invoice_file.exists()
    assert (process_dirs["ERROR_DIR"] / "bad_invoice.pdf").exists()
    mock_validate.assert_not_called()

def test_process_validate_failure(process_dirs, mock_pipeline, mocker):
    """Test validate failure moves scan to ERROR_DIR."""
    ingest_dir = process_dirs["INGEST_DIR"]
    invoice_file = ingest_dir / "invoice.pdf"
    invoice_file.write_text("dummy")
    
    env_vars = {k: str(v) for k, v in process_dirs.items()}
    env_vars["WORK_DIR"] = str(ingest_dir.parent)
    mocker.patch.dict(os.environ, env_vars)
    
    mock_ingest, mock_validate, mock_record = mock_pipeline
    
    def ingest_side_effect(path):
        json_path = process_dirs["INGESTED_DIR"] / f"{Path(path).stem}.json"
        json_path.write_text("{}")
    mock_ingest.side_effect = ingest_side_effect
    mock_validate.side_effect = typer.Exit(code=1)
    
    result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    
    assert not invoice_file.exists()
    assert (process_dirs["ERROR_DIR"] / "invoice.pdf").exists()
    # The intermediate JSON should probably stay in INGESTED_DIR since it failed validation
    assert (process_dirs["INGESTED_DIR"] / "invoice.json").exists()
    mock_record.assert_not_called()

def test_process_record_duplicate(process_dirs, mock_pipeline, mocker):
    """Test record handling of duplicate (exit 0) archives file."""
    ingest_dir = process_dirs["INGEST_DIR"]
    invoice_file = ingest_dir / "invoice.pdf"
    invoice_file.write_text("dummy")
    
    env_vars = {k: str(v) for k, v in process_dirs.items()}
    env_vars["WORK_DIR"] = str(ingest_dir.parent)
    mocker.patch.dict(os.environ, env_vars)
    
    mock_ingest, mock_validate, mock_record = mock_pipeline
    
    def ingest_side_effect(path):
        json_path = process_dirs["INGESTED_DIR"] / f"{Path(path).stem}.json"
        json_path.write_text("{}")
    mock_ingest.side_effect = ingest_side_effect
    
    def validate_side_effect(json_path, bank_statement=None):
        out_path = process_dirs["VALIDATED_DIR"] / f"{Path(json_path).stem}-validated.json"
        out_path.write_text("{}")
    mock_validate.side_effect = validate_side_effect
    
    mock_record.side_effect = typer.Exit(code=0) # Duplicate throws exit code 0
    
    result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    
    assert not invoice_file.exists()
    assert (process_dirs["SCAN_ARCHIVE_DIR"] / "invoice.pdf").exists()
    assert (process_dirs["JSON_ARCHIVE_DIR"] / "invoice.json").exists()
    assert (process_dirs["JSON_ARCHIVE_DIR"] / "invoice-validated.json").exists()

def test_process_multiple_bank_statements(process_dirs, mock_pipeline, mocker):
    """Test process handles multiple bank statements by picking the youngest and logging a warning."""
    import time
    ingest_dir = process_dirs["INGEST_DIR"]
    
    # Create an older bank statement
    old_stmt = ingest_dir / "old_bank.xlsx"
    old_stmt.write_text("dummy")
    # Change mod time of the old statement to ensure it's older
    os.utime(str(old_stmt), (time.time() - 100, time.time() - 100))
    
    # Create a newer bank statement
    new_stmt = ingest_dir / "new_bank.xlsx"
    new_stmt.write_text("dummy")
    
    invoice_file = ingest_dir / "invoice.pdf"
    invoice_file.write_text("dummy")
    
    env_vars = {k: str(v) for k, v in process_dirs.items()}
    env_vars["WORK_DIR"] = str(ingest_dir.parent)
    mocker.patch.dict(os.environ, env_vars)
    
    mock_ingest, mock_validate, mock_record = mock_pipeline
    
    def ingest_side_effect(path):
        json_path = process_dirs["INGESTED_DIR"] / f"{Path(path).stem}.json"
        json_path.write_text("{}")
    mock_ingest.side_effect = ingest_side_effect
    
    def validate_side_effect(json_path, bank_statement=None):
        # We'll assert the correct bank statement was passed here
        assert bank_statement == str(new_stmt)
        out_path = process_dirs["VALIDATED_DIR"] / f"{Path(json_path).stem}-validated.json"
        out_path.write_text("{}")
    mock_validate.side_effect = validate_side_effect
    
    result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    # verify it called validate
    mock_validate.assert_called_once()
    assert not invoice_file.exists()

def test_process_excludes_temp_excel_files(process_dirs, mock_pipeline, mocker):
    """Test process ignores files starting with ~$ when searching for bank statements."""
    ingest_dir = process_dirs["INGEST_DIR"]
    
    # Create a temp bank statement
    temp_stmt = ingest_dir / "~$bank_temp.xlsx"
    temp_stmt.write_text("dummy")
    
    # Create a real bank statement
    real_stmt = ingest_dir / "real_bank.xlsx"
    real_stmt.write_text("dummy")
    
    invoice_file = ingest_dir / "invoice.pdf"
    invoice_file.write_text("dummy")
    
    env_vars = {k: str(v) for k, v in process_dirs.items()}
    env_vars["WORK_DIR"] = str(ingest_dir.parent)
    mocker.patch.dict(os.environ, env_vars)
    
    mock_ingest, mock_validate, mock_record = mock_pipeline
    
    def ingest_side_effect(path):
        json_path = process_dirs["INGESTED_DIR"] / f"{Path(path).stem}.json"
        json_path.write_text("{}")
    mock_ingest.side_effect = ingest_side_effect
    
    def validate_side_effect(json_path, bank_statement=None):
        # We'll assert that the real statement was picked, NOT the temp one
        assert bank_statement == str(real_stmt)
        out_path = process_dirs["VALIDATED_DIR"] / f"{Path(json_path).stem}-validated.json"
        out_path.write_text("{}")
    mock_validate.side_effect = validate_side_effect
    
    result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    mock_validate.assert_called_once()
    assert not invoice_file.exists()
