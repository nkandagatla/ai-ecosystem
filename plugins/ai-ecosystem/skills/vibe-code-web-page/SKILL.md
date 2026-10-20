---
name: vibe-code-web-page
description: "Workflow: Vibe-code a web page end to end with a dedicated agent per SDLC stage."
argument-hint: "[what to build or fix]"
disable-model-invocation: true
---

# vibe-code-web-page

Idea -> shipped web page. Pass the idea as the argument, e.g. 'landing page for a coffee shop'.

Run the stages in order. Each stage is performed by the named agent (spawn it as a subagent where the tool supports it, otherwise adopt its role file). Each stage reads the previous stage's artifacts in `docs/` and must finish before the next begins.

1. **planner** - write docs/plan.md (goal, stories, acceptance criteria) for the idea.
2. **architect** - choose the simplest stack (default: static HTML/CSS/JS), layout, ADR.
3. **developer** - implement the page in small commits; use `web-frontend-basics`.
4. **reviewer** - review the diff; send blockers back to developer.
5. **tester** - smoke test at 375px and 1280px, a11y and Lighthouse; report defects.
6. **security** - check for XSS, third-party scripts, headers, secrets.
7. **docs** - README with run/deploy instructions.
8. **release** - changelog, version, deploy checklist. Stop and ask for human approval before publishing.

Input: $ARGUMENTS
