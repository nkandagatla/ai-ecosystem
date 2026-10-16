---
name: test-strategy
description: Plan and write tests across the pyramid. Use when designing or adding tests.
---

# Test strategy

- Pyramid: many unit tests, some integration, few e2e.
- Derive cases from acceptance criteria; add boundaries, empty/null, invalid input, concurrency, failure injection.
- Tests must be deterministic and independent; no sleeping on timers.
- For web UIs: component tests plus a small Playwright smoke suite (load, primary flow, a11y check).
- For IaC: lint/validate, policy-as-code, plan snapshot tests, and an ephemeral-environment apply test.
- Report: what is covered, what is not, and defects found.
