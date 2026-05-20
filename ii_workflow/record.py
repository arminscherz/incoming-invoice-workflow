import os
import json
import csv
from pathlib import Path
from datetime import datetime
import typer
from loguru import logger

from .models import InvoiceData

def _parse_date(date_obj) -> datetime:
    """Helper to parse dates from string or return datetime directly."""
    if isinstance(date_obj, datetime):
        return date_obj
    if not date_obj:
        return None
    date_str = str(date_obj).split(" ")[0].strip()
    
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    try:
        # Fallback to ISO format
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None

def check_google_sheet_duplicate(target_invoice_number: str, target_date_str: str, target_vendor: str) -> bool:
    """
    Checks if a duplicate row exists in the Google Worksheet tab 'Ausgaben'.
    Returns True if a duplicate exists, False otherwise.
    """
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
    if not spreadsheet_id:
        logger.warning("GOOGLE_SPREADSHEET_ID not found in environment. Google Sheets duplicate check skipped.")
        return False

    try:
        from googleapiclient.discovery import build
        from ii_workflow.ingest import get_google_credentials
        
        creds = get_google_credentials()
        if not creds:
            logger.warning("Failed to retrieve Google credentials. Google Sheets duplicate check skipped.")
            return False
            
        service = build("sheets", "v4", credentials=creds)
        
        # Read the 'Ausgaben' tab values
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Ausgaben"
        ).execute()
        
        rows = result.get("values", [])
        if not rows:
            logger.info("Google Sheet tab 'Ausgaben' is empty or doesn't exist.")
            return False
            
        headers = [str(h).strip().lower() for h in rows[0]]
        
        # We need to find column indices for 'invoice_number', 'date', 'vendor_name'
        try:
            inv_idx = headers.index("invoice_number")
            date_idx = headers.index("date")
            vendor_idx = headers.index("vendor_name")
        except ValueError as e:
            logger.error(f"Required header not found in Google Sheet 'Ausgaben': {e}. Headers present: {headers}")
            return False

        # Parse target date
        target_date = _parse_date(target_date_str)
        
        for idx, row in enumerate(rows[1:], start=2):
            # Row length might be less than headers, handle gracefully
            row_inv = str(row[inv_idx]).strip() if len(row) > inv_idx else ""
            row_date_str = str(row[date_idx]).strip() if len(row) > date_idx else ""
            row_vendor = str(row[vendor_idx]).strip() if len(row) > vendor_idx else ""
            
            row_date = _parse_date(row_date_str)
            
            # Check for matches
            if row_inv.lower() == target_invoice_number.strip().lower() and row_vendor.lower() == target_vendor.strip().lower():
                if target_date and row_date:
                    if target_date.date() == row_date.date():
                        logger.warning(f"Duplicate entry found in Google Sheets 'Ausgaben' (row {idx}) for invoice {target_invoice_number} from {target_vendor} on {target_date.strftime('%d.%m.%Y')}. Skipping append.")
                        return True
                elif not target_date and not row_date:
                    logger.warning(f"Duplicate entry found in Google Sheets 'Ausgaben' (row {idx}) for invoice {target_invoice_number} from {target_vendor} (dates unparseable/missing). Skipping append.")
                    return True
                    
        return False
        
    except Exception as e:
        logger.error(f"Error performing Google Sheets duplicate check: {e}")
        return False

def record_run(
    invoice_json: str = typer.Argument(..., help="Path to the validated invoice JSON."),
    result_csv: str = typer.Option("invoices_record.csv", "--result_csv", help="Filename or path for the output CSV.")
):
    """
    Appends validated invoice data to a master CSV file, preventing duplicate entries.
    """
    # 1. Configuration & Path Resolution
    validated_dir = Path(os.getenv("VALIDATED_DIR", "."))
    
    json_path = Path(invoice_json)
    if not json_path.is_absolute():
        if not json_path.exists():
            json_path = validated_dir / invoice_json
            
    if not json_path.exists():
        logger.error(f"Invoice JSON not found: {json_path}")
        raise typer.Exit(code=1)

    csv_path = Path(result_csv)
    if not csv_path.is_absolute():
        csv_path = Path.cwd() / result_csv

    result_columns_str = os.getenv("RESULT_COLUMNS")
    if not result_columns_str:
        logger.error("RESULT_COLUMNS environment variable must be set (e.g., 'vendor_name;invoice_number;date').")
        raise typer.Exit(code=1)
        
    columns = [col.strip() for col in result_columns_str.split(";")]

    # 2. Load the JSON Data
    try:
        with open(json_path, "r") as f:
            data_dict = json.load(f)
        invoice = InvoiceData.model_validate(data_dict)
    except Exception as e:
        logger.error(f"Failed to parse invoice JSON: {e}")
        raise typer.Exit(code=1)

    invoice_dict = invoice.model_dump()
    
    # Format fields
    for key, value in invoice_dict.items():
        if isinstance(value, float):
            invoice_dict[key] = f"{value:.2f}".replace(".", ",")
        elif key == "date" and isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
                invoice_dict[key] = dt.strftime("%d.%m.%Y")
            except ValueError:
                pass # Keep as is if not ISO format
    # 3. Duplicate Checking
    target_invoice_number = str(invoice_dict.get("invoice_number", ""))
    target_date = str(invoice_dict.get("date", ""))
    target_vendor = str(invoice_dict.get("vendor_name", ""))
    
    if check_google_sheet_duplicate(target_invoice_number, target_date, target_vendor):
        # Exit successfully so orchestrator can proceed (e.g., to archive it)
        raise typer.Exit(code=0)

    # 4. Append to CSV
    file_exists = csv_path.exists()
    try:
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, delimiter=";", extrasaction="ignore")
            
            if not file_exists:
                writer.writeheader()
                
            writer.writerow(invoice_dict)
    except Exception as e:
        logger.error(f"Failed to write to CSV {csv_path}: {e}")
        raise typer.Exit(code=1)

    logger.success(f"Recorded data for {json_path.name} to {csv_path.name}")
    typer.echo(str(csv_path.absolute()))
