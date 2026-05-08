# MOC: Process Summary Overview

Provide a summary overview of all processed invoices at the end of a `process` run to improve observability.

## Goal

At the end of each `process` run, the orchestrator should output a summarized list of results for all invoices processed in that batch. This allows the user to quickly see which invoices succeeded, which had warnings, and which failed.

## Implementation Details

### 1. Status Definitions

Each invoice result will be categorized into one of three statuses:

- **SUCCESS**:
  - All steps (`ingest`, `validate`, `record`) completed with exit code 0.
  - `gdrive_link` is present and non-empty in the final record.
  - If a bank statement was provided, a match was found (i.e., `payment_method` is "Bankkonto").
  - No significant validation warnings (like math recalculations or tip mismatches).
- **WARNING**:
  - The invoice was successfully recorded (`record` step succeeded).
  - BUT one or more of the following occurred:
    - `gdrive_link` is missing or empty.
    - `payment_method` is "bar" despite a bank statement being provided (lookup failed).
    - Validation warnings were logged (e.g., partial keyword match for bank txn).
- **ERROR**:
  - Any of the steps (`ingest`, `validate`, `record`) failed (non-zero exit code) or an unexpected exception occurred.
  - Log out which step failed and why.
  - The invoice scan was moved to `ERROR_DIR`.

### 2. Logic in `ii_workflow/process.py`

- Initialize an empty list `execution_results` before the loop.
- Inside the loop, track the status of each invoice.
- After the loop, iterate over `execution_results` and print a summary table using `logger.info`.
- Format: `[STATUS] invoice_file.name - Reason (if any)`

### 3. Data Extraction for Summary

To determine if a successful run is a "WARNING", the orchestrator will:

- Check if `gdrive_link` is empty in the `validated_json`.
- Check if `payment_method` is "bar" while `resolved_bank_stmt` was present.

## Testing Strategy

### 1. Mocking

- Mock `ingest_run`, `validate_run`, and `record_run` in `tests/test_process.py`.
- Create tests for:
  - All steps success -> Status: SUCCESS.
  - Record success, but missing GDrive link -> Status: WARNING.
  - Record success, but bank lookup failed (if bank stmt provided) -> Status: WARNING.
  - Any step failure -> Status: ERROR.

### 2. Assertions

- Verify that the summary log message contains the expected number of SUCCESS, WARNING, and ERROR lines.
- Verify the specific status for each mocked invoice filename.

## Exit Codes

- No changes to existing exit codes. The summary is for informational purposes in the logs.
