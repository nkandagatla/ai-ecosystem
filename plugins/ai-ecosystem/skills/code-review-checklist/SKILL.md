---
name: code-review-checklist
description: Checklist for reviewing diffs. Use when reviewing a PR or change.
---

# Code review checklist

- [ ] Meets acceptance criteria; no scope creep
- [ ] Correct error handling and edge cases
- [ ] Tests added/updated and meaningful
- [ ] No secrets, debug code, or dead code
- [ ] Readable names; functions small; no needless complexity
- [ ] Security: validation, authn/z, injection, dependency changes
- [ ] Performance: no obvious N+1 or unbounded loops
- [ ] Docs/changelog updated when behaviour changes

Label findings blocker / should-fix / nit with file:line.
