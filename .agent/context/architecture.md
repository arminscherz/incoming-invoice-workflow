---
name: architecture-guidelines
description: "Rules for maintaining and developing the incoming invoice workflow"
activation: always_on
---

# Incoming Invoice Workflow Architecture Guidelines

This document outlines the architectural principles, design patterns, and coding standards for the 'ii-workflow' (incoming-invoice-workflow) project MVP (up to 20 invoices per batch). All developments must adhere to these rules to ensure maintainability, reliability, and the integrity of the data pipeline.

## 1. Core Philosophy: The Modular CLI Pipeline

The system is built as a set of loose-coupled CLI tools that can be chained together or orchestrated independently.

### 1.1 Invocation and Output

Every core functional command (`ingest`, `validate`, `record`) **MUST** be capable of receiving input and producing clean output.

- **Batch Processing:** Tools should process a batch of files at once. `ingest` submits files to the LLM in batch mode and polls for the results.
- **State Management:** Intermediate state is managed via text files (e.g., intermediate JSON files in the workspace). No database is used for the MVP.
- **Side Effects:** All logs, status messages, progress bars, and errors **MUST** be printed to `stderr` or written to log files.

### 1.2 Separation of Concerns

Functionality is divided into distinct phases. Do not mix these responsibilities in a single command unless it is an explicit "Orchestrator".

1. **Ingest (`ingest`):**
    - **Goal:** Ingest invoices.
    - **Inputs:**
        - File path to one invoice file (e.g. PDF, PNG)
    - **Tech:** batch llm (Gemini API with polling), Pydantic schemas for invoice data structure
    - **Outputs:**
        - File path to the extracted invoice data as intermediate JSON files.
2. **Validate (`validate`):**
    - **Goal:** Validate extracted data.
    - **Inputs:**
        - File path to the extracted invoice data as intermediate JSON files.
        - File path to a bank account data file (.xslx) for lookup of payments
    - **Tech:** Calculation, schema validation, regex, error flagging (moves failed files to ERROR_DIR).
    - **Output:**
        - File path to validated JSON invoice files.
3. **Record (`record`):**
    - **Goal:** Write data to CSV and check for duplicates.
    - **Inputs:**
        - File path to the validated invoice data as JSON files.
        - File path to the CSV file for data export
        - File path to the folder for invoice archiving
    - **Tech:** CSV standard library.
    - **Output:** Path to updated CSV. Moves source files to ARCHIVE_DIR.
4. **Orchestration (`process`):**
    - **Goal:** Combine steps 1-3 for multiple invoices (up to 20).
    - **Logic:**
        - Check the INGEST folder for invoice files
        - For each invoice file, execute steps 'Ingest', 'Validate' and 'Record'.
        - Move successfuly processed files to the ARCHIVE_DIR

## 2. Technology Stack Standards

- **Language:** Python 3.14+, setup with a virtual environment (at subdirectory venv), activate it with `source venv/bin/activate` before running any commands.
- **CLI Framework:** `typer` (with `Annotated` types)
- **Data Validation:** `pydantic` (integrates natively with Gemini structured output)
- **CSV processing:** `csv` standard library (pandas is not needed for CSVs).
- **Excel processing:** `openpyxl` library to read `.xlsx` bank account data files.
- **AI/LLM:** Google Gemini API (genai SDK). The API is called in batch mode, but the calling service waits for results (polling).
- **Logging:** `loguru` or `rich` for structured logging.

## 3. Directory Structure & Modules

- `ii_workflow/main.py`: **Only** CLI entry points and orchestration logic. Keep business logic out of here.
- `ii_workflow/ingest.py`: Ingest invoices via LLM batch processing.
- `ii_workflow/validate.py`: Validate extracted data.
- `ii_workflow/record.py`: Write data to CSV.

## 4. Error Handling & Exit Codes

CLI commands must return meaningful exit codes to allow orchestration scripts to react appropriately.

| Code | Meaning | Use Case |
| :--- | :--- | :--- |
| `0` | Success | Operation completed successfully. |
| `1` | Error | Critical failure (exception, network down, FS error). |
| `2` | Skipped | Valid execution but no data found. |
| `3` | Validation Error | Extraction failed or data is invalid. |

**Implementation:**
Use `raise typer.Exit(code=N)`.
Invoices triggering non-zero exits should be logged clearly and moved to `ERROR_DIR` for manual review.

## 5. Coding Standards

- **Type Hinting:** All functions must have Python type hints.
- **Path Handling:** Use `pathlib.Path` instead of `os.path` strings where possible.
- **Environment Variables:** Access secrets and config via `os.getenv` or `dotenv`. Do **not** hardcode API keys.
- **Logging:** Always use the central logging mechanism. Provide clear error logs as notifications are out of scope for the MVP.
- **Idempotency:** Ensure that commands can be re-run safely without duplicating data if a crash occurs (e.g., checking existing JSONs/CSV rows).

## 5. Test driven development

- **MOC concept**: Create a Mini Orange Concept (MOC) for each new feature. The MOC will be a markdown file that describes the feature and how it should be implemented. This MOC will be used to generate the test cases and the implementation code.
- Use `pytest` for unit, integration and functional testing.
- alle external dependencies (LLM, Filesystem) should be mocked using `pytest` and `pytest-mock`.
