import os
import json
import csv
from pathlib import Path
from datetime import datetime
import typer
from loguru import logger

from .models import InvoiceData

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
    file_exists = csv_path.exists()
    
    target_invoice_number = str(invoice_dict.get("invoice_number", ""))
    target_date = str(invoice_dict.get("date", ""))
    target_vendor = str(invoice_dict.get("vendor_name", ""))
    
    if file_exists:
        try:
            with open(csv_path, "r", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    # Check for duplicates based on invoice_number, date, and vendor_name
                    row_inv = str(row.get("invoice_number", ""))
                    row_date = str(row.get("date", ""))
                    row_vendor = str(row.get("vendor_name", ""))
                    
                    if (row_inv == target_invoice_number and 
                        row_date == target_date and 
                        row_vendor == target_vendor):
                        
                        logger.warning(f"Duplicate entry found in {csv_path.name} for invoice {target_invoice_number} from {target_vendor} on {target_date}. Skipping append.")
                        # Exit successfully so orchestrator can proceed (e.g., to archive it)
                        raise typer.Exit(code=0)
        except Exception as e:
             if not isinstance(e, typer.Exit):
                 logger.error(f"Error reading CSV for duplicate check: {e}")
                 raise typer.Exit(code=1)
             else:
                 raise

    # 4. Append to CSV
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
