# TDD Workflow with Mini Orange Concepts (MOC)

This workflow defines the iterative process for developing new features using Test-Driven Development (TDD) guided by Mini Orange Concepts (MOCs).

## 1. Requirement Gathering
The AI Agent must first ask the user for high-level functional requirements for the new feature or task.
- What is the goal?
- What are the inputs and expected outputs?
- Are there specific technical constraints?

## 2. Create Mini Orange Concept (MOC)
Based on the requirements, the AI Agent creates a new markdown file in the `mocs/` directory (e.g., `mocs/XX_feature_name.md`).
The MOC must include:
- **Goal**: High-level purpose.
- **Implementation Details**: Commands, logic steps, dependencies.
- **Testing Strategy**: Mocks required, key assertions, exit codes.

## 3. User Review and Refinement
The user reviews the MOC file. The user may manually edit the file or ask the AI Agent to refine it until the concept is finalized.

## 4. Test Creation
Once the MOC is approved, the AI Agent creates the corresponding test files in the `tests/` directory (e.g., `tests/test_feature_name.py`) using `pytest` and `pytest-mock`.
- Tests should initially fail (as the implementation is not yet done).

## 5. Initial Development
The AI Agent implements the business logic in the corresponding module (e.g., `ii_workflow/feature_name.py`).

## 6. Iterative Validation and Fixes
The AI Agent runs the tests. If any tests fail:
- Analyze the failure.
- Fix the implementation code.
- Re-run tests.
- Repeat until all tests pass.

## 7. Final Verification
The AI Agent performs a final verification (e.g., manual CLI dry-run) and updates the user.
