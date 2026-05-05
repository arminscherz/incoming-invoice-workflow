import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import typer
from loguru import logger
import openpyxl

from .models import InvoiceData

def _parse_date(date_obj) -> datetime:
    """Helper to parse dates from string or return datetime directly."""
    if isinstance(date_obj, datetime):
        return date_obj
    if not date_obj:
        return None
    date_str = str(date_obj).split(" ")[0]
    
    # Try ISO format
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        pass
        
    # Try DD.MM.YYYY
    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        pass
        
    # Try DD.MM.YY
    try:
        return datetime.strptime(date_str, "%d.%m.%y")
    except ValueError:
        return None

def validate_run(
    invoice_json: str = typer.Argument(..., help="Path to the extracted invoice JSON."),
    bank_statement: str = typer.Option(None, "--bank_statement", help="Path to the bank account data file (.xlsx).")
):
    """
    Validate extracted invoice data and perform bank account matching.
    """
    # 1. Resolve Paths
    work_dir = Path(os.getenv("WORK_DIR", "."))
    ingest_dir = Path(os.getenv("INGEST_DIR", str(work_dir)))
    ingested_dir = Path(os.getenv("INGESTED_DIR", str(work_dir)))
    
    json_path = Path(invoice_json)
    if not json_path.is_absolute():
        if not json_path.exists():
            json_path = ingested_dir / invoice_json
            
    if not json_path.exists():
        logger.error(f"Invoice JSON not found: {json_path}")
        raise typer.Exit(code=1)
        
    bank_path = None
    if bank_statement:
        bank_path = Path(bank_statement)
        if not bank_path.is_absolute():
            if not bank_path.exists():
                bank_path = ingest_dir / bank_statement
                
        if not bank_path.exists():
            logger.error(f"Bank data file not found: {bank_path}")
            raise typer.Exit(code=1)

    if bank_path:
        logger.info(f"Validating {json_path.name} against {bank_path.name}")
    else:
        logger.info(f"Validating {json_path.name} without bank statement")

    # 2. Load Invoice JSON
    try:
        with open(json_path, "r") as f:
            data_dict = json.load(f)
        invoice = InvoiceData.model_validate(data_dict)
    except Exception as e:
        logger.error(f"Failed to parse invoice JSON: {e}")
        raise typer.Exit(code=1)

    # 3. Pre-check: Gross == Net
    gross = invoice.total_invoice_amount_gross
    net = invoice.total_invoice_amount_net
    tax = invoice.total_invoice_amount_tax
    
    if abs(gross - net) < 0.05:
        logger.warning(f"Gross amount ({gross}) equals Net amount ({net}). Recalculating net amount...")
        net = (
            gross 
            - invoice.tip_amount 
            - invoice.tax_amount_0_percent_VAT 
            - invoice.tax_amount_10_percent_VAT 
            - invoice.tax_amount_13_percent_VAT 
            - invoice.tax_amount_20_percent_VAT
        )
        invoice.total_invoice_amount_net = net
        logger.info(f"Recalculated Net amount: {net}")

    # 4. Gross vs Net+Tax Validation    
    if abs(gross - (net + tax)) > 0.05:
        logger.error(f"Math validation failed: Gross ({gross}) does not equal Net ({net}) + Tax ({tax})")
        raise typer.Exit(code=1)

    logger.success(f"Validation passed: Gross equals Net + Tax for {json_path.name}")
        
    sum_taxes = (
        invoice.tax_amount_0_percent_VAT +
        invoice.tax_amount_10_percent_VAT +
        invoice.tax_amount_13_percent_VAT +
        invoice.tax_amount_20_percent_VAT
    )
    if abs(sum_taxes - tax) > 0.05:
        logger.error(f"Math validation failed: Sum of VAT fields ({sum_taxes}) does not equal total tax ({tax})")
        raise typer.Exit(code=1)

    logger.success(f"Validation passed: Tax amounts match the tax sum for {json_path.name}")
    
    # 4. Tip Validation
    if invoice.total_payment_amount_gross is not None:
        calculated_tip = round(invoice.total_payment_amount_gross - invoice.total_invoice_amount_gross, 2)
        if abs(calculated_tip - invoice.tip_amount) > 0.05:
            logger.warning(f"Tip mismatch for {json_path.name}: Calculated tip ({calculated_tip}) differs from extracted tip ({invoice.tip_amount})")
        else:
            logger.success(f"Validation passed: Tip calculation matches for {json_path.name} (Tip: {calculated_tip})")
    else:
        logger.info(f"Skipping tip validation for {json_path.name} (no payment amount provided)")

    # 5. Bank Matching Heuristics
    payment_method = "bar" # Default
    target_amount = invoice.total_payment_amount_gross if invoice.total_payment_amount_gross is not None else invoice.total_invoice_amount_gross
    invoice_date = _parse_date(invoice.date)
    
    # Clean vendor name for exact match
    import re
    cleaned_vendor = re.sub(r'(?i)\b(gmbh|ag|e\.u\.|kg|gesmbh)\b', '', invoice.vendor_name)
    cleaned_vendor = re.sub(r'[^a-zA-Z0-9\säöüÄÖÜß]', '', cleaned_vendor)
    cleaned_vendor = ' '.join(cleaned_vendor.split()).lower()
    
    # Extract vendor keywords (words > 2 chars)
    vendor_keywords = [w for w in cleaned_vendor.split() if len(w) > 2]

    try:
        if bank_path:
            wb = openpyxl.load_workbook(bank_path, data_only=True)
            ws = wb.active
            
            headers = None
            for row in ws.iter_rows(values_only=True):
                if not headers:
                    # Look for header row
                    if row and "Valutadatum" in str(row) and "Betrag" in str(row):
                        headers = {str(cell): idx for idx, cell in enumerate(row) if cell}
                    continue
                    
                # Process transaction row
                if not any(row): continue # Skip empty rows
                
                try:
                    betrag = row[headers["Betrag"]]
                    if betrag is None: continue
                    txn_amount = abs(float(betrag))
                    
                    # Check amount match (+/- 0.05 tolerance)
                    if abs(txn_amount - target_amount) > 0.05:
                        continue
                    
                    # Check date match (+/- 7 days)
                    valuta_val = row[headers["Valutadatum"]]
                    txn_date = _parse_date(valuta_val)
                    if not invoice_date or not txn_date:
                        continue
                        
                    days_diff = abs((invoice_date - txn_date).days)
                    if days_diff > 7:
                        continue
                        
                    # Check vendor match
                    gegenpartei = str(row[headers.get("Gegenpartei", -1)] or "").lower()
                    bezeichnung = str(row[headers.get("Bezeichnung", -1)] or "").lower()
                    nachricht = str(row[headers.get("Nachricht", -1)] or "").lower()
                    
                    combined_text = f"{gegenpartei} {bezeichnung} {nachricht}"
                    
                    if cleaned_vendor and cleaned_vendor in combined_text:
                        payment_method = "Bankkonto"
                        logger.info(f"Matched bank transaction on {txn_date.date()} for amount {txn_amount} (Exact vendor match)")
                        break
                    
                    # Fallback: Keyword match
                    match_found = False
                    for kw in vendor_keywords:
                        if kw in combined_text:
                            match_found = True
                            break
                            
                    if match_found:
                        payment_method = "Bankkonto"
                        logger.warning(f"Matched bank transaction on {txn_date.date()} for amount {txn_amount} (Partial keyword match only. Verify manually if correct.)")
                        break
                        
                except (ValueError, KeyError, TypeError):
                    continue
                    
    except Exception as e:
        logger.error(f"Error processing bank statement: {e}")
        raise typer.Exit(code=1)

    # Log the bank matching result
    if bank_path:
        if payment_method == "Bankkonto":
            logger.success(f"Bank statement match found for {json_path.name}: payment_method set to 'Bankkonto'")
        else:
            logger.warning(f"No bank statement match found for {json_path.name}: payment_method defaults to 'bar'")
    else:
        logger.info(f"Skipping bank lookup for {json_path.name}: payment_method set to 'bar'")

    # 6. Tip to 0% VAT Allocation
    if invoice.tip_amount > 0:
        if invoice.tax_amount_0_percent_VAT == 0:
            logger.info(f"Allocating tip amount ({invoice.tip_amount}) to tax_amount_0_percent_VAT for {json_path.name}")
            invoice.tax_amount_0_percent_VAT = invoice.tip_amount
        elif invoice.tip_amount == invoice.tax_amount_0_percent_VAT:
            logger.debug(f"Tip amount already matches tax_amount_0_percent_VAT for {json_path.name}. Skipping calculation.")
        else:
            logger.warning(f"Tip amount ({invoice.tip_amount}) differs from non-zero tax_amount_0_percent_VAT ({invoice.tax_amount_0_percent_VAT}) for {json_path.name}. No automatic allocation performed.")

    # 7. Save Validated JSON
    invoice.payment_method = payment_method
    
    validated_dir = Path(os.getenv("VALIDATED_DIR", "."))
    if not validated_dir.exists():
        validated_dir.mkdir(parents=True, exist_ok=True)

    output_filename = f"{json_path.stem}-validated.json"
    output_path = validated_dir / output_filename
    
    with open(output_path, "w") as f:
        json.dump(invoice.model_dump(), f, indent=2)
        
    logger.info(f"Validated data saved to {output_path}")
    typer.echo(str(output_path.absolute()))
