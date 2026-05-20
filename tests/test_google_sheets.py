import os
import pytest
from unittest.mock import Mock, patch
from googleapiclient.errors import HttpError
from ii_workflow.record import check_google_sheet_duplicate

def test_check_duplicate_missing_spreadsheet_id(mocker):
    """Test that check returns False when GOOGLE_SPREADSHEET_ID is missing."""
    mocker.patch.dict(os.environ, {}, clear=True)
    if "GOOGLE_SPREADSHEET_ID" in os.environ:
        del os.environ["GOOGLE_SPREADSHEET_ID"]
        
    result = check_google_sheet_duplicate("INV-100", "2026-05-04", "Vendor X")
    assert result is False

def test_check_duplicate_failed_credentials(mocker):
    """Test that check returns False when credentials retrieval fails."""
    mocker.patch.dict(os.environ, {"GOOGLE_SPREADSHEET_ID": "dummy-id"})
    mocker.patch("ii_workflow.ingest.get_google_credentials", return_value=None)
    
    result = check_google_sheet_duplicate("INV-100", "2026-05-04", "Vendor X")
    assert result is False

def test_check_duplicate_api_error(mocker):
    """Test that check returns False and logs error when Sheets API call fails."""
    mocker.patch.dict(os.environ, {"GOOGLE_SPREADSHEET_ID": "dummy-id"})
    mocker.patch("ii_workflow.ingest.get_google_credentials", return_value=Mock())
    
    mock_build = mocker.patch("googleapiclient.discovery.build")
    mock_build.side_effect = Exception("API connection failed")
    
    result = check_google_sheet_duplicate("INV-100", "2026-05-04", "Vendor X")
    assert result is False

def test_check_duplicate_empty_sheet(mocker):
    """Test that check returns False when the sheet values are empty."""
    mocker.patch.dict(os.environ, {"GOOGLE_SPREADSHEET_ID": "dummy-id"})
    mocker.patch("ii_workflow.ingest.get_google_credentials", return_value=Mock())
    
    mock_build = mocker.patch("googleapiclient.discovery.build")
    mock_service = mock_build.return_value
    mock_service.spreadsheets().values().get().execute.return_value = {"values": []}
    
    result = check_google_sheet_duplicate("INV-100", "2026-05-04", "Vendor X")
    assert result is False

def test_check_duplicate_missing_required_headers(mocker):
    """Test that check returns False when required headers are missing in sheet."""
    mocker.patch.dict(os.environ, {"GOOGLE_SPREADSHEET_ID": "dummy-id"})
    mocker.patch("ii_workflow.ingest.get_google_credentials", return_value=Mock())
    
    mock_build = mocker.patch("googleapiclient.discovery.build")
    mock_service = mock_build.return_value
    # Missing 'invoice_number'
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            ["date", "vendor_name", "total_amount"]
        ]
    }
    
    result = check_google_sheet_duplicate("INV-100", "2026-05-04", "Vendor X")
    assert result is False

def test_check_duplicate_not_found(mocker):
    """Test that check returns False when no matching row is found in sheet."""
    mocker.patch.dict(os.environ, {"GOOGLE_SPREADSHEET_ID": "dummy-id"})
    mocker.patch("ii_workflow.ingest.get_google_credentials", return_value=Mock())
    
    mock_build = mocker.patch("googleapiclient.discovery.build")
    mock_service = mock_build.return_value
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            ["invoice_number", "date", "vendor_name"],
            ["INV-200", "2026-05-05", "Vendor Y"],
            ["INV-300", "2026-05-06", "Vendor Z"]
        ]
    }
    
    result = check_google_sheet_duplicate("INV-100", "2026-05-04", "Vendor X")
    assert result is False

def test_check_duplicate_found_exact(mocker):
    """Test that check returns True when exact duplicate matching vendor, invoice, and date exists."""
    mocker.patch.dict(os.environ, {"GOOGLE_SPREADSHEET_ID": "dummy-id"})
    mocker.patch("ii_workflow.ingest.get_google_credentials", return_value=Mock())
    
    mock_build = mocker.patch("googleapiclient.discovery.build")
    mock_service = mock_build.return_value
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            ["invoice_number", "date", "vendor_name"],
            ["INV-100", "2026-05-04", "Vendor X"], # Match!
            ["INV-300", "2026-05-06", "Vendor Z"]
        ]
    }
    
    result = check_google_sheet_duplicate("INV-100", "2026-05-04", "Vendor X")
    assert result is True

def test_check_duplicate_date_normalization(mocker):
    """Test that check handles date normalization correctly (e.g. DD.MM.YYYY vs ISO YYYY-MM-DD)."""
    mocker.patch.dict(os.environ, {"GOOGLE_SPREADSHEET_ID": "dummy-id"})
    mocker.patch("ii_workflow.ingest.get_google_credentials", return_value=Mock())
    
    mock_build = mocker.patch("googleapiclient.discovery.build")
    mock_service = mock_build.return_value
    mock_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            ["invoice_number", "date", "vendor_name"],
            ["INV-100", "04.05.2026", "Vendor X"], # DD.MM.YYYY date, should match 2026-05-04
            ["INV-300", "2026-05-06", "Vendor Z"]
        ]
    }
    
    result = check_google_sheet_duplicate("INV-100", "2026-05-04", "Vendor X")
    assert result is True
