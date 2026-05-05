import typer
from dotenv import load_dotenv
import ii_workflow.ingest as ingest
import ii_workflow.validate as validate
import ii_workflow.record as record
from loguru import logger

# Load environment variables
load_dotenv()

app = typer.Typer(
    name="ii-workflow",
    help="Incoming Invoice Processing Workflow MVP",
    add_completion=False,
)

# Add subcommands
app.command("ingest")(ingest.ingest_run)
app.command("validate")(validate.validate_run)
app.command("record")(record.record_run)

import ii_workflow.process as process_module

@app.command("process")
def process(
    bank_statement: str = typer.Option(None, "--bank_statement", help="Path to the bank account data file (.xlsx)."),
    result_csv: str = typer.Option("invoices_record.csv", "--result_csv", help="Filename or path for the output CSV.")
):
    """
    Orchestrator: Combines ingest, validate, and record steps for a batch of invoices.
    """
    process_module.process_run(bank_statement=bank_statement, result_csv=result_csv)

if __name__ == "__main__":
    app()
