---
name: test-campaign
description: Build or extend an automated test suite for an existing codebase.
agents: [planner, tester, developer, reviewer, docs]
---

# test-campaign

Raise coverage on a target area with a strategy first, then tests, then review.

Run the stages in order. Each stage is performed by the named agent (spawn it as a subagent where the tool supports it, otherwise adopt its role file). Each stage reads the previous stage's artifacts in `docs/` and must finish before the next begins.

1. **planner** - define scope, risk areas and target coverage.
2. **tester** - write test-strategy and the case list.
3. **developer** - make code testable if needed (small refactors only).
4. **tester** - implement and run tests; report gaps and defects.
5. **reviewer** - review tests for determinism and value.
6. **docs** - document how to run the tests.

Input: $ARGUMENTS
