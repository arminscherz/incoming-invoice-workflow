# MOC: ZUGFeRD / Factur-X Generation Feature

## Goal

Enable automated import of extracted & validated invoice data into accounting software (specifically BMD via the BMD "Eingangsrechnungs-Workflow"). This is accomplished by producing hybrid (PDF & XML) enhanced PDF files matching the ZUGFeRD / Factur-X standard. 

The **BASIC WL** (Basic Without Lines) profile is used because it includes header, footer, and invoice-level tax (VAT rate breakdowns) which maps perfectly to the fields of `InvoiceData`. Scanned image inputs (PNG, JPG, JPEG) must be automatically converted to PDF before embedding the XML.

## Functional Requirements

- **Schema Extension**: Extend the Pydantic schema `InvoiceData` in `ii_workflow/models.py` with:
  - `vendor_vat_id`: string (optional, UID/VAT number of the vendor, e.g., 'ATU12345678')
  - `customer_vat_id`: string (optional, UID/VAT number of the customer/buyer)
  - `customer_name`: string (optional, Name of the customer/buyer)
  - `vendor_address_street`: string (optional, Street of the vendor)
  - `vendor_address_zip`: string (optional, Postal code of the vendor)
  - `vendor_address_city`: string (optional, City of the vendor)
  - `vendor_address_country`: string (optional, 2-letter country code of the vendor, defaults to 'AT')
  - `payment_reference`: string (optional, structured payment reference)

- **Gemini Prompts**: Update the Gemini extraction guidelines in `ii_workflow/ingest.py` to extract these additional fields.

- **Image Conversion**: If the input scan is an image (`.png`, `.jpg`, `.jpeg`), convert it to a PDF page using `Pillow` before embedding the XML.

- **ZUGFeRD/Factur-X Generation**:
  - Build the UN/CEFACT Cross Industry Invoice (CII) XML for the `BASIC WL` profile.
  - Embed the XML into the PDF as an attachment named `factur-x.xml` with `Alternative` relationship using the `factur-x` python package (`facturx.generate_from_file`).
  - Output file is named `<scan_stem>.pdf` (always PDF/A-3 hybrid file) and moved directly to the archive-folder (instead of the original input scan-file).

- **Error Handling**:
  - If ZUGFeRD generation fails, log the error clearly and raise `typer.Exit(code=3)`.
  - The orchestrator will catch this, print an error log, and move the original scan file to the `ERROR_DIR` (existing error workflow).

## Implementation Details

### Integrate into 'Record' Step
The ZUGFeRD/Factur-X generation is integrated directly into the existing `record` command.
- CLI Command: `python -m ii_workflow.main record <validated_json> --result_csv <csv_path> --scan_file <scan_path> --scan_archive_dir <archive_dir>`
- Logic inside `record_run`:
  1. Load `validated_json` into `InvoiceData` model and append the record to CSV.
  2. If `scan_file` and `scan_archive_dir` are provided:
     a. If `scan_file` is an image (`.png`, `.jpg`, `.jpeg`), convert it to a temporary PDF using `Pillow`.
     b. Generate the XML bytes conforming to the `urn:factur-x.eu:1p0:basicwl` profile.
     c. Call `facturx.generate_from_file` to embed the XML.
     d. Validate XML automatically via XSD/Schematron checks built into the `factur-x` library.
     e. Save the resulting hybrid ZUGFeRD PDF file directly into `scan_archive_dir / <scan_stem>.pdf`.
     f. Clean up/delete the original input `scan_file` (if it was successfully archived as the hybrid PDF).

### Orchestrator Step
- Updates inside `ii_workflow/process.py`:
  - Call `record_run(str(validated_json), result_csv=result_csv, scan_file=str(scan_file), scan_archive_dir=str(scan_archive_dir))` in Step 3.
  - In the archiving/cleanup logic of `process.py`, only archive/move `scan_file` if it still exists (which it won't if `record_run` successfully generated and archived the hybrid PDF). If the file still exists (e.g. because ZUGFeRD was skipped or not run), use the standard fallback behavior.

## Testing Strategy

- **Schema Check**: Verify Pydantic model can parse new fields.
- **XML Structure Check**: Validate that generated XML contains correct namespaces, vendor/customer UIDs, currency, VAT breakdowns, and monetary sums.
- **XSD Validation**: Ensure generated XML passes the built-in XSD validator (`facturx.xml_check_xsd(xml_bytes, level='basicwl')`).
- **Integration Test**: Mock Gemini responses, run orchestrator with image and PDF inputs, and verify that the final archived files in the archive folder are valid hybrid PDFs containing `factur-x.xml`.
