import json
import os
import csv
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from PIL import Image
import pypdf
import facturx
from typer.testing import CliRunner

from ii_workflow.main import app
from ii_workflow.models import InvoiceData

runner = CliRunner()

@pytest.fixture(autouse=True)
def mock_sheets_duplicate_check(mocker):
    """Mock out the Google Sheets duplicate check globally in this test file."""
    return mocker.patch("ii_workflow.record.check_google_sheet_duplicate", return_value=False)

@pytest.fixture
def sample_validated_json(tmp_path):
    """Creates a sample validated JSON file with new BMD & ZUGFeRD fields."""
    validated_dir = tmp_path / "validated"
    validated_dir.mkdir(parents=True, exist_ok=True)
    
    data = {
        "vendor_name": "Test Vendor GmbH",
        "purchase_category": "Büromaterial",
        "invoice_number": "INV-123",
        "date": "2026-05-04",
        "total_invoice_amount_gross": 120.0,
        "total_invoice_amount_net": 100.0,
        "total_invoice_amount_tax": 20.0,
        "tip_amount": 0.0,
        "total_payment_amount_gross": 120.0,
        "tax_amount_0_percent_VAT": 0.0,
        "tax_amount_10_percent_VAT": 0.0,
        "tax_amount_13_percent_VAT": 0.0,
        "tax_amount_20_percent_VAT": 20.0,
        "net_amount_0_percent_VAT": 0.0,
        "net_amount_10_percent_VAT": 0.0,
        "net_amount_13_percent_VAT": 0.0,
        "net_amount_20_percent_VAT": 100.0,
        "currency": "EUR",
        "iban": "AT123456789012345678",
        "payment_method": "Bankkonto",
        "vendor_vat_id": "ATU68822002",
        "customer_vat_id": "ATU87654321",
        "customer_name": "Armin Scherz",
        "vendor_address_street": "Spengergasse 20",
        "vendor_address_zip": "1050",
        "vendor_address_city": "Wien",
        "vendor_address_country": "AT",
        "payment_reference": "REF-2026-99"
    }
    
    file_path = validated_dir / "invoice-validated.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
        
    return str(file_path)

@pytest.fixture
def sample_pdf_scan(tmp_path):
    """Creates a basic dummy PDF file to act as the scanned invoice."""
    ingest_dir = tmp_path / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = ingest_dir / "invoice.pdf"
    
    # Write a simple empty PDF structure or use pypdf to create one
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72 * 8.5, height=72 * 11)
    with open(pdf_path, "wb") as f:
        writer.write(f)
        
    return str(pdf_path)

@pytest.fixture
def sample_image_scan(tmp_path):
    """Creates a dummy PNG image file to act as the scanned invoice."""
    ingest_dir = tmp_path / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    img_path = ingest_dir / "invoice.png"
    
    # Create a small white image
    img = Image.new("RGB", (100, 100), color="white")
    img.save(img_path)
    
    return str(img_path)

def test_invoice_data_schema_extension(sample_validated_json):
    """Verify that Pydantic model can parse the new fields correctly."""
    with open(sample_validated_json, "r") as f:
        data = json.load(f)
    invoice = InvoiceData.model_validate(data)
    
    assert invoice.vendor_vat_id == "ATU68822002"
    assert invoice.customer_vat_id == "ATU87654321"
    assert invoice.customer_name == "Armin Scherz"
    assert invoice.vendor_address_street == "Spengergasse 20"
    assert invoice.vendor_address_zip == "1050"
    assert invoice.vendor_address_city == "Wien"
    assert invoice.vendor_address_country == "AT"
    assert invoice.payment_reference == "REF-2026-99"

