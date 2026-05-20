import os
import json
import csv
import html
from pathlib import Path
from datetime import datetime, timedelta
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

def parse_recipient_address(address_str: str) -> dict:
    """
    Parses a comma-separated address string into ZUGFeRD components.
    Example: 'Töpfelgasse 14/7, 1140 Wien, Österreich'
    """
    result = {
        "street": "",
        "zip": "",
        "city": "",
        "country": "AT"
    }
    if not address_str:
        return result
        
    parts = [p.strip() for p in address_str.split(",")]
    if len(parts) >= 1:
        result["street"] = parts[0]
    if len(parts) >= 2:
        # e.g., '1140 Wien'
        zip_city = parts[1].split(maxsplit=1)
        if len(zip_city) >= 1:
            result["zip"] = zip_city[0]
        if len(zip_city) >= 2:
            result["city"] = zip_city[1]
    if len(parts) >= 3:
        country_name = parts[2].lower()
        if "österreich" in country_name or "austria" in country_name or "at" in country_name:
            result["country"] = "AT"
        elif "deutschland" in country_name or "germany" in country_name or "de" in country_name:
            result["country"] = "DE"
        else:
            # Fallback or keep as is if 2 letters
            val_clean = parts[2].strip()
            if len(val_clean) == 2:
                result["country"] = val_clean.upper()
            else:
                result["country"] = "AT" # default
    return result


