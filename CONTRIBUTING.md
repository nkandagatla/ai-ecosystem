# Contributing

`core/` is the single source of truth. Never hand-edit generated IDE files; change `core/` or the renderers in `ai_ecosystem/render.py`.

## Add an agent
Create `core/agents/<name>.md` with frontmatter `name`, `description` (say *when* to use it), `skills: [..]`, `readonly: true|false`, `handoffs: [..]` and optional `model`, then a body with Do / Don't (the hand-off section is generated). Add it to the relevant `profiles/*.json`.

## Add a skill
Create `core/skills/<name>/SKILL.md` (frontmatter `name`, `description`). Keep it under ~100 lines and actionable. Cloud/language skills belong in [ai-cloud-skills](https://github.com/nkandagatla/ai-cloud-skills); reference them via `external_skills`.

## Add a workflow
`core/workflows/<name>.md` with `agents: [..]` and ordered stages. Any step that publishes, deploys or applies infrastructure must require human approval.

## Add an MCP server
`core/mcp/<name>.json` with `command`/`args`/`env` or `url`; reference it from a profile's `mcp` list.

## Add a tool/target
Add an `r_<tool>` renderer in `ai_ecosystem/render.py`, register it in `TARGETS`/`RENDERERS`, link the official docs in the README layout table, and extend `tests/test_ecosystem.py`. Only generate formats confirmed by official docs.

## Before a PR
`./scripts/sync-cloud-skills.sh && python3 scripts/ai_ecosystem.py build-plugin && ./tests/test_install.sh`
