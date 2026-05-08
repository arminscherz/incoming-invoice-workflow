# MOC: Validate Feature

## Goal

Validate the extracted invoice data (JSON) and cross-reference it with a bank account statement (`.xlsx`) to determine the payment method.

## Functional Requirements

- **Inputs**:
  - `invoice_json`: The path to the JSON file extracted by the ingest step. If not an absolute path, it should be resolved relative to the `INGEST_DIR` (from environment variables).
  - `--bank_statement` (Optional): The path to the bank statement `.xlsx` file. If provided and not an absolute path, it should also be resolved relative to the `INGEST_DIR`. If omitted, skip the bank lookup logic.
- **Output**:
  - The validated JSON file is saved to `VALIDATED_DIR`.
  - The full path to the written result file is printed to stdout.
  - Check that `total_invoice_amount_gross` equals `total_invoice_amount_net` + `total_invoice_amount_tax`.
  - Check that the sum of all VAT fields (`tax_amount_X_percent_VAT`) equals `total_invoice_amount_tax`.
  - **Tip Validation**: If `total_payment_amount_gross` is provided, the difference between it and `total_invoice_amount_gross` should match `tip_amount`. Log a warning if they differ.
  - **Net amounts for differrent tax-levels matches total net amount**: `total_invoice_amount_net` must match (+ / - 5 cents) the sum of `net_amount_0_percent_VAT`, `net_amount_10_percent_VAT`, `net_amount_13_percent_VAT`, and `net_amount_20_percent_VAT`.
- **Bank Lookup Logic (Heuristics)**:
  - Read the `.xlsx` file, skipping lines until the header row ('Valutadatum', 'Buchungsdatum', 'Betrag', 'Währung', 'Gegenpartei', 'Bezeichnung', 'Referenz', 'Nachricht', 'Zahlungs-ID').
  - Compare each transaction against the invoice:
    - Amount Match: Transaction 'Betrag' matches `total_payment_amount_gross` (fallback to `total_invoice_amount_gross`). Note: Bank statements usually have negative amounts for outgoing payments; ensure correct sign handling (absolute value).
    - Date Match: Invoice `date` is within +/- 3 days of transaction 'Valutadatum'.
    - Vendor Match: Any word/part of `vendor_name` (ignoring case) is present in 'Gegenpartei', 'Bezeichnung', or 'Nachricht'.
- **Outcome**:
  - If a match is found: Update `payment_method` in the JSON to `"Bankkonto"`.
  - If no match is found: Update `payment_method` in the JSON to `"bar"`.
  - If validation fails (e.g., math doesn't add up), log the error and return a non-zero exit code so the orchestrator can move it to the `ERROR_DIR`.
- **Tip to 0% VAT Allocation**:
  - After validations, if `tip_amount` > 0 and `tax_amount_0_percent_VAT` == 0, set `tax_amount_0_percent_VAT = tip_amount`.
  - Skip if `tip_amount` == 0 or if it already equals `tax_amount_0_percent_VAT`.
  - Log the update for transparency.

## Implementation Details

- Command: `python -m ii_workflow.main validate <invoice_json> [--bank_statement <bank_statement_path>]`
- Logic:
  1. Load and parse the JSON file into the `InvoiceData` model.
  2. Run the math validation checks (Gross vs Net+Tax, VAT sum).
  3. Perform tip validation (Calculated tip vs Extracted tip) if a payment amount exists.
  4. If `--bank_statement` is provided, load the `.xlsx` file using `openpyxl`.
  5. Iterate through transactions and apply the heuristic matching logic.
  6. Update the `InvoiceData.payment_method` field ("Bankkonto" or "bar").
  7. **Tip Allocation**: If `tip_amount` > 0 and `tax_amount_0_percent_VAT` is 0, update it to include the tip and log the change.
  8. Save the updated JSON to `VALIDATED_DIR` (as defined in `.env`), ensuring the directory exists.
  9. Print the absolute path of the output file to stdout.

## Testing Strategy

- Unit test: Mock `openpyxl` or provide a dummy `.xlsx` file for testing.
- Test 1: Successful math validation + Bank match found -> `payment_method == "Bankkonto"`.
- Test 2: Successful math validation + No bank match -> `payment_method == "bar"`.
- Test 3: Failed math validation (e.g., gross != net + tax) -> Error raised and non-zero exit code.
- Test 4: Tip Allocation -> If `tip_amount` is 5.0 and `tax_amount_0_percent_VAT` is 0, it should become 5.0 in the output.
- Test 5: Tip Allocation Skip -> If `tip_amount` is 5.0 and `tax_amount_0_percent_VAT` is already 5.0, no change/log.
