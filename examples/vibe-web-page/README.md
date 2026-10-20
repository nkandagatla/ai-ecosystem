# Example: vibe-coding a web page with the agent team

What `vibe-code-web-page` produces for: *"landing page for a neighbourhood coffee shop"*.

```bash
ai-ecosystem install --yes --target claude,cursor --profile web-app --dir .
# Claude Code:  /vibe-code-web-page landing page for a neighbourhood coffee shop
# Cursor/Codex/Copilot: ask "run the vibe-code-web-page workflow: landing page for ..." (skill in .agents/skills)
```

| Stage | Agent | Artifact |
|---|---|---|
| Plan | planner | [docs/plan.md](docs/plan.md) |
| Design | architect | [docs/adr/0001-static-site.md](docs/adr/0001-static-site.md) |
| Build | developer | [index.html](index.html) |
| Review / Test / Secure | reviewer, tester, security | findings appended to `docs/plan.md` |
| Docs / Release | docs, release | README + changelog (release waits for your approval) |

`layout.txt` lists the files the installer generated for `--target claude,cursor --profile web-app`.
