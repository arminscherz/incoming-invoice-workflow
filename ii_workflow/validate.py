import typer
from loguru import logger

app = typer.Typer(help="Validate extracted invoice data.")

@app.command("run")
def validate_run(
    invoice_json: str = typer.Argument(..., help="Path to the extracted invoice JSON."),
    bank_data: str = typer.Argument(..., help="Path to the bank account data file (.xlsx).")
):
    """
    Validates the invoice data and checks against the bank data to see if it's already paid.
    """
    logger.info(f"Validating invoice {invoice_json} against {bank_data}")
    # TODO: Implement validation and openpyxl logic
    typer.echo(f"Validated data for {invoice_json} (placeholder)")
