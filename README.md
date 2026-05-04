# Incoming Invoice Workflow

Automate the reception, analysis, and accounting of incoming invoices with ease. This project provides a robust, modular CLI pipeline designed for processing batches of invoices (up to 20 per batch) using Google Gemini's advanced LLM capabilities.

## 🚀 Overview

The **Incoming Invoice Workflow** (ii-workflow) streamlines the transition from raw invoice files (PDFs, PNGs) to structured, validated accounting records. It leverages a modular architecture to ingest data, validate it against bank records, and archive the results.

### Key Features

- **AI-Powered Extraction:** Uses Google Gemini (via Batch mode) to extract structured JSON data from scanned invoices.
- **Robust Validation:** Implements Pydantic schemas for strict data integrity.
- **Payment Verification:** Automatically checks bank statement data (`.xlsx`) to identify paid invoices.
- **Idempotent Processing:** Prevents duplicate entries by matching Vendor and Invoice Numbers.
- **Modular CLI:** Each step (`ingest`, `validate`, `record`) can be run independently or via the main orchestrator.
- **TDD Backed:** Developed using Mini Orange Concepts (MOCs) and comprehensive `pytest` suites.

## 🏗 Architecture

The workflow follows a 3-step pipeline:

1. **Ingest:** Scans the `INGEST_DIR` for invoices and uses Gemini LLM to generate intermediate JSON data.
2. **Validate:** Validates extracted data, performs bank account lookups, and flags errors.
3. **Record:** Appends validated data to a master CSV and moves files to the `ARCHIVE_DIR`.

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
ARCHIVE_DIR=archive
ERROR_DIR=error
```

## 📖 Usage

The workflow can be executed as a full process or in individual steps.

### activate virtual environment

source venv/bin/activate  # On Windows: venv\Scripts\activate

### Main Orchestrator

Process all invoices in the ingest directory:

```bash
python -m ii_workflow.main process
```

### Individual Steps

For fine-grained control:

- **Ingest Invoices:**

  ```bash
  python -m ii_workflow.main ingest [PATH_TO_INVOICE]
  ```

- **Validate Data:**

  ```bash
  python -m ii_workflow.main validate [PATH_TO_JSON]
  ```

- **Record Results:**

  ```bash
  python -m ii_workflow.main record [PATH_TO_JSON]
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