def generate_zugferd_xml(invoice: InvoiceData) -> bytes:
    """
    Generates a ZUGFeRD/Factur-X BASIC WL compliant XML string for document-level booking.
    """
    # Load invoice recipient values from environment
    recipient_name = os.getenv("INVOICE_RECIPIENT_NAME")
    recipient_address_str = os.getenv("INVOICE_RECIPIENT_ADDRESS")
    recipient_vat = os.getenv("INVOICE_RECIPIENT_VAT_NUMBER")
    
    # Fallback to invoice customer name/vat if env variables are not set
    if not recipient_name:
        recipient_name = invoice.customer_name or "Kunde"
    if not recipient_vat:
        recipient_vat = invoice.customer_vat_id
        
    buyer_addr = parse_recipient_address(recipient_address_str)
    # 1. Parse date and calculate due date
    inv_date_dt = _parse_date(invoice.date)
    if not inv_date_dt:
        inv_date_dt = datetime.now()
    
    issue_date_str = inv_date_dt.strftime("%Y%m%d")
    
    # Calculate due date: invoice date + 14 days
    due_date_dt = inv_date_dt + timedelta(days=14)
    due_date_str = due_date_dt.strftime("%Y%m%d")

    # 2. Build tax breakdown
    taxes = []
    # 20% VAT
    if invoice.net_amount_20_percent_VAT > 0 or invoice.tax_amount_20_percent_VAT > 0:
        taxes.append({
            "rate": 20.0,
            "basis": invoice.net_amount_20_percent_VAT,
            "amount": invoice.tax_amount_20_percent_VAT,
            "category": "S"
        })
    # 13% VAT
    if invoice.net_amount_13_percent_VAT > 0 or invoice.tax_amount_13_percent_VAT > 0:
        taxes.append({
            "rate": 13.0,
            "basis": invoice.net_amount_13_percent_VAT,
            "amount": invoice.tax_amount_13_percent_VAT,
            "category": "S"
        })
    # 10% VAT
    if invoice.net_amount_10_percent_VAT > 0 or invoice.tax_amount_10_percent_VAT > 0:
        taxes.append({
            "rate": 10.0,
            "basis": invoice.net_amount_10_percent_VAT,
            "amount": invoice.tax_amount_10_percent_VAT,
            "category": "S"
        })
    # 0% VAT
    if invoice.net_amount_0_percent_VAT > 0 or invoice.tax_amount_0_percent_VAT > 0:
        taxes.append({
            "rate": 0.0,
            "basis": invoice.net_amount_0_percent_VAT,
            "amount": invoice.tax_amount_0_percent_VAT,
            "category": "Z"
        })

    if not taxes:
        # Fallback if no specific VAT levels were extracted
        rate = 20.0 if invoice.total_invoice_amount_tax > 0 else 0.0
        taxes.append({
            "rate": rate,
            "basis": invoice.total_invoice_amount_net,
            "amount": invoice.total_invoice_amount_tax,
            "category": "S" if rate > 0 else "Z"
        })

    # XML namespaces & structure conforming to basicwl
    xml_parts = []
    xml_parts.append(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rsm:CrossIndustryInvoice '
        'xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100" '
        'xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" '
        'xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" '
        'xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    )
    
    xml_parts.append('  <rsm:ExchangedDocumentContext>')
    xml_parts.append('    <ram:BusinessProcessSpecifiedDocumentContextParameter>')
    xml_parts.append('      <ram:ID>A1</ram:ID>')
    xml_parts.append('    </ram:BusinessProcessSpecifiedDocumentContextParameter>')
    xml_parts.append('    <ram:GuidelineSpecifiedDocumentContextParameter>')
    xml_parts.append('      <ram:ID>urn:factur-x.eu:1p0:basicwl</ram:ID>')
    xml_parts.append('    </ram:GuidelineSpecifiedDocumentContextParameter>')
    xml_parts.append('  </rsm:ExchangedDocumentContext>')
    
    xml_parts.append('  <rsm:ExchangedDocument>')
    xml_parts.append(f'    <ram:ID>{html.escape(invoice.invoice_number)}</ram:ID>')
    xml_parts.append('    <ram:TypeCode>380</ram:TypeCode>')
    xml_parts.append('    <ram:IssueDateTime>')
    xml_parts.append(f'      <udt:DateTimeString format="102">{issue_date_str}</udt:DateTimeString>')
    xml_parts.append('    </ram:IssueDateTime>')
    xml_parts.append('  </rsm:ExchangedDocument>')
    
    xml_parts.append('  <rsm:SupplyChainTradeTransaction>')
    xml_parts.append('    <ram:ApplicableHeaderTradeAgreement>')
    
    # Seller details
    xml_parts.append('      <ram:SellerTradeParty>')
    xml_parts.append(f'        <ram:Name>{html.escape(invoice.vendor_name)}</ram:Name>')
    xml_parts.append('        <ram:PostalTradeAddress>')
    if invoice.vendor_address_zip:
        xml_parts.append(f'          <ram:PostcodeCode>{html.escape(invoice.vendor_address_zip)}</ram:PostcodeCode>')
    if invoice.vendor_address_street:
        xml_parts.append(f'          <ram:LineOne>{html.escape(invoice.vendor_address_street)}</ram:LineOne>')
    if invoice.vendor_address_city:
        xml_parts.append(f'          <ram:CityName>{html.escape(invoice.vendor_address_city)}</ram:CityName>')
    xml_parts.append(f'          <ram:CountryID>{html.escape(invoice.vendor_address_country or "AT")}</ram:CountryID>')
    xml_parts.append('        </ram:PostalTradeAddress>')
    if invoice.vendor_vat_id:
        xml_parts.append('        <ram:SpecifiedTaxRegistration>')
        xml_parts.append(f'          <ram:ID schemeID="VA">{html.escape(invoice.vendor_vat_id)}</ram:ID>')
        xml_parts.append('        </ram:SpecifiedTaxRegistration>')
    xml_parts.append('      </ram:SellerTradeParty>')
    
    # Buyer details
    xml_parts.append('      <ram:BuyerTradeParty>')
    xml_parts.append(f'        <ram:Name>{html.escape(recipient_name)}</ram:Name>')
    xml_parts.append('        <ram:PostalTradeAddress>')
    if buyer_addr["zip"]:
        xml_parts.append(f'          <ram:PostcodeCode>{html.escape(buyer_addr["zip"])}</ram:PostcodeCode>')
    if buyer_addr["street"]:
        xml_parts.append(f'          <ram:LineOne>{html.escape(buyer_addr["street"])}</ram:LineOne>')
    if buyer_addr["city"]:
        xml_parts.append(f'          <ram:CityName>{html.escape(buyer_addr["city"])}</ram:CityName>')
    xml_parts.append(f'          <ram:CountryID>{html.escape(buyer_addr["country"])}</ram:CountryID>')
    xml_parts.append('        </ram:PostalTradeAddress>')
    if recipient_vat:
        xml_parts.append('        <ram:SpecifiedTaxRegistration>')
        xml_parts.append(f'          <ram:ID schemeID="VA">{html.escape(recipient_vat)}</ram:ID>')
        xml_parts.append('        </ram:SpecifiedTaxRegistration>')
    xml_parts.append('      </ram:BuyerTradeParty>')
    
    xml_parts.append('    </ram:ApplicableHeaderTradeAgreement>')
    
    # Delivery
    xml_parts.append('    <ram:ApplicableHeaderTradeDelivery/>')
    
    # Settlement
    xml_parts.append('    <ram:ApplicableHeaderTradeSettlement>')
    currency = invoice.currency or "EUR"
    xml_parts.append(f'      <ram:InvoiceCurrencyCode>{html.escape(currency)}</ram:InvoiceCurrencyCode>')
    
    # Payment means
    if invoice.iban:
        xml_parts.append('      <ram:SpecifiedTradeSettlementPaymentMeans>')
        xml_parts.append('        <ram:TypeCode>42</ram:TypeCode>')
        xml_parts.append('        <ram:PayeePartyCreditorFinancialAccount>')
        xml_parts.append(f'          <ram:IBANID>{html.escape(invoice.iban)}</ram:IBANID>')
        xml_parts.append('        </ram:PayeePartyCreditorFinancialAccount>')
        xml_parts.append('      </ram:SpecifiedTradeSettlementPaymentMeans>')
        
    # Applicable Trade Taxes
    for tax in taxes:
        xml_parts.append('      <ram:ApplicableTradeTax>')
        xml_parts.append(f'        <ram:CalculatedAmount>{tax["amount"]:.2f}</ram:CalculatedAmount>')
        xml_parts.append('        <ram:TypeCode>VAT</ram:TypeCode>')
        xml_parts.append(f'        <ram:BasisAmount>{tax["basis"]:.2f}</ram:BasisAmount>')
        xml_parts.append(f'        <ram:CategoryCode>{tax["category"]}</ram:CategoryCode>')
        xml_parts.append(f'        <ram:RateApplicablePercent>{tax["rate"]}</ram:RateApplicablePercent>')
        xml_parts.append('      </ram:ApplicableTradeTax>')
        
    # Payment Terms
    xml_parts.append('      <ram:SpecifiedTradePaymentTerms>')
    xml_parts.append('        <ram:DueDateDateTime>')
    xml_parts.append(f'          <udt:DateTimeString format="102">{due_date_str}</udt:DateTimeString>')
    xml_parts.append('        </ram:DueDateDateTime>')
    xml_parts.append('      </ram:SpecifiedTradePaymentTerms>')
    
    # Monetary Summation
    xml_parts.append('      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>')
    xml_parts.append(f'        <ram:LineTotalAmount>{invoice.total_invoice_amount_net:.2f}</ram:LineTotalAmount>')
    xml_parts.append(f'        <ram:TaxBasisTotalAmount>{invoice.total_invoice_amount_net:.2f}</ram:TaxBasisTotalAmount>')
    xml_parts.append(f'        <ram:TaxTotalAmount currencyID="{currency}">{invoice.total_invoice_amount_tax:.2f}</ram:TaxTotalAmount>')
    xml_parts.append(f'        <ram:GrandTotalAmount>{invoice.total_invoice_amount_gross:.2f}</ram:GrandTotalAmount>')
    xml_parts.append(f'        <ram:DuePayableAmount>{invoice.total_invoice_amount_gross:.2f}</ram:DuePayableAmount>')
    xml_parts.append('      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>')
    
    xml_parts.append('    </ram:ApplicableHeaderTradeSettlement>')
    xml_parts.append('  </rsm:SupplyChainTradeTransaction>')
    xml_parts.append('</rsm:CrossIndustryInvoice>')
    
    xml_string = "\n".join(xml_parts)
    return xml_string.encode("utf-8")


def record_run(
    invoice_json: str = typer.Argument(..., help="Path to the validated invoice JSON."),
    result_csv: str = typer.Option("invoices_record.csv", "--result_csv", help="Filename or path for the output CSV."),
    scan_file: str = typer.Option(None, "--scan_file", help="Path to the scanned PDF invoice file."),
    scan_archive_dir: str = typer.Option(None, "--scan_archive_dir", help="Directory where the generated ZUGFeRD PDF should be stored.")
):
    """
    Appends validated invoice data to a master CSV file, preventing duplicate entries.
    Generates and embeds ZUGFeRD BASIC WL XML in the scan file if options are provided.
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

    # 5. ZUGFeRD / Factur-X generation
    if scan_file and scan_archive_dir:
        scan_path = Path(scan_file)
        archive_dir = Path(scan_archive_dir)
        
        if not scan_path.is_absolute():
            ingest_dir = os.getenv("INGEST_DIR", "ingest")
            resolved_scan_path = Path.cwd() / ingest_dir / scan_file
            if resolved_scan_path.exists():
                scan_path = resolved_scan_path
                
        if not scan_path.exists():
            logger.error(f"Scan file not found: {scan_file}")
            raise typer.Exit(code=3)
            
        # If it is an image, convert to PDF
        if scan_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            try:
                from PIL import Image
                logger.info(f"Converting scan image {scan_path.name} to PDF...")
                pdf_path = scan_path.with_suffix(".pdf")
                with Image.open(scan_path) as img:
                    img.convert("RGB").save(pdf_path, "PDF")
                # Delete original scan file (as it's an image)
                scan_path.unlink()
                scan_path = pdf_path
            except Exception as e:
                logger.error(f"Image conversion failed in record step: {e}")
                raise typer.Exit(code=3)
            
        archive_dir.mkdir(parents=True, exist_ok=True)
        output_pdf = archive_dir / f"{scan_path.name}"
        
        try:
            import facturx
            logger.info(f"Generating ZUGFeRD/Factur-X BASIC WL XML for {scan_path.name}...")
            xml_bytes = generate_zugferd_xml(invoice)
            
            logger.info(f"Embedding XML into {scan_path.name} to produce hybrid PDF/A-3...")
            facturx.generate_from_file(
                pdf_file=str(scan_path),
                xml=xml_bytes,
                flavor='factur-x',
                level='basicwl',
                afrelationship='data',
                output_pdf_file=str(output_pdf)
            )
            
            logger.success(f"Successfully generated hybrid ZUGFeRD PDF at {output_pdf}")
            # Delete original PDF/converted PDF scan file on success
            scan_path.unlink()
            logger.info(f"Cleaned up original scan file: {scan_path.name}")
        except Exception as e:
            logger.error(f"ZUGFeRD/Factur-X generation failed: {e}")
            raise typer.Exit(code=3)

    typer.echo(str(csv_path.absolute()))
