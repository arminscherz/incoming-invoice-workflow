# MOC: Google Drive Link Feature

## Goal

Add a Google Drive `webViewLink` to the extracted invoice data and include it in the final recording CSV. This allows the user to quickly access the original scan document from the spreadsheet.

## Functional Requirements

- **Model Update**: 
  - Add `gdrive_link: Optional[str] = None` to the `InvoiceData` model in `ii_workflow/models.py`.
- **Google Drive Integration**:
  - Use the Google Drive API (v3) to search for the file by name.
  - Since the directories are synced, we assume the file name in the `INGEST_DIR` (or eventually `SCAN_ARCHIVE_DIR`) corresponds to the file on Google Drive.
  - The search should be scoped to a specific folder if possible, or just by filename if the filename is unique.
- **Link Capture**:
  - In `ii_workflow/ingest.py`, after the Gemini extraction, perform a lookup on Google Drive.
  - If a matching file is found, retrieve its `webViewLink` and add it to the `InvoiceData` object.
- **Recording**:
  - Update `ii_workflow/record.py` to support the `gdrive_link` column.
  - Update the `.env` default `RESULT_COLUMNS` to include `gdrive_link`.
- **Configuration & Authorization**:
  - **Option 1: Service Account (Recommended)**:
    - `GDRIVE_SERVICE_ACCOUNT_JSON`: Path to service account key file (default: `service_account.json`).
    - The key file is resolved relative to the working directory (`WORK_DIR` or `cwd`), keeping credentials outside of the git source tree.
    - **Creation**: Create Service Account in GCP (`IAM & Admin` > `Service Accounts`), download JSON key as `service_account.json` into working directory. Ensure Drive API and Sheets API are enabled.
    - **Sharing**: Share both the Google Sheet (`GOOGLE_SPREADSHEET_ID`) and the Google Drive invoice folder (`INGEST_DIR` / `Eingang`) with the Service Account email (`Viewer` access).
    - Provides permanent, non-expiring credentials with zero interactive browser prompts.
  - **Option 2: OAuth 2.0 User Credentials (Fallback)**:
    - `GDRIVE_OAUTH_CLIENT_ID`: OAuth 2.0 Client ID (from .env).
    - `GDRIVE_OAUTH_CLIENT_KEY`: OAuth 2.0 Client Secret (from .env).
    - `GDRIVE_TOKEN_JSON`: Path to store the authorized token (default: `token.json` in working directory).
    - Refreshed tokens are saved back to disk to persist renewals.
  - `gdrive_link` is included in `RESULT_COLUMNS`.

## Implementation Details

- **Dependencies**: Add `google-api-python-client` and `google-auth` to `requirements.txt`.
- **Logic**:
  1. Initialize the Google credentials via `get_google_credentials()` in `ii_workflow/ingest.py`:
     - Checks working directory for `service_account.json` (or `GDRIVE_SERVICE_ACCOUNT_JSON` / `GOOGLE_APPLICATION_CREDENTIALS`).
     - If not found, falls back to OAuth 2.0 client config and loads/refreshes `token.json` in the working directory.
  2. Build the Drive service (`build("drive", "v3", credentials=creds)`).
  3. Search for the file: `q="name = 'filename.pdf' and trashed = false"`.
  4. Fetch fields: `files(id, name, webViewLink)`.
  5. If found, set `invoice.gdrive_link = file['webViewLink']`.

## Testing Strategy

- **Mocking**: Mock the `googleapiclient.discovery.build` service and the `.files().list().execute()` chain.
- **Scenario 1**: File found on GDrive -> Link is added to JSON and CSV.
- **Scenario 2**: File not found on GDrive -> `gdrive_link` remains `None`, process continues without error.
- **Scenario 3**: API Error -> Log warning, continue process (don't fail the whole ingestion just because of a link).
