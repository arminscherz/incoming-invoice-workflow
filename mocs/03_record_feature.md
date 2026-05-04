# MOC: Record Feature

## Goal
Write the validated invoice data to a CSV and archive the original invoice file.

## Implementation Details
- Command: `python -m ii-workflow.main record run <validated_json> <csv_file> <archive_dir>`
- Logic:
  1. Read the validated JSON.
  2. Check if the invoice already exists in the CSV (deduplication check).
  3. Append to CSV if not duplicated.
  4. Move the original source file to `archive_dir`.

## Testing Strategy
- Unit test: Use a temporary directory for the CSV and archive directory.
- Verify CSV appending functionality.
- Verify file move operation.
