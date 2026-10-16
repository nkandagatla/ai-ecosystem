# Contributing

`core/` is the single source of truth. Never hand-edit generated IDE files; change `core/` or the renderers in `scripts/ai_ecosystem.py`.

## Add an agent
Create `core/agents/<name>.md` with frontmatter `name`, `description` (say *when* to use it), `skills: [..]`, then a body with Do / Don't / Hand off. Add it to the relevant `profiles/*.json`.

## Add a skill
Create `core/skills/<name>/SKILL.md` (frontmatter `name`, `description`). Keep it under ~100 lines and actionable. Cloud/language skills belong in [ai-cloud-skills](https://github.com/nkandagatla/ai-cloud-skills); reference them via `external_skills`.

## Add a workflow
`core/workflows/<name>.md` with `agents: [..]` and ordered stages. Any step that publishes, deploys or applies infrastructure must require human approval.

## Add an IDE
Add a `to_<ide>` renderer and register it in `IDES` and `main()`, then extend `tests/test_install.sh`.

## Before a PR
`./scripts/sync-cloud-skills.sh && ./tests/test_install.sh`
