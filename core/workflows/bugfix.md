---
name: bugfix
description: Reproduce, fix, verify and release a bug.
agents: [tester, developer, reviewer, security, release]
---

# bugfix

Failing test first, minimal fix, review, release.

Run the stages in order. Each stage is performed by the named agent (spawn it as a subagent where the tool supports it, otherwise adopt its role file). Each stage reads the previous stage's artifacts in `docs/` and must finish before the next begins.

1. **tester** - reproduce and add a failing test.
2. **developer** - minimal fix; make the test pass.
3. **reviewer** - review for regressions.
4. **security** - check if the bug has security impact.
5. **release** - patch version, changelog, rollout.

Input: $ARGUMENTS
