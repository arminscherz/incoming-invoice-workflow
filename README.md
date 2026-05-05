# Incoming Invoice Workflow

Automate the reception, analysis, and accounting of incoming invoices & payment receipts with ease. This project provides a robust, modular CLI pipeline designed for processing batches of invoices using AI/OCR capabilities (e.g. Google Gemini).

## 🚀 Overview

The **Incoming Invoice Workflow** (ii-workflow) streamlines the transition from raw invoice & payment receipt files (e.g. PDFs, PNGs) to structured, validated accounting records. It leverages a modular architecture to ingest data, validate it against bank records, and archive the results.

### Key Features

- **AI-Powered Extraction:** Uses Google Gemini to extract structured JSON data from scanned invoices & payment receipts. Token usage is minimized by using batch mode.
- **Robust Validation:** Implements Pydantic schemas for strict data integrity.
- **Payment Verification:** Automatically checks bank statement data (in '.xlsx' format) to identify paid invoices.
- **Idempotent Processing:** Prevents duplicate entries by matching Vendor and Invoice Numbers.
- **Modular CLI:** Each step (`ingest`, `validate`, `record`) can be run independently or via the main orchestrator.
- **TDD Backed:** Developed using Mini Orange Concepts (MOCs) and comprehensive `pytest` suites.

## 🏗 Architecture

The workflow follows a 3-step pipeline:

1. **Ingest:** Scans the `INGEST_DIR` for invoices and uses Gemini LLM to generate intermediate JSON data in `INGESTED_DIR`.
2. **Validate:** Validates extracted data from `INGESTED_DIR`, performs bank account lookups, and saves the result to `VALIDATED_DIR`.
3. **Record:** Appends validated data from `VALIDATED_DIR` to a master CSV and moves files to the `ARCHIVE_DIR`.

Failures at any stage are moved to the `ERROR_DIR` for manual review, ensuring no invoice is lost.

## 🛠 Tech Stack

- **Language:** Python 3.11+
- **CLI:** [Typer](https://typer.tiangolo.com/)
- **Data Validation:** [Pydantic v2](https://docs.pydantic.dev/)
- **AI/LLM:** Google Gemini API (`google-genai`)
- **Excel/CSV:** `openpyxl`, `csv` (standard library)
- **Logging:** `loguru`

## ⚙️ Setup & Installation

### Prerequisites

- Python 3.11 or higher.
- A Google Gemini API Key.

### Installation

1. **Clone the repository:**

    ```bash
    git clone https://github.com/arminscherz/incoming-invoice-workflow.git
    cd incoming-invoice-workflow
    ```

2. **Create and activate a virtual environment:**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3. **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

### Configuration

Create a `.env` file in the root directory based on the project requirements:

```env
# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here

# Directory Configuration
INGEST_DIR=ingest
INGESTED_DIR=ingested
VALIDATED_DIR=validated
ARCHIVE_DIR=archive
SCAN_ARCHIVE_DIR=archive/scans
JSON_ARCHIVE_DIR=archive/jsons
ERROR_DIR=error

# Record Configuration (Semicolon separated JSON keys)
RESULT_COLUMNS=vendor_name;invoice_number;date;purchase_category;total_invoice_amount_gross;currency;payment_method
```

## 📖 Usage

The workflow can be executed as a full process or in individual steps.

### activate virtual environment

source venv/bin/activate  # On Windows: venv\Scripts\activate

### Main Orchestrator

Process all invoices in the ingest directory. It automatically chains `ingest`, `validate`, and `record` for each file.

```bash
python -m ii_workflow.main process [--bank_statement PATH] [--result_csv FILENAME]
```

*   **Auto-detection:** If no `--bank_statement` is provided, it automatically scans `INGEST_DIR` for `.xlsx` files and picks the newest one.
*   **Archiving:** Successful runs move scans to `SCAN_ARCHIVE_DIR` and JSONs to `JSON_ARCHIVE_DIR`. Failures move the scan file to `ERROR_DIR`.

### Individual Steps

For fine-grained control:

- **Ingest Invoices:**

  ```bash
  python -m ii_workflow.main ingest [PATH_TO_INVOICE]
  ```

  *Note: The command prints the absolute path of the generated result file to stdout. (for piping to other tools)*

- **Validate Data:**

  ```bash
  python -m ii_workflow.main validate [PATH_TO_JSON] --bank_statement [PATH_TO_BANK_STATEMENT]
  ```

  *Note: The `--bank_statement` is optional. If paths are not fully qualified, the JSON is resolved relative to `INGESTED_DIR` and the bank statement relative to `INGEST_DIR`. The command prints the absolute path of the generated result file to stdout.*

- **Record Results:**

  ```bash
  python -m ii_workflow.main record [PATH_TO_JSON] --result_csv [PATH_TO_RESULT_CSV_FILE]
  ```

## 📂 Project Structure

```text
.
├── .agent/              # Agent context and MOCs
├── ii_workflow/         # Main package
│   ├── ingest.py        # LLM extraction logic
│   ├── validate.py      # Validation & Bank lookup
│   ├── record.py        # CSV writing & Archiving
│   ├── models.py        # Pydantic schemas
│   └── main.py          # CLI entry point
├── tests/               # Pytest suite
├── requirements.txt     # Dependencies
└── README.md            # This file
```

## 🧪 Testing

The project uses `pytest` for automated testing.

Run all tests:

```bash
pytest
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
