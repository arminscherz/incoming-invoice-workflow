---
description: 
---

# TDD Workflow with Mini Orange Concepts (MOC)

This workflow defines the iterative process for developing new features using Test-Driven Development (TDD) guided by Mini Orange Concepts (MOCs).

## 1. Requirement Gathering

The AI Agent must first ask the user for high-level functional requirements for the new feature or task.

- What is the goal?
- What are the inputs and expected outputs?
- Are there specific technical constraints?

## 2. Update / create Mini Orange Concept (MOC)

Based on the requirements, the AI Agent decides whether this new feature is better described as a new, seperate MOC (for complex features, e.g. new logic, new capabilities, that touch many parts of the architecture) or as an update to existing MOCs (less complex features, e.g. new fields but existing logic). The functional changes must conform to the overall concept (.agent/context/concept.md).The AI Agent does the changes in the `mocs/` directory (e.g., `mocs/XX_feature_name.md`).
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

The AI Agent creates an implementation plan, that conforms to the overall Architecure (.agent/context/architecture.md). After user review, the AI agent implements the business logic in the corresponding module (e.g., `ii_workflow/feature_name.py`).

## 6. Iterative Validation and Fixes

The AI Agent runs the tests. If any tests fail:

- Analyze the failure.
- Fix the implementation code.
- Re-run tests.
- Repeat until all tests pass.

## 7. Final Verification

The AI Agent performs a final verification (e.g., manual CLI dry-run) to make sure the new feature is working as required. The AI agent carefully doublechecks, if the Tests, Implementation and all overarching context (.agent/context) are still aligned. If there are differences, the AI agent suggests changes to the user.
Finally the AI Agent creates a walkthough document and summarizes it to the user.
