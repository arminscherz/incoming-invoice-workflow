import os
import json
import time
import base64
import tempfile
from pathlib import Path
import typer
from loguru import logger
from google.genai import Client, types
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from .models import InvoiceData

def get_gdrive_service():
    """Builds and returns a Google Drive service using OAuth."""
    client_id = os.getenv("GDRIVE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GDRIVE_OAUTH_CLIENT_KEY")
    token_path = os.getenv("GDRIVE_TOKEN_JSON", "token.json")

    if not client_id or not client_secret:
        logger.warning("GDRIVE_OAUTH_CLIENT_ID or GDRIVE_OAUTH_CLIENT_KEY not found. Google Drive link lookup will be skipped.")
        return None

    scopes = ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/drive.metadata.readonly"]
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Failed to refresh GDrive token: {e}")
                creds = None
        
        if not creds:
            # Construct client config from env vars
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": ["http://localhost"]
                }
            }
            try:
                flow = InstalledAppFlow.from_client_config(client_config, scopes)
                creds = flow.run_local_server(port=0)
                # Save the credentials for the next run
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error(f"Failed to perform GDrive OAuth flow: {e}")
                return None

    try:
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to build GDrive service: {e}")
        return None

def get_gdrive_folder_id(service, folder_name: str) -> str | None:
    """Searches for a folder by name on Google Drive and returns its ID."""
    if not service:
        return None
    try:
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        files = results.get('files', [])
        if files:
            return files[0].get('id')
        return None
    except Exception as e:
        logger.warning(f"Error looking up Google Drive folder '{folder_name}': {e}")
        return None

def get_gdrive_link(service, filename: str) -> str | None:
    """Searches for a file by name on Google Drive and returns its webViewLink."""
    if not service:
        return None
    
    try:
        # 1. Determine folder constraint
        folder_name = os.getenv("INGEST_DIR", "ingest")
        folder_id = get_gdrive_folder_id(service, folder_name)
        
        # 2. Build search query
        query = f"name = '{filename}' and trashed = false"
        if folder_id:
            query += f" and '{folder_id}' in parents"
            logger.info(f"Searching for '{filename}' in GDrive folder '{folder_name}' ({folder_id})")
        else:
            logger.warning(f"Could not find GDrive folder '{folder_name}'. Searching globally for '{filename}'.")

        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, webViewLink)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            return files[0].get('webViewLink')
        
        logger.info(f"File '{filename}' not found on Google Drive.")
        return None
    except Exception as e:
        logger.warning(f"Error looking up Google Drive link for '{filename}': {e}")
        return None

def clean_schema(schema: dict) -> dict:
    """Cleans a Pydantic JSON schema to be compatible with Gemini REST API Schema."""
    cleaned = {}
    for k, v in schema.items():
        if k in ("title", "default", "anyOf", "$defs"):
            continue
        if isinstance(v, dict):
            cleaned[k] = clean_schema(v)
        elif isinstance(v, list):
            cleaned[k] = [clean_schema(item) if isinstance(item, dict) else item for item in v]
        else:
            cleaned[k] = v
            
    if "anyOf" in schema:
        types_list = [t.get("type") for t in schema["anyOf"] if isinstance(t, dict) and "type" in t]
        if "null" in types_list:
            cleaned["nullable"] = True
            other_types = [t for t in types_list if t != "null"]
            if other_types:
                cleaned["type"] = other_types[0]
                
    if "type" in cleaned and isinstance(cleaned["type"], str):
        cleaned["type"] = cleaned["type"].upper()
        
    return cleaned

