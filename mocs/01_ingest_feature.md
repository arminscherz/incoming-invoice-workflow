# MOC: Ingest Feature

## Goal

Ingest invoice images (PDF, PNG) and extract structured JSON data using the Google Gemini API in batch mode with polling.

## Functional Requirements

- **Extraction Schema**:
  - `vendor_name`: string
  - `invoice_number`: string
  - `date`: string (ISO 8601)
  - `total_amount`: float
  - `tax_amount_0_percent_VAT`: float
  - `tax_amount_10_percent_VAT`: float
  - `tax_amount_13_percent_VAT`: float
  - `tax_amount_20_percent_VAT`: float
  - `currency`: string (3-letter code)
  - `iban`: string (optional)
- **Batching**: The CLI command `ingest run` will take a single file path for the MVP. The `process` orchestrator will loop through files in `INGEST_DIR`.
- **Polling**: Use a 10-second interval for checking batch completion status.

## Implementation Details

- Command: `python -m ii_workflow.main ingest run <invoice_path>`
- Logic:
  1. Validate that the input file exists and is a supported format.
  2. Instantiate the `google-genai` client.
  3. Define a Pydantic model for the `InvoiceData` schema.
  4. Submit the invoice file to the Gemini model (e.g., `gemini-2.0-flash`) using structured output.
  5. Wait/Poll for the response.
  6. Save the output as a JSON file in `WORK_DIR`.

## Testing Strategy

- Unit test: Mock `google.genai.Client`.
- Verify that `ingest_run` creates the expected JSON file with correct field values.
- Verify exit codes for file-not-found or API errors.
