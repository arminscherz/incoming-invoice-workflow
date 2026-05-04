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
app.add_typer(ingest.app, name="ingest")
app.add_typer(validate.app, name="validate")
app.add_typer(record.app, name="record")

@app.command()
def process():
    """
    Orchestrator: Combines ingest, validate, and record steps for a batch of invoices.
    """
    logger.info("Starting process orchestrator for batch of invoices...")
    # TODO: Implement batch logic
    typer.echo("Process completed.")

if __name__ == "__main__":
    app()
