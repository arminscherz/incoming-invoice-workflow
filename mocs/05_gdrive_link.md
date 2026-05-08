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
- **Configuration**:
  - `GDRIVE_OAUTH_CLIENT_ID`: OAuth 2.0 Client ID (from .env).
  - `GDRIVE_OAUTH_CLIENT_KEY`: OAuth 2.0 Client Secret (from .env).
  - `GDRIVE_TOKEN_JSON`: Path to store the authorized token (default: `token.json`).
  - `gdrive_link` is already added to `RESULT_COLUMNS`.

## Implementation Details

- **Dependencies**: Add `google-api-python-client` and `google-auth` to `requirements.txt`.
- **Logic**:
  1. Initialize the Google Drive service using `GDRIVE_OAUTH_CLIENT_ID` and `GDRIVE_OAUTH_CLIENT_KEY`.
  2. Perform OAuth flow (browser-based for first run, then cached in `token.json`).
  3. Search for the file: `q="name = 'filename.pdf' and trashed = false"`.
  4. Fetch fields: `files(id, name, webViewLink)`.
  5. If found, set `invoice.gdrive_link = file['webViewLink']`.

## Testing Strategy

- **Mocking**: Mock the `googleapiclient.discovery.build` service and the `.files().list().execute()` chain.
- **Scenario 1**: File found on GDrive -> Link is added to JSON and CSV.
- **Scenario 2**: File not found on GDrive -> `gdrive_link` remains `None`, process continues without error.
- **Scenario 3**: API Error -> Log warning, continue process (don't fail the whole ingestion just because of a link).
