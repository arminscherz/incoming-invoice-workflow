import os
import json
from pathlib import Path
import typer
from loguru import logger
from google.genai import Client
from .models import InvoiceData

app = typer.Typer(help="Ingest invoices and extract data using LLM.")

@app.command("run")
def ingest_run(
    invoice_path: str = typer.Argument(..., help="Path to the invoice file (e.g., PDF, PNG).")
):
    """
    Ingests an invoice, calls the LLM, and outputs JSON data.
    """
    invoice_file = Path(invoice_path)
    if not invoice_file.exists():
        logger.error(f"Invoice file not found: {invoice_path}")
        # According to architecture, return non-zero for errors
        raise typer.Exit(code=1)

    work_dir = Path(os.getenv("WORK_DIR", "."))
    work_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Ingesting invoice: {invoice_path}")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment.")
        raise typer.Exit(code=1)

    try:
        # Initialize the client
        client = Client(api_key=api_key)
        
        # Call Gemini with structured output
        # Using gemini-2.0-flash as it is fast and supports structured outputs well
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[invoice_file],
            config={
                "response_mime_type": "application/json",
                "response_schema": InvoiceData,
            }
        )
        
        if not response.parsed:
             logger.error("No data extracted from the invoice.")
             raise typer.Exit(code=3)

        # The SDK's .parsed attribute already returns a Pydantic object if response_schema is provided
        extracted_data = response.parsed

        output_path = work_dir / f"{invoice_file.stem}_extracted.json"
        with open(output_path, "w") as f:
            json.dump(extracted_data.model_dump(), f, indent=2)
            
        logger.info(f"Extracted data saved to {output_path}")
        typer.echo(f"Successfully processed {invoice_path}")

    except Exception as e:
        logger.error(f"Error during LLM extraction: {e}")
        # Using architecture code 1 for critical failures
        raise typer.Exit(code=1)
