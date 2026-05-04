# MOC: Validate Feature

## Goal
Validate the extracted invoice data and check a bank account `.xlsx` file to see if the invoice is already paid.

## Implementation Details
- Command: `python -m ii-workflow.main validate run <invoice_json> <bank_data.xlsx>`
- Logic:
  1. Load JSON file and validate against the Pydantic model.
  2. Load `.xlsx` file using `openpyxl`.
  3. Check if the invoice number / vendor combination exists in the bank data.
  4. If validation fails or already paid, exit with code 3.
  5. Otherwise, output `<invoice_name>_validated.json`.

## Testing Strategy
- Unit test: Mock file reading. Provide a dummy `.xlsx` file structure.
- Assert correct exit codes for paid vs. unpaid invoices.
- Assert validation errors trigger exit code 3.
