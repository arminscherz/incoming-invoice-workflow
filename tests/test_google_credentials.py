import os
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from ii_workflow.ingest import get_google_credentials

def test_get_google_credentials_service_account_in_work_dir(tmp_path, mocker):
    """Test loading credentials from service_account.json in WORK_DIR."""
    sa_file = tmp_path / "service_account.json"
    sa_file.write_text('{"type": "service_account"}')
    
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path)
    }, clear=True)
    
    mock_from_file = mocker.patch("google.oauth2.service_account.Credentials.from_service_account_file")
    mock_sa_creds = Mock()
    mock_from_file.return_value = mock_sa_creds

    creds = get_google_credentials()
    assert creds == mock_sa_creds
    mock_from_file.assert_called_once_with(str(sa_file), scopes=[
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ])

def test_get_google_credentials_service_account_custom_env_in_work_dir(tmp_path, mocker):
    """Test loading credentials via GDRIVE_SERVICE_ACCOUNT_JSON relative to WORK_DIR."""
    sa_file = tmp_path / "my_custom_sa.json"
    sa_file.write_text('{"type": "service_account"}')
    
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path),
        "GDRIVE_SERVICE_ACCOUNT_JSON": "my_custom_sa.json"
    }, clear=True)
    
    mock_from_file = mocker.patch("google.oauth2.service_account.Credentials.from_service_account_file")
    mock_sa_creds = Mock()
    mock_from_file.return_value = mock_sa_creds

    creds = get_google_credentials()
    assert creds == mock_sa_creds
    mock_from_file.assert_called_once_with(str(sa_file), scopes=[
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ])

def test_get_google_credentials_missing_keys(tmp_path, mocker):
    """Test returning None when no Service Account and no OAuth client keys exist."""
    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path)
    }, clear=True)

    creds = get_google_credentials()
    assert creds is None

def test_get_google_credentials_oauth_refresh_persisted_in_work_dir(tmp_path, mocker):
    """Test that a refreshed OAuth token in WORK_DIR is updated."""
    token_file = tmp_path / "token.json"
    token_file.write_text('{"token": "old-token"}')

    mocker.patch.dict(os.environ, {
        "WORK_DIR": str(tmp_path),
        "GDRIVE_OAUTH_CLIENT_ID": "dummy-id",
        "GDRIVE_OAUTH_CLIENT_KEY": "dummy-key",
        "GDRIVE_TOKEN_JSON": "token.json"
    }, clear=True)

    mock_creds = Mock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "valid-refresh-token"
    mock_creds.to_json.return_value = '{"token": "refreshed-token"}'

    mocker.patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=mock_creds)

    creds = get_google_credentials()
    assert creds == mock_creds
    mock_creds.refresh.assert_called_once()
    assert token_file.read_text() == '{"token": "refreshed-token"}'
