import os
import shutil
from pathlib import Path
import typer
from loguru import logger

from ii_workflow.ingest import ingest_run
from ii_workflow.validate import validate_run
from ii_workflow.record import record_run

def get_dir(env_var_name: str, default_name: str, work_dir: Path) -> Path:
    """Helper to get and create a directory from environment variables."""
    dir_path = Path(os.getenv(env_var_name, default_name))
    if not dir_path.is_absolute():
        dir_path = work_dir / dir_path
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path

def process_run(
    bank_statement: str = typer.Option(None, "--bank_statement", help="Path to the bank account data file (.xlsx)."),
    result_csv: str = typer.Option("invoices_record.csv", "--result_csv", help="Filename or path for the output CSV.")
):
    """
    Orchestrator: Combines ingest, validate, and record steps for a batch of invoices.
    """
    logger.info("Starting process orchestrator for batch of invoices...")
    
    work_dir = Path(os.getenv("WORK_DIR", "."))
    
    # 1. Ensure all directories exist
    ingest_dir = get_dir("INGEST_DIR", "ingest", work_dir)
    ingested_dir = get_dir("INGESTED_DIR", "ingested", work_dir)
    validated_dir = get_dir("VALIDATED_DIR", "validated", work_dir)
    json_archive_dir = get_dir("JSON_ARCHIVE_DIR", "json_archive", work_dir)
    scan_archive_dir = get_dir("SCAN_ARCHIVE_DIR", "scan_archive", work_dir)
    error_dir = get_dir("ERROR_DIR", "error", work_dir)
    
    # 2. Find bank statement if not provided via argument
    resolved_bank_stmt = bank_statement
    if not resolved_bank_stmt:
        xlsx_files = [f for f in ingest_dir.glob("*.xlsx") if not f.name.startswith("~$")]
        if xlsx_files:
            # Sort by modification time descending (youngest first)
            xlsx_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            if len(xlsx_files) > 1:
                logger.warning(f"Multiple bank statements found in {ingest_dir}. Using the youngest one: {xlsx_files[0].name}")
            else:
                logger.info(f"Auto-detected bank statement: {xlsx_files[0].name}")
            resolved_bank_stmt = str(xlsx_files[0])
            
    # 3. Iterate over supported files
    supported_extensions = {".pdf", ".png", ".jpg", ".jpeg"}
    invoice_files = [f for f in ingest_dir.iterdir() if f.is_file() and f.suffix.lower() in supported_extensions]
    
    if not invoice_files:
        logger.info(f"No invoice files found in {ingest_dir}")
        return
        
    for scan_file in invoice_files:
        logger.info(f"--- Processing {scan_file.name} ---")
        
        # Paths for intermediate and final files
        intermediate_json = ingested_dir / f"{scan_file.stem}.json"
        validated_json = validated_dir / f"{scan_file.stem}-validated.json"
        
        success = False
        try:
            # Step 1: Ingest
            logger.info("Step 1: Ingest")
            ingest_run(str(scan_file))
            
            if not intermediate_json.exists():
                logger.error(f"Ingest failed to produce {intermediate_json}")
                raise typer.Exit(code=1)
                
            # Step 2: Validate
            logger.info("Step 2: Validate")
            validate_run(str(intermediate_json), bank_statement=resolved_bank_stmt)
            
            if not validated_json.exists():
                logger.error(f"Validate failed to produce {validated_json}")
                raise typer.Exit(code=1)
                
            # Step 3: Record
            logger.info("Step 3: Record")
            # Note: A duplicate will raise typer.Exit(code=0) inside record_run
            try:
                record_run(str(validated_json), result_csv=result_csv)
            except typer.Exit as e:
                if e.exit_code != 0:
                    raise
                else:
                    logger.info("Record finished successfully (possibly as duplicate).")
                    
            success = True
            
        except typer.Exit as e:
            if e.exit_code != 0:
                logger.error(f"Processing failed for {scan_file.name} at some step.")
            else:
                # Should not happen at the top level except if record exited with 0
                success = True
        except Exception as e:
            logger.exception(f"Unexpected error processing {scan_file.name}: {e}")
            
        # 4. Archiving and Cleanup
        try:
            if success:
                logger.info(f"Archiving successful file {scan_file.name}")
                shutil.move(str(scan_file), str(scan_archive_dir / scan_file.name))
                
                if intermediate_json.exists():
                    shutil.move(str(intermediate_json), str(json_archive_dir / intermediate_json.name))
                    
                if validated_json.exists():
                    shutil.move(str(validated_json), str(json_archive_dir / validated_json.name))
            else:
                logger.warning(f"Moving failed file {scan_file.name} to ERROR_DIR")
                shutil.move(str(scan_file), str(error_dir / scan_file.name))
        except Exception as e:
            logger.error(f"Failed to move files during cleanup for {scan_file.name}: {e}")

    logger.info("Batch processing completed.")