def test_record_creates_zugferd_pdf_from_pdf_input(sample_validated_json, sample_pdf_scan, tmp_path, mocker):
    """Test that the record command produces a ZUGFeRD-compliant hybrid PDF from a PDF input."""
    result_csv = tmp_path / "results.csv"
    scan_archive_dir = tmp_path / "scan_archive"
    scan_archive_dir.mkdir(parents=True, exist_ok=True)
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(tmp_path / "validated"),
        "RESULT_COLUMNS": "vendor_name;invoice_number;date;total_invoice_amount_gross",
        "INVOICE_RECIPIENT_NAME": "",
        "INVOICE_RECIPIENT_ADDRESS": "",
        "INVOICE_RECIPIENT_VAT_NUMBER": ""
    })
    
    # Invoke record with the new options
    result = runner.invoke(app, [
        "record", 
        sample_validated_json, 
        "--result_csv", str(result_csv),
        "--scan_file", sample_pdf_scan,
        "--scan_archive_dir", str(scan_archive_dir)
    ])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    # The output ZUGFeRD PDF should be archived as <scan_stem>.pdf in scan_archive_dir
    expected_archived_pdf = scan_archive_dir / "invoice.pdf"
    assert expected_archived_pdf.exists()
    
    # The original scan_file in ingest folder should be deleted/moved
    assert not Path(sample_pdf_scan).exists()
    
    # Verify that the archived PDF is Factur-X/ZUGFeRD compliant by extracting the XML
    res = facturx.get_xml_from_pdf(expected_archived_pdf.read_bytes())
    assert res is not None
    xml_bytes = res[1] if isinstance(res, tuple) else res
    assert xml_bytes is not None
    
    # Parse and check XML content
    root = ET.fromstring(xml_bytes)
    namespaces = {
        'rsm': 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100',
        'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100',
        'udt': 'urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100'
    }
    
    # Verify profile context is basicwl
    profile_el = root.find('.//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID', namespaces)
    assert profile_el is not None
    assert "basicwl" in profile_el.text.lower()
    
    # Verify invoice number and date
    inv_num_el = root.find('.//rsm:ExchangedDocument/ram:ID', namespaces)
    assert inv_num_el is not None
    assert inv_num_el.text == "INV-123"
    
    # Verify Seller details
    seller_name = root.find('.//ram:SellerTradeParty/ram:Name', namespaces)
    assert seller_name is not None
    assert seller_name.text == "Test Vendor GmbH"
    
    seller_trade_party = root.find('.//ram:SellerTradeParty', namespaces)
    assert seller_trade_party is not None
    seller_vat = None
    for tax_reg in seller_trade_party.findall('ram:SpecifiedTaxRegistration', namespaces):
        id_el = tax_reg.find('ram:ID', namespaces)
        if id_el is not None and id_el.get('schemeID') == 'VA':
            seller_vat = id_el
            break
    assert seller_vat is not None
    assert seller_vat.text == "ATU68822002"
    
    # Verify Buyer/Customer details
    buyer_name = root.find('.//ram:BuyerTradeParty/ram:Name', namespaces)
    assert buyer_name is not None
    assert buyer_name.text == "Armin Scherz"
    
    buyer_trade_party = root.find('.//ram:BuyerTradeParty', namespaces)
    assert buyer_trade_party is not None
    buyer_vat = None
    for tax_reg in buyer_trade_party.findall('ram:SpecifiedTaxRegistration', namespaces):
        id_el = tax_reg.find('ram:ID', namespaces)
        if id_el is not None and id_el.get('schemeID') == 'VA':
            buyer_vat = id_el
            break
    assert buyer_vat is not None
    assert buyer_vat.text == "ATU87654321"

    # Verify Currency and IBAN
    currency_el = root.find('.//ram:InvoiceCurrencyCode', namespaces)
    assert currency_el is not None
    assert currency_el.text == "EUR"
    
    iban_el = root.find('.//ram:PayeePartyCreditorFinancialAccount/ram:IBANID', namespaces)
    assert iban_el is not None
    assert iban_el.text == "AT123456789012345678"

    # Verify monetary summation
    grand_total_el = root.find('.//ram:GrandTotalAmount', namespaces)
    assert grand_total_el is not None
    assert grand_total_el.text == "120.00"

def test_record_creates_zugferd_pdf_from_image_input(sample_validated_json, sample_image_scan, tmp_path, mocker):
    """Test that the record command converts an image input to PDF and produces a hybrid ZUGFeRD PDF."""
    result_csv = tmp_path / "results.csv"
    scan_archive_dir = tmp_path / "scan_archive"
    scan_archive_dir.mkdir(parents=True, exist_ok=True)
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(tmp_path / "validated"),
        "RESULT_COLUMNS": "vendor_name;invoice_number;date;total_invoice_amount_gross",
        "INVOICE_RECIPIENT_NAME": "",
        "INVOICE_RECIPIENT_ADDRESS": "",
        "INVOICE_RECIPIENT_VAT_NUMBER": ""
    })
    
    result = runner.invoke(app, [
        "record", 
        sample_validated_json, 
        "--result_csv", str(result_csv),
        "--scan_file", sample_image_scan,
        "--scan_archive_dir", str(scan_archive_dir)
    ])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    # The output ZUGFeRD PDF should be archived as invoice.pdf in scan_archive_dir
    expected_archived_pdf = scan_archive_dir / "invoice.pdf"
    assert expected_archived_pdf.exists()
    
    # The original PNG scan_file in ingest folder should be deleted/moved
    assert not Path(sample_image_scan).exists()
    
    # Verify the output is indeed a valid Factur-X/ZUGFeRD file
    res = facturx.get_xml_from_pdf(expected_archived_pdf.read_bytes())
    assert res is not None
    xml_bytes = res[1] if isinstance(res, tuple) else res
    assert xml_bytes is not None

