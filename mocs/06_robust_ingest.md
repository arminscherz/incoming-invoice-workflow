# MOC: Robust Ingest

## Goal

Enhance the `ingest` command to handle transient API failures and glitches by implementing retry logic for batch creation and status polling.

## Functional Requirements

- **Batch Creation Retries**: 
  - If the initial `client.batches.create` call fails with a recoverable error (e.g., network timeout, 5xx server error), retry up to 3 times.
  - Abort only if all 3 retries fail.
- **Polling Retries**:
  - If a `client.batches.get` call during the polling loop fails with a recoverable error, retry up to 3 times for *that specific polling step*.
  - If the polling fails 3 times consecutively, abort the entire job.
- **Recoverable Errors**:
  - Network connectivity issues.
  - HTTP 500, 502, 503, 504 errors from the Gemini API.
  - Specific "glitches" (e.g., empty or malformed responses that might be transient).

## Implementation Details

- **Retry Strategy**:
  - Use exponential backoff (e.g., 5s, 10s, 20s) between retries.
  - Log each retry attempt at `WARNING` level.
- **Modified Logic in `ii_workflow/ingest.py`**:
  - Wrap `client.batches.create` in a retry loop.
  - Wrap `client.batches.get` in a retry loop inside the existing `while True` polling loop.
- **Exit Codes**:
  - Maintain existing exit codes (1 for failure).

## Testing Strategy

- **Mocking**:
  - Use `pytest-mock` to simulate `side_effect` on `client.batches.create` and `client.batches.get`.
- **Test Cases**:
  - `test_ingest_batch_create_retry_success`: Mock `create` to fail twice and then succeed. Verify it completes.
  - `test_ingest_batch_create_retry_failure`: Mock `create` to fail 4 times. Verify it aborts.
  - `test_ingest_polling_retry_success`: Mock `get` to fail once in the middle of polling and then succeed. Verify it completes.
  - `test_ingest_polling_retry_failure`: Mock `get` to fail 3 times consecutively during polling. Verify it aborts.
