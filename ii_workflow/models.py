from typing import Optional
from pydantic import BaseModel, Field

class InvoiceData(BaseModel):
    vendor_name: str = Field(..., description="Name of the vendor/company issuing the invoice.")
    invoice_number: str = Field(..., description="The unique identifier/number of the invoice.")
    date: str = Field(..., description="The date of the invoice in ISO 8601 format (YYYY-MM-DD).")
    total_amount: float = Field(..., description="The total amount of the invoice including tax.")
    tax_amount_0_percent_VAT: float = Field(0.0, description="Tax amount for 0% VAT.")
    tax_amount_10_percent_VAT: float = Field(0.0, description="Tax amount for 10% VAT.")
    tax_amount_13_percent_VAT: float = Field(0.0, description="Tax amount for 13% VAT.")
    tax_amount_20_percent_VAT: float = Field(0.0, description="Tax amount for 20% VAT.")
    currency: str = Field("EUR", description="3-letter currency code (e.g., EUR, USD).")
    iban: Optional[str] = Field(None, description="The IBAN of the vendor for payment.")
