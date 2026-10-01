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

COMMON_VENDOR_TERMS = {
    "gmbh", "ag", "kg", "og", "gesmbh", "e.u.", "eu", "co", "ltd", "inc", "sa", "se", "gbr",
    "restaurant", "gasthaus", "gasthof", "bistro", "cafe", "café", "hotel", "markt", "filiale",
    "service", "services", "austria", "wien", "vienna", "vendor", "shop", "store", "online"
}

STOPWORDS = {
    "und", "der", "die", "das", "den", "dem", "des", "von", "vom", "mit", "fuer", "für",
    "bei", "zum", "zur", "im", "in", "am", "an", "auf", "aus", "nach", "ueber", "über",
    "and", "the", "for", "with", "at", "by", "from", "to", "of", "in", "on"
}

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

    # 2b. Soft Warning for 0% VAT
    if invoice.tax_amount_0_percent_VAT > 0.0:
        logger.warning(f"Inconsistent tax amount for 0% VAT detected: {invoice.tax_amount_0_percent_VAT}. Keeping value as extracted.")

    # 2c. Invoice Date Check (> 6 months from today)
    inv_date_dt = _parse_date(invoice.date)
    if inv_date_dt:
        today = datetime.now()
        days_diff_today = abs((today.date() - inv_date_dt.date()).days)
        if days_diff_today > 182:
            logger.warning(
                f"Invoice date '{invoice.date}' differs by more than 6 months ({days_diff_today} days) from today's date ({today.strftime('%Y-%m-%d')}) for {json_path.name}. Please verify manually."
            )

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

    # 5. Gross vs Net+Tax Validation    
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
    
    sum_net_amounts = (
        invoice.net_amount_0_percent_VAT +
        invoice.net_amount_10_percent_VAT +
        invoice.net_amount_13_percent_VAT +
        invoice.net_amount_20_percent_VAT
    )
    if abs(sum_net_amounts - net) > 0.05:
        logger.error(f"Math validation failed: Net amounts sum ({sum_net_amounts}) does not match total invoice net amount ({net})")
        raise typer.Exit(code=1)

    logger.success(f"Validation passed: Net amounts match the total net amount for {json_path.name}")
    
    # 5b. VAT Amount Consistency Check
    vat_checks = [
        ("0%", invoice.tax_amount_0_percent_VAT, invoice.net_amount_0_percent_VAT * 0.00),
        ("10%", invoice.tax_amount_10_percent_VAT, invoice.net_amount_10_percent_VAT * 0.10),
        ("13%", invoice.tax_amount_13_percent_VAT, invoice.net_amount_13_percent_VAT * 0.13),
        ("20%", invoice.tax_amount_20_percent_VAT, invoice.net_amount_20_percent_VAT * 0.20),
    ]
    
    for vat_name, actual_tax, expected_tax in vat_checks:
        if abs(actual_tax - expected_tax) > 0.02:
            logger.error(f"VAT amount consistency check failed for {vat_name}: Actual tax ({actual_tax}) does not match expected tax ({round(expected_tax, 2)}) for {json_path.name}")
            raise typer.Exit(code=1)

    logger.success(f"Validation passed: VAT amounts are consistent for {json_path.name}")
    
    # 6. Tip Validation
    if invoice.total_payment_amount_gross is not None:
        calculated_tip = round(invoice.total_payment_amount_gross - invoice.total_invoice_amount_gross, 2)
        if abs(calculated_tip - invoice.tip_amount) > 0.05:
            logger.warning(f"Tip mismatch for {json_path.name}: Calculated tip ({calculated_tip}) differs from extracted tip ({invoice.tip_amount})")
        else:
            logger.success(f"Validation passed: Tip calculation matches for {json_path.name} (Tip: {calculated_tip})")
    else:
        logger.info(f"Skipping tip validation for {json_path.name} (no payment amount provided)")

    # 7. Bank Matching Heuristics
    payment_method = "bar" # Default
    target_amount = invoice.total_payment_amount_gross if invoice.total_payment_amount_gross is not None else invoice.total_invoice_amount_gross
    inv_amount = invoice.total_invoice_amount_gross
    invoice_date = _parse_date(invoice.date)
    
    # Clean vendor name for exact match
    import re
    cleaned_vendor = re.sub(r'(?i)\b(gmbh|ag|e\.u\.|kg|gesmbh|og|co|ltd)\b', '', invoice.vendor_name)
    cleaned_vendor = re.sub(r'[^a-zA-Z0-9\säöüÄÖÜß]', ' ', cleaned_vendor)
    cleaned_vendor = ' '.join(cleaned_vendor.split()).lower()
    
    # Extract vendor keywords (excluding stopwords and common vendor terms)
    vendor_keywords = [
        w for w in cleaned_vendor.split()
        if len(w) > 2 and w not in STOPWORDS and w not in COMMON_VENDOR_TERMS
    ]

    inv_num_clean = invoice.invoice_number.strip().lower()

    try:
        if bank_path:
            wb = openpyxl.load_workbook(bank_path, data_only=True)
            ws = wb.active
            
            headers = None
            candidates = []
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
                    
                    # 1. Amount match evaluation: exact, tip, or span
                    amount_match_type = None
                    if abs(txn_amount - target_amount) <= 0.05 or abs(txn_amount - inv_amount) <= 0.05:
                        amount_match_type = "exact"
                    elif txn_amount > target_amount and (txn_amount - target_amount) <= max(10.0, target_amount * 0.30):
                        amount_match_type = "tip"
                    elif abs(txn_amount - target_amount) <= max(5.0, target_amount * 0.15):
                        amount_match_type = "span"
                        
                    if not amount_match_type:
                        continue
                    
                    # 2. Date match evaluation (candidate dates + date span)
                    valuta_val = row[headers["Valutadatum"]]
                    txn_date = _parse_date(valuta_val)
                    if not txn_date:
                        continue
                        
                    cand_dates = []
                    if invoice_date:
                        cand_dates.append(invoice_date)
                        if invoice_date.year != txn_date.year:
                            try:
                                cand_dates.append(invoice_date.replace(year=txn_date.year))
                            except ValueError:
                                pass
                            
                    if not cand_dates:
                        continue
                        
                    min_diff = min(abs((d - txn_date).days) for d in cand_dates)
                    
                    # 3. Text details match
                    gegenpartei = str(row[headers.get("Gegenpartei", -1)] or "").lower()
                    bezeichnung = str(row[headers.get("Bezeichnung", -1)] or "").lower()
                    nachricht = str(row[headers.get("Nachricht", -1)] or "").lower()
                    combined_text = f"{gegenpartei} {bezeichnung} {nachricht}"
                    
                    text_match_type = None
                    matched_kws = []
                    if len(inv_num_clean) >= 3 and inv_num_clean in combined_text:
                        text_match_type = "structured"
                    elif cleaned_vendor and (cleaned_vendor in combined_text or combined_text in cleaned_vendor):
                        text_match_type = "exact_vendor"
                    else:
                        for kw in vendor_keywords:
                            if kw in combined_text:
                                matched_kws.append(kw)
                        if matched_kws:
                            text_match_type = "partial_keyword"
                            
                    if not text_match_type:
                        continue

                    # Date span check: allow up to 30 days for structured match, otherwise up to 14 days
                    max_allowed_days = 30 if text_match_type == "structured" else 14
                    if min_diff > max_allowed_days:
                        continue
                        
                    # Non-exact amount requires high-confidence text match
                    if amount_match_type != "exact" and text_match_type == "partial_keyword" and len(matched_kws) < 2:
                        continue
                        
                    # Calculate candidate score
                    score = 0
                    if text_match_type == "structured": score += 100
                    elif text_match_type == "exact_vendor": score += 50
                    elif text_match_type == "partial_keyword": score += 15 * len(matched_kws)
                    
                    if amount_match_type == "exact": score += 30
                    elif amount_match_type == "tip": score += 15
                    elif amount_match_type == "span": score += 5
                    
                    score -= min_diff # Prioritize closer dates
                    
                    candidates.append({
                        "score": score,
                        "row": row,
                        "txn_date": txn_date,
                        "txn_amount": txn_amount,
                        "text_match_type": text_match_type,
                        "amount_match_type": amount_match_type,
                        "min_diff": min_diff,
                        "matched_kws": matched_kws
                    })
                except (ValueError, KeyError, TypeError):
                    continue

            # Evaluate candidate transactions
            if len(candidates) > 1:
                logger.warning(f"Multiple bank transactions ({len(candidates)}) match criteria for invoice {json_path.name}. Selecting highest scoring match...")
                
            candidates.sort(key=lambda x: x["score"], reverse=True)
            
            if candidates:
                best = candidates[0]
                cand_row = best["row"]
                cand_date = best["txn_date"]
                cand_amount = best["txn_amount"]
                match_type = best["text_match_type"]
                amt_match = best["amount_match_type"]
                payment_method = "Bankkonto"
                
                # Check for year correction in invoice date based on bank transaction date
                if invoice_date and invoice_date.year != cand_date.year:
                    try:
                        adj = invoice_date.replace(year=cand_date.year)
                        if abs((adj - cand_date).days) <= 14:
                            logger.warning(f"Correcting invoice year in date from {invoice.date} to {adj.strftime('%Y-%m-%d')} based on bank transaction")
                            invoice.date = adj.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                        
                # Update tip and payment amount if bank transaction included tip
                if amt_match == "tip" and cand_amount > invoice.total_invoice_amount_gross:
                    calc_tip = round(cand_amount - invoice.total_invoice_amount_gross, 2)
                    invoice.total_payment_amount_gross = cand_amount
                    if invoice.tip_amount == 0.0:
                        invoice.tip_amount = calc_tip
                        logger.info(f"Updated payment amount to {cand_amount} and tip amount to {calc_tip} for {json_path.name} based on bank transaction")
                
                if match_type == "structured":
                    logger.success(f"Matched bank transaction on {cand_date.date()} for amount {cand_amount} (Structured invoice number match: '{invoice.invoice_number}')")
                elif match_type == "exact_vendor":
                    logger.info(f"Matched bank transaction on {cand_date.date()} for amount {cand_amount} (Exact vendor match, amount match: {amt_match})")
                elif match_type == "partial_keyword":
                    logger.warning(f"Matched bank transaction on {cand_date.date()} for amount {cand_amount} (Partial keyword match on {best['matched_kws']}, amount match: {amt_match}. Verify manually if correct.)")
                    
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

    # 8. Tip to 0% VAT Allocation
    if invoice.tip_amount > 0:
        if invoice.net_amount_0_percent_VAT == 0:
            logger.info(f"Allocating tip amount ({invoice.tip_amount}) to net_amount_0_percent_VAT for {json_path.name}")
            invoice.net_amount_0_percent_VAT = invoice.tip_amount
        elif abs(invoice.tip_amount - invoice.net_amount_0_percent_VAT) < 0.05:
            logger.debug(f"Tip amount already matches net_amount_0_percent_VAT for {json_path.name}. Skipping calculation.")
        else:
            logger.warning(f"Tip amount ({invoice.tip_amount}) differs from non-zero net_amount_0_percent_VAT ({invoice.net_amount_0_percent_VAT}) for {json_path.name}. No automatic allocation performed.")

    # 9. Save Validated JSON
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
