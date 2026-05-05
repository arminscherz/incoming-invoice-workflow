---
description: 
---

# Workflow: Run Regression Tests & Fix Findings

This workflow ensures the stability of the `incoming-invoice-workflow` by executing the full regression suite and resolving any issues discovered.

## Steps

### 1. Execute Regression Suite

Run all tests in the `tests/` directory:

```bash
source venv/bin/activate && pytest tests/
```

### 2. Analyze Failures

If any tests fail:

- Identify the failing test cases and the specific assertions that triggered the error.
- Check the failure logs (captured stdout/stderr) to understand the root cause.

### 3. Verify against MOCs

Before changing any code or tests, cross-reference the failing behavior with the established **MOC (Map of Content)** files in `mocs/`:

- `01_ingest_feature.md`
- `02_validate_feature.md`
- `03_record_feature.md`
- `04_process_feature.md`

**Important**:

- If the current code logic correctly implements the MOC but the test is outdated, update the test.
- If the code logic deviates from the MOC, fix the code.
- If there is ambiguity or a conflict between the MOC and the requirement, **stop and ask the user for clarification**.

### 4. Implement Fixes

- Apply the necessary code or test changes.
- Ensure that the fixes are robust and follow the project's coding standards.

### 5. Final Verification

Re-run the regression suite to ensure all tests pass:

```bash
source venv/bin/activate && pytest tests/
```

### 6. Inform User

Provide a summary of the results to the user, including:

- Total number of tests run.
- Any failures encountered and the steps taken to resolve them.
- Confirmation that the suite is now passing.
