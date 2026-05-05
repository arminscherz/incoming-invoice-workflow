# MOC: Process Feature

## Goal

Automate the end-to-end invoice workflow by orchestrating the `ingest`, `validate`, and `record` steps for all invoice files found in the ingestion directory. Handle archiving of successful files and segregation of failed files.

## Functional Requirements

- **Inputs**:
  - Automatically scans the `INGEST_DIR` (from `.env`) for all supported files (e.g., PDF, PNG, JPG).
  - Automatically scans the `INGEST_DIR` (from `.env`) for a `.xlsx` file. If no `.xlsx` file is found, the `--bank_statement` argument needs to be provided. **Note**: Files starting with `~$` (Excel temporary files) are ignored.
  - If multiple `.xlsx` files are found, the youngest one is selected, and a warning is logged.
  - `--bank_statement` (Optional): Path to a bank statement file to be passed down to the `validate` step. If provided, the value overrides any `.xlsx` file found in the `INGEST_DIR`.
  - `--result_csv` (Optional): Path to the target CSV file, passed down to the `record` step (defaults to `invoices_record.csv`).
- **Orchestration Logic**:
  - For each file in `INGEST_DIR`:
    1. **Ingest**: Call the `ingest` logic on the file. If it fails, move the source file to `ERROR_DIR` and skip to the next file.
    2. **Validate**: Call the `validate` logic on the resulting JSON from `INGESTED_DIR`. If it fails (e.g., bad math), move the source file to `ERROR_DIR` and skip.
    3. **Record**: Call the `record` logic on the resulting JSON from `VALIDATED_DIR`. If it fails, move the source file to `ERROR_DIR` and skip. (Note: A duplicate entry returns exit code 0, so it counts as a success).
    4. **Archiving**: Archive the processed files:
    - JSON files from `INGESTED_DIR` and `VALIDATED_DIR` to `JSON_ARCHIVE_DIR`.
    - Scan (.pdf, .png, .jpg, etc.) files from `INGESTED_DIR` to `SCAN_ARCHIVE_DIR`. If one of the processing steps fails, the scan file is moved to `ERROR_DIR` and not archived.
- **Error Handling**:
  - The script must not crash if a single file fails. It should log the error, move the failing scan file to `ERROR_DIR`, and continue processing the remaining files.

## Implementation Details

- Command: `python -m ii_workflow.main process [--bank_statement <path>] [--result_csv <path>]`
- Logic:
  - Directly calls the Python functions (`ingest_run`, `validate_run`, `record_run`) for better performance and easier error handling.
  - Ensure all directories (`INGEST_DIR`, `INGESTED_DIR`, `VALIDATED_DIR`, `JSON_ARCHIVE_DIR`, `SCAN_ARCHIVE_DIR`, `ERROR_DIR`) exist before starting. (Creates the directories if they don't exist)
  - Loop through files in `INGEST_DIR`.
  - Use `try...except` blocks around the function calls. Since the functions currently raise `typer.Exit(code=1)` on failure, the orchestrator needs to catch these `typer.Exit` exceptions to handle the routing to `ERROR_DIR` or `SCAN_ARCHIVE_DIR`.

## Testing Strategy

- Test 1: Full successful run on a valid file (Ingest -> Validate -> Record -> Move scan files to SCAN_ARCHIVE_DIR, json files to JSON_ARCHIVE_DIR).
- Test 2: Ingest failure (e.g., unsupported format) -> Move scan file to ERROR_DIR.
- Test 3: Validate failure (e.g., invalid math) -> Move scan file to ERROR_DIR.
- Test 4: Record handling of duplicate -> File is still moved to SCAN_ARCHIVE_DIR because it was processed successfully.
- Test 5: Multiple bank statements -> Youngest is picked, warning logged.
- Test 6: Excel temporary files (`~$*.xlsx`) -> Ignored during bank statement auto-detection.