def ingest_run(
    invoice_path: str = typer.Argument(..., help="Path to the invoice file (e.g., PDF, PNG).")
):
    """
    Ingests an invoice, calls the LLM, and outputs JSON data.
    """
    invoice_file = Path(invoice_path)
    if not invoice_file.exists():
        # Try resolving relative to INGEST_DIR
        ingest_dir = os.getenv("INGEST_DIR", "ingest")
        resolved_path = Path.cwd() / ingest_dir / invoice_path
        if resolved_path.exists():
            invoice_file = resolved_path
        else:
            logger.error(f"Invoice file not found: {invoice_path} (also checked {resolved_path})")
            raise typer.Exit(code=1)

    # Determine mime type
    extension = invoice_file.suffix.lower()
    if extension == ".pdf":
        mime_type = "application/pdf"
    elif extension in [".png", ".jpg", ".jpeg"]:
        mime_type = f"image/{extension[1:]}".replace("jpeg", "jpeg") # just being safe
    else:
        logger.error(f"Unsupported file format: {extension}")
        raise typer.Exit(code=1)

    ingested_dir = Path(os.getenv("INGESTED_DIR", "ingested"))
    if not ingested_dir.exists():
        ingested_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Ingesting invoice: {invoice_path}")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment.")
        raise typer.Exit(code=1)

    try:
        client = Client(api_key=api_key)
        
        # In True Batch Mode, we typically need to:
        # 1. Upload the file to GCS or use the Files API if supported by the batch.
        # 2. Create a batch job.
        # 3. Poll for completion.
        
        logger.info(f"Submitting {invoice_file.name} in batch mode using Files API...")
        
        # 1. Read and base64 encode the invoice file
        with open(invoice_file, "rb") as f:
            encoded_image = base64.b64encode(f.read()).decode("utf-8")
        
        # 2. Prepare the JSONL request using manual dictionary to ensure correct REST API camelCase
        raw_schema = InvoiceData.model_json_schema()
        schema_dict = clean_schema(raw_schema)
        
        request_payload = {
            "request": {
                "systemInstruction": {
                    "parts": [
                        {
                            "text": (
                                "You are an expert at extracting structured data from invoices and receipts. "
                                "Note that the scanned image may contain both the invoice and a separate payment receipt. "
                                "If the total amounts differ between the invoice and the receipt, this is often due to tips. "
                                "In such cases, prioritize the total amount listed on the invoice for the total_invoice_amount_* fields. "
                                "Use the tip_amount field for the tip and total_payment_amount_gross for the receipt total. "
                                "Also extract the individual net amounts corresponding to each VAT level (0%, 10%, 13%, 20%)."
                            )
                        }
                    ]
                },
                "contents": [
                    {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": encoded_image
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema_dict
                }
            }
        }
        
        request_json = json.dumps(request_payload)
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as temp_jsonl:
            temp_jsonl.write(request_json + "\n")
            temp_jsonl_path = temp_jsonl.name
        
        try:
            # 3. Upload JSONL to Gemini Files API
            uploaded_file = client.files.upload(
                file=temp_jsonl_path,
                config={"mime_type": "application/jsonl"}
            )
            logger.info(f"Uploaded request file: {uploaded_file.name}")
            
            # 4. Create Batch Job using the uploaded file name
            ai_model = os.getenv("AI_MODEL", "gemini-flash-latest")
            job = client.batches.create(
                model=ai_model,
                src=uploaded_file.name
            )
            
            job_name = job.name
            logger.info(f"Batch job created: {job_name}")
            
            # 5. Polling loop
            while True:
                job_status = client.batches.get(name=job_name)
                state_str = str(job_status.state)
                logger.info(f"Job state: {state_str}")
                
                if "SUCCEEDED" in state_str or "COMPLETED" in state_str:
                    break
                elif "FAILED" in state_str or "CANCELED" in state_str:
                    logger.error(f"Batch job failed with state: {state_str}")
                    raise typer.Exit(code=1)
                
                time.sleep(30)
                
            # 6. Retrieve results from the output file
            # The output info should contain the file name for the results
            results = download_batch_results(client, job_status)
            if not results:
                 logger.error("No data extracted from the batch job.")
                 raise typer.Exit(code=3)

            extracted_data = results[0]
            
            # 7. Add Google Drive Link
            try:
                service = get_gdrive_service()
                if service:
                    link = get_gdrive_link(service, invoice_file.name)
                    if link:
                        extracted_data.gdrive_link = link
                        logger.info(f"Added GDrive link: {link}")
            except Exception as e:
                logger.warning(f"Failed to fetch GDrive link: {e}")

            output_path = ingested_dir / f"{invoice_file.stem}.json"
            with open(output_path, "w") as f:
                json.dump(extracted_data.model_dump(), f, indent=2)
                
            logger.info(f"Extracted data saved to {output_path}")
            typer.echo(str(output_path.absolute()))
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_jsonl_path):
                os.remove(temp_jsonl_path)

    except Exception as e:
        logger.error(f"Error during LLM extraction: {e}")
        # Using architecture code 1 for critical failures
        raise typer.Exit(code=1)

def download_batch_results(client: Client, job) -> list[InvoiceData]:
    """
    Helper to download and parse results from a completed batch job using the Files API.
    """
    # In the Developer API, the output file name is stored in job.dest.file_name
    output_file_name = None
    if hasattr(job, 'dest') and job.dest and job.dest.file_name:
        output_file_name = job.dest.file_name

    results = []
    
    if output_file_name:
        content_bytes = client.files.download(file=output_file_name)
        # Content is JSONL
        for line in content_bytes.decode("utf-8").splitlines():
            if not line.strip(): continue
            resp_json = json.loads(line)
            
            # Extract the text and parse into InvoiceData
            if "response" in resp_json:
                candidates = resp_json["response"].get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"]
                    data_dict = json.loads(text)
                    results.append(InvoiceData.model_validate(data_dict))
                    
    return results
