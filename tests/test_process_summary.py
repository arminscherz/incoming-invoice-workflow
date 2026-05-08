import os
import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
import typer
from ii_workflow.main import app
from loguru import logger

runner = CliRunner()

@pytest.fixture(autouse=True)
def caplog_loguru(caplog):
    """Fixture to let loguru output to caplog."""
    handler_id = logger.add(caplog.handler, format="{message}")
    yield
    logger.remove(handler_id)

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

def test_summary_all_success(process_dirs, mock_pipeline, mocker, caplog):
    """Test that summary shows SUCCESS when all steps pass perfectly."""
    ingest_dir = process_dirs["INGEST_DIR"]
    (ingest_dir / "inv1.pdf").write_text("dummy")
    
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
        # SUCCESS condition: has gdrive_link
        with open(out_path, "w") as f:
            json.dump({"vendor_name": "Test", "gdrive_link": "http://gdrive/1"}, f)
    mock_validate.side_effect = validate_side_effect
    
    with caplog.at_level("INFO"):
        result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    assert "[SUCCESS] inv1.pdf" in caplog.text

def test_summary_warning_no_gdrive(process_dirs, mock_pipeline, mocker, caplog):
    """Test that summary shows WARNING when GDrive link is missing."""
    ingest_dir = process_dirs["INGEST_DIR"]
    (ingest_dir / "inv2.pdf").write_text("dummy")
    
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
        # WARNING condition: missing gdrive_link
        with open(out_path, "w") as f:
            json.dump({"vendor_name": "Test", "gdrive_link": None}, f)
    mock_validate.side_effect = validate_side_effect
    
    with caplog.at_level("INFO"):
        result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    assert "[WARNING] inv2.pdf" in caplog.text
    assert "Missing GDrive link" in caplog.text

def test_summary_error_ingest_failure(process_dirs, mock_pipeline, mocker, caplog):
    """Test that summary shows ERROR when ingest fails."""
    ingest_dir = process_dirs["INGEST_DIR"]
    (ingest_dir / "inv_bad.pdf").write_text("dummy")
    
    env_vars = {k: str(v) for k, v in process_dirs.items()}
    env_vars["WORK_DIR"] = str(ingest_dir.parent)
    mocker.patch.dict(os.environ, env_vars)
    
    mock_ingest, mock_validate, mock_record = mock_pipeline
    mock_ingest.side_effect = typer.Exit(code=1)
    
    with caplog.at_level("INFO"):
        result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    assert "[ERROR] inv_bad.pdf" in caplog.text
    assert "Step: Ingest" in caplog.text

def test_summary_mixed_results(process_dirs, mock_pipeline, mocker, caplog):
    """Test summary with a mix of SUCCESS, WARNING, and ERROR."""
    ingest_dir = process_dirs["INGEST_DIR"]
    (ingest_dir / "inv_ok.pdf").write_text("dummy")
    (ingest_dir / "inv_warn.pdf").write_text("dummy")
    (ingest_dir / "inv_err.pdf").write_text("dummy")
    
    env_vars = {k: str(v) for k, v in process_dirs.items()}
    env_vars["WORK_DIR"] = str(ingest_dir.parent)
    mocker.patch.dict(os.environ, env_vars)
    
    mock_ingest, mock_validate, mock_record = mock_pipeline
    
    def ingest_side_effect(path):
        if "inv_err" in path:
            raise typer.Exit(code=1)
        json_path = process_dirs["INGESTED_DIR"] / f"{Path(path).stem}.json"
        json_path.write_text("{}")
    mock_ingest.side_effect = ingest_side_effect
    
    def validate_side_effect(json_path, bank_statement=None):
        out_path = process_dirs["VALIDATED_DIR"] / f"{Path(json_path).stem}-validated.json"
        if "inv_warn" in json_path:
            with open(out_path, "w") as f:
                json.dump({"vendor_name": "Test", "gdrive_link": ""}, f)
        else:
            with open(out_path, "w") as f:
                json.dump({"vendor_name": "Test", "gdrive_link": "http://gdrive/ok"}, f)
    mock_validate.side_effect = validate_side_effect
    
    with caplog.at_level("INFO"):
        result = runner.invoke(app, ["process"])
    
    assert result.exit_code == 0
    assert "[SUCCESS] inv_ok.pdf" in caplog.text
    assert "[WARNING] inv_warn.pdf" in caplog.text
    assert "[ERROR] inv_err.pdf" in caplog.text