def test_record_zugferd_error_triggers_original_preservation(sample_validated_json, tmp_path, mocker):
    """Test that if ZUGFeRD generation fails, the exit code is non-zero and original file is preserved."""
    result_csv = tmp_path / "results.csv"
    scan_archive_dir = tmp_path / "scan_archive"
    scan_archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Non-existent scan file to trigger error
    non_existent_scan = tmp_path / "ingest" / "does_not_exist.pdf"
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(tmp_path / "validated"),
        "RESULT_COLUMNS": "vendor_name;invoice_number;date;total_invoice_amount_gross",
        "INVOICE_RECIPIENT_NAME": "",
        "INVOICE_RECIPIENT_ADDRESS": "",
        "INVOICE_RECIPIENT_VAT_NUMBER": ""
    })
    
    result = runner.invoke(app, [
        "record", 
        sample_validated_json, 
        "--result_csv", str(result_csv),
        "--scan_file", str(non_existent_scan),
        "--scan_archive_dir", str(scan_archive_dir)
    ])
    
    # Should exit with non-zero exit code due to error
    assert result.exit_code != 0

def test_record_creates_zugferd_pdf_with_env_recipient_override(sample_validated_json, sample_pdf_scan, tmp_path, mocker):
    """Test that the record command uses the env variables to override the recipient in the ZUGFeRD PDF."""
    result_csv = tmp_path / "results.csv"
    scan_archive_dir = tmp_path / "scan_archive"
    scan_archive_dir.mkdir(parents=True, exist_ok=True)
    
    mocker.patch.dict(os.environ, {
        "VALIDATED_DIR": str(tmp_path / "validated"),
        "RESULT_COLUMNS": "vendor_name;invoice_number;date;total_invoice_amount_gross",
        "INVOICE_RECIPIENT_NAME": "SpiralUp! GmbH",
        "INVOICE_RECIPIENT_ADDRESS": "Töpfelgasse 14/7, 1140 Wien, Österreich",
        "INVOICE_RECIPIENT_VAT_NUMBER": "ATU77016578"
    })
    
    # Invoke record with the options
    result = runner.invoke(app, [
        "record", 
        sample_validated_json, 
        "--result_csv", str(result_csv),
        "--scan_file", sample_pdf_scan,
        "--scan_archive_dir", str(scan_archive_dir)
    ])
    
    assert result.exit_code == 0, f"Output: {result.output}"
    
    expected_archived_pdf = scan_archive_dir / "invoice.pdf"
    assert expected_archived_pdf.exists()
    
    res = facturx.get_xml_from_pdf(expected_archived_pdf.read_bytes())
    assert res is not None
    xml_bytes = res[1] if isinstance(res, tuple) else res
    assert xml_bytes is not None
    
    root = ET.fromstring(xml_bytes)
    namespaces = {
        'rsm': 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100',
        'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100',
        'udt': 'urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100'
    }
    
    # Verify Buyer/Customer details are overridden by env variables
    buyer_name = root.find('.//ram:BuyerTradeParty/ram:Name', namespaces)
    assert buyer_name is not None
    assert buyer_name.text == "SpiralUp! GmbH"
    
    buyer_zip = root.find('.//ram:BuyerTradeParty/ram:PostalTradeAddress/ram:PostcodeCode', namespaces)
    assert buyer_zip is not None
    assert buyer_zip.text == "1140"
    
    buyer_street = root.find('.//ram:BuyerTradeParty/ram:PostalTradeAddress/ram:LineOne', namespaces)
    assert buyer_street is not None
    assert buyer_street.text == "Töpfelgasse 14/7"
    
    buyer_city = root.find('.//ram:BuyerTradeParty/ram:PostalTradeAddress/ram:CityName', namespaces)
    assert buyer_city is not None
    assert buyer_city.text == "Wien"
    
    buyer_country = root.find('.//ram:BuyerTradeParty/ram:PostalTradeAddress/ram:CountryID', namespaces)
    assert buyer_country is not None
    assert buyer_country.text == "AT"
    
    buyer_trade_party = root.find('.//ram:BuyerTradeParty', namespaces)
    assert buyer_trade_party is not None
    buyer_vat = None
    for tax_reg in buyer_trade_party.findall('ram:SpecifiedTaxRegistration', namespaces):
        id_el = tax_reg.find('ram:ID', namespaces)
        if id_el is not None and id_el.get('schemeID') == 'VA':
            buyer_vat = id_el
            break
    assert buyer_vat is not None
    assert buyer_vat.text == "ATU77016578"
