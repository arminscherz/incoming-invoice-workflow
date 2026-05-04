import typer
from loguru import logger

app = typer.Typer(help="Write validated data to CSV and archive source files.")

@app.command("run")
def record_run(
    invoice_json: str = typer.Argument(..., help="Path to the validated invoice JSON."),
    csv_file: str = typer.Argument(..., help="Path to the output CSV file."),
    archive_dir: str = typer.Argument(..., help="Path to the archive folder.")
):
    """
    Writes the invoice data to the CSV and moves the source file to the archive directory.
    """
    logger.info(f"Recording {invoice_json} to {csv_file}")
    # TODO: Implement CSV writing and file archiving
    typer.echo(f"Recorded data for {invoice_json} (placeholder)")
