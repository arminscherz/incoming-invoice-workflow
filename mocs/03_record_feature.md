# MOC: Record Feature

## Goal

Take a validated invoice JSON file and append its data to a master CSV record file, preventing duplicate entries.

## Functional Requirements

- **Inputs**:
  - `invoice_json`: The path to the validated JSON file (from `VALIDATED_DIR`). If the path is not fully qualified, resolve it relative to `VALIDATED_DIR`.
  - `--result_csv` (Optional): The filename or path of the result CSV file. Defaults to `invoices_record.csv`. If not fully qualified, resolve it relative to the current working directory.
- **Configuration**:
  - `RESULT_COLUMNS`: An environment variable specifying the columns to write to the CSV, formatted as JSON field names separated by `;` (e.g., `vendor_name;invoice_number;date;total_invoice_amount_gross`).
- **Data Validation & Duplicate Checking**:
  - Check if the entry already exists in the CSV to prevent duplicates.
  - A duplicate is defined by the combination of: `invoice_number`, `date`, and `vendor_name`.
  - If a duplicate is found, log a warning and exit without appending to the CSV.
- **Output**:
  - Appends the extracted JSON data to the target CSV file using `;` as the delimiter.
  - If the CSV file does not exist, it must be created with the header row matching the `RESULT_COLUMNS`.
  - Prints the absolute path of the CSV file to stdout.
- **Archiving**:
  - Archiving the original files and JSONs to `ARCHIVE_DIR` is **NOT** handled by this command. It will be handled by the orchestrator (`process` command).

## Implementation Details

- Command: `python -m ii_workflow.main record <invoice_json> [--result_csv <result_csv_path>]`
- Logic:
  1. Parse the JSON file into the `InvoiceData` model.
  2. Read the `RESULT_COLUMNS` from the environment.
  3. Check if the target CSV exists. If not, create it and write the headers.
  4. If it exists, read the existing rows to check for duplicates based on `invoice_number`, `date`, and `vendor_name`.
  5. If duplicate found -> log warning, exit with code 0 (so orchestrator knows it was successful, just a duplicate, and can archive it).
  6. If no duplicate -> append the row.
  7. Print absolute path to stdout.

## Testing Strategy

- Test 1: Successful creation of a new CSV file and appending the first record.
- Test 2: Successful appending to an existing CSV file.
- Test 3: Attempting to append a duplicate record -> aborted, no new row added.
- Test 4: Handling relative paths, `--result_csv` option, and missing `RESULT_COLUMNS` env var.
