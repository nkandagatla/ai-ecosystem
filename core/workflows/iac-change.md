---
name: iac-change
description: Plan, review, and safely roll out an infrastructure-as-code change.
agents: [planner, architect, developer, reviewer, security, devops, release]
---

# iac-change

Infrastructure change with plan-before-apply and mandatory human approval for apply.

Run the stages in order. Each stage is performed by the named agent (spawn it as a subagent where the tool supports it, otherwise adopt its role file). Each stage reads the previous stage's artifacts in `docs/` and must finish before the next begins.

1. **planner** - define the change, blast radius and rollback in docs/plan.md.
2. **architect** - confirm module/state layout and environments (ADR if new).
3. **developer** - write the IaC change; run fmt/validate.
4. **reviewer** - review code and the `plan` output.
5. **security** - run iac-security-review and policy checks; no wildcard IAM.
6. **devops** - produce the plan/diff, CI run, and apply steps. STOP: require explicit human approval before apply.
7. **release** - change record, rollback steps, post-apply verification.

Input: $ARGUMENTS
