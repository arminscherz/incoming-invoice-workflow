# Concept: Incoming Invoice Processing Workflow

This purpose of this workflow is to automate the reception and filing of incoming invoices. It is designed as an MVP capable of processing up to 20 invoices per batch.

## High level idea

1. The invoices are expected to be stored as scanned images (e.g. PDFs, PNG) in the INGEST_DIR directory. Payment receipts may be provided together with the invoice in the same source image.
2. A LLM is called to ingest the scanned invoices & payment receipts and extract structured invoice data as a JSON.
3. Data is validated and accounting details are calculated. Invoices that fail validation or extraction are moved to an ERROR_DIR.
4. The extracted invoice data is used to search in a bank account data file (e.g. xlsx-Format) to see if the invoice is already paid.
5. The extracted data is stored as a CSV in the WORK_DIR directory. Duplicate checking is performed against the output CSV (e.g., matching Vendor and Invoice Number) to prevent double processing.
6. The successfully processed invoice files are moved to the ARCHIVE_DIR directory.

## Technical implementation

- The workflow is implemented in Python and called from the shell.
- The LLM (Google Gemini) is called in batch mode to reduce costs. The orchestrator submits the batch and polls for completion.
- Clear error logs are generated for observability.
- For more details see [architecture](./architecture.md).

## Folder structure

All folders are expected to be relative to the calling working directory.

- INGEST_DIR: Invoices to be processed
- ARCHIVE_DIR: Successfully processed invoices
- ERROR_DIR: Invoices that failed extraction or validation (Manual Review)
- WORK_DIR: Working directory for intermediate text/JSON files and the output CSV
- LOG_DIR: Logs

## Configuration

All configuration is done in the [.env](./../.env) file.
