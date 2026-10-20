"""Render a Bundle into each tool's native layout (project or user scope).

Layouts follow the tools' official docs (see README "Layout reference")."""
import json
import re

from . import fm
from .paths import CORE

TARGETS = ["claude", "codex", "cursor", "copilot", "windsurf", "gemini", "kiro"]
ALIASES = {"github": "copilot", "vscode": "copilot", "gh": "copilot", "devin": "windsurf", "claude-code": "claude",
           "gemini-cli": "gemini", **{"." + t: t for t in TARGETS}, ".github": "copilot", ".agents": "codex"}
WINDSURF_RULE_LIMIT = 12000
WINDSURF_GLOBAL_LIMIT = 6000
GUARD = "ai-ecosystem-guard.py"
CLAUDE_READONLY_TOOLS = "Read, Grep, Glob"


def resolve_target(x):
    x = x.strip().lower()
    return ALIASES.get(x, x)


# ---------------------------------------------------------------- shared text
def handoff_text(item, b):
    hs = [h for h in item.meta.get("handoffs", []) if h in b.agents]
    if not hs:
        return ""
    return "\n## Hand off\nWhen your stage is done, summarize the artifacts you produced and hand off to: " + \
        ", ".join(f"`{h}`" for h in hs) + ".\n"


def skills_of(item, b):
    return [s for s in item.meta.get("skills", []) if s in b.skills]


def skill_list_text(item, b):
    s = skills_of(item, b)
    return ("\n## Skills to load\n" + "\n".join(f"- `{x}`" for x in s) + "\n") if s else ""


def agent_body(item, b, skill_note=True):
    return item.body.rstrip() + "\n" + (skill_list_text(item, b) if skill_note else "") + handoff_text(item, b)


def wf_body(item, args_token="$ARGUMENTS"):
    return item.body.replace("$ARGUMENTS", args_token)


def index_text(b, scope="project"):
    L = ["# AI Ecosystem", "", f"Profile: **{b.profile}** - {b.prof.get('description', '')}", "",
         "Work through the SDLC with dedicated agents. Spawn the matching subagent where your tool supports it; "
         "otherwise adopt the role described below before acting in that role.", "", "## Agents"]
    L += [f"- `{n}`: {a.meta.get('description', '')}" for n, a in b.agents.items()]
    L += ["", "## Skills"]
    L += [f"- `{n}`{' (ai-cloud-skills)' if s.origin != 'core' else ''}: {str(s.meta.get('description', ''))[:160]}" for n, s in b.skills.items()]
    if b.workflows:
        L += ["", "## Workflows"]
        L += [f"- `{n}`: {w.meta.get('description', '')} Stages: {' -> '.join(w.meta.get('agents', []))}" for n, w in b.workflows.items()]
    L += ["", "## Rules",
          "- Never commit secrets. Show a plan/diff before destructive or infrastructure changes.",
          "- Publishing, deploying, applying IaC, or sending messages requires explicit human approval.",
          "- Hand artifacts between stages through `docs/` (plan.md, adr/, test-report.md)."]
    return "\n".join(L) + "\n"


def short_index(b, limit):
    L = ["# AI Ecosystem (global)", f"Profile {b.profile}. Agents: " + ", ".join(b.agents) + ".",
         "Skills: " + ", ".join(b.skills) + ".",
         "Workflows: " + ", ".join(b.workflows) + "." if b.workflows else "",
         "Rules: never commit secrets; show a plan before destructive/IaC changes; deploy/publish/apply needs explicit human approval."]
    t = "\n".join(x for x in L if x) + "\n"
    return t if len(t) <= limit else t[: limit - 20] + "\n...(truncated)\n"


def limit_text(text, limit, where):
    if len(text) <= limit:
        return text
    note = f"\n\n...(truncated to fit the {limit}-character limit; full text: {where})\n"
    return text[: limit - len(note)] + note


def workflow_skill_md(w, args_token):
    meta = {"name": w.name, "description": f"Workflow: {w.meta.get('description', '')} Run when the user asks to {w.name.replace('-', ' ')}."}
    return fm.render(meta, wf_body(w, args_token))


def toml_str(s):
    return json.dumps(s)  # TOML basic strings are JSON-compatible for our content


def toml_multiline(s):
    if "'''" not in s:
        return "'''\n" + s + "'''"
    return '"""\n' + s.replace("\\", "\\\\").replace('"""', '\\"""') + '"""'


# ---------------------------------------------------------------- MCP formats
def env_ref(v, style):
    """Convert ${VAR} references to the target's interpolation syntax."""
    if style == "vscode":
        return re.sub(r"\$\{(\w+)\}", r"${env:\1}", v)
    return v


def mcp_entry(d, flavor):
    remote = "url" in d
    style = "vscode" if flavor in ("cursor", "copilot") else "plain"
    env = {k: env_ref(v, style) for k, v in d.get("env", {}).items()}
    if flavor == "claude":
        e = {"type": "http", "url": d["url"]} if remote else {"command": d["command"], "args": d.get("args", [])}
    elif flavor == "copilot":
        e = {"type": "http", "url": d["url"]} if remote else {"type": "stdio", "command": d["command"], "args": d.get("args", [])}
    elif flavor == "gemini":
        e = {"httpUrl": d["url"]} if remote else {"command": d["command"], "args": d.get("args", [])}
    else:  # cursor, kiro
        e = {"url": d["url"]} if remote else {"command": d["command"], "args": d.get("args", [])}
    if env and not remote:
        e["env"] = env
    return e


def codex_mcp_toml(b, existing=""):
    out = []
    for n, d in b.mcp.items():
        key = n.replace("-", "_")
        if re.search(rf"^\[mcp_servers\.{re.escape(key)}\]", existing, re.M):
            continue
        out.append(f"[mcp_servers.{key}]")
        if "url" in d:
            out.append(f"url = {toml_str(d['url'])}")
        else:
            out.append(f"command = {toml_str(d['command'])}")
            out.append("args = [" + ", ".join(toml_str(a) for a in d.get("args", [])) + "]")
            fwd = [k for k, v in d.get("env", {}).items() if v == "${" + k + "}"]
            lit = {k: v for k, v in d.get("env", {}).items() if k not in fwd}
            if fwd:
                out.append(f"# needs {', '.join(fwd)} exported in the environment Codex runs in")
            if lit:
                out.append("env = { " + ", ".join(f"{k} = {toml_str(v)}" for k, v in lit.items()) + " }")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- targets
def shared_skills(o, b, base):
    """Agent Skills standard dir (.agents/skills) read by Codex, Copilot/VS Code and Cursor."""
    for n, s in b.skills.items():
        o.copytree(f"{base}/{n}", s.src)
    for n, w in b.workflows.items():
        o.write(f"{base}/{n}/SKILL.md", workflow_skill_md(w, "the user's request"))


def install_guard(o, rel):
    o.write(rel, (CORE / "hooks" / GUARD).read_bytes(), mode=0o755)


def r_claude(o, b, scope, opt):
    for n, a in b.agents.items():
        meta = {"name": n, "description": a.meta["description"]}
        if a.meta.get("readonly"):
            meta["tools"] = CLAUDE_READONLY_TOOLS
        if a.meta.get("model"):
            meta["model"] = a.meta["model"]
        sk = skills_of(a, b)
        if sk:
            meta["skills"] = sk
        o.write(f".claude/agents/{n}.md", fm.render(meta, agent_body(a, b, skill_note=False)))
    for n, s in b.skills.items():
        o.copytree(f".claude/skills/{n}", s.src)
    for n, w in b.workflows.items():
        meta = {"name": n, "description": "Workflow: " + w.meta.get("description", ""),
                "argument-hint": "[what to build or fix]", "disable-model-invocation": True}
        o.write(f".claude/skills/{n}/SKILL.md", fm.render(meta, wf_body(w)))
    if scope == "project":
        o.block("CLAUDE.md", "@AGENTS.md")
    else:
        o.block(".claude/CLAUDE.md", index_text(b, scope))
    if opt["hooks"]:
        install_guard(o, f".claude/hooks/{GUARD}")
        cmd = (f'python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/{GUARD}' if scope == "project"
               else f'python3 "$HOME"/.claude/hooks/{GUARD}')
        o.append_json(".claude/settings.json", ["hooks", "PreToolUse"],
                      {"matcher": "Bash", "hooks": [{"type": "command", "command": cmd}]})
    if opt["mcp"] and b.mcp:
        if scope == "project":
            o.merge_json(".mcp.json", ["mcpServers"], {n: mcp_entry(d, "claude") for n, d in b.mcp.items()})
        else:
            o.notes.append("Claude user-scope MCP lives in ~/.claude.json (not edited). Add with: " +
                           "; ".join(f"claude mcp add --scope user {n} -- {d['command']} {' '.join(d.get('args', []))}" if 'command' in d
                                     else f"claude mcp add --scope user --transport http {n} {d['url']}" for n, d in b.mcp.items()))


def codex_agent_toml(n, a, b):
    instr = agent_body(a, b)
    if a.meta.get("readonly"):
        instr = "You are read-only: do not modify files; report findings instead.\n\n" + instr
    lines = [f"name = {toml_str(n.replace('-', '_'))}", f"description = {toml_str(a.meta['description'])}"]
    if a.meta.get("model"):
        lines.append(f"model = {toml_str(a.meta['model'])}")
    lines.append(f"developer_instructions = {toml_multiline(instr)}")
    return "\n".join(lines) + "\n"


def r_codex(o, b, scope, opt):
    shared_skills(o, b, ".agents/skills")
    cdir = ".codex"
    for n, a in b.agents.items():
        o.write(f"{cdir}/agents/{n}.toml", codex_agent_toml(n, a, b))
    if scope == "user":
        o.block(f"{cdir}/AGENTS.md", index_text(b, scope))
    if opt["mcp"] and b.mcp:
        p = o.root / cdir / "config.toml"
        from .out import strip_block
        existing = strip_block(p.read_text(), "toml") if p.exists() else ""
        body = codex_mcp_toml(b, existing)
        if body.strip():
            o.block(f"{cdir}/config.toml", body, kind="toml")


def r_cursor(o, b, scope, opt):
    for n, a in b.agents.items():
        meta = {"name": n, "description": a.meta["description"], "model": a.meta.get("model", "inherit"),
                "readonly": bool(a.meta.get("readonly"))}
        o.write(f".cursor/agents/{n}.md", fm.render(meta, agent_body(a, b)))
    if scope == "project":
        shared_skills(o, b, ".agents/skills")
    else:
        shared_skills(o, b, ".agents/skills")  # ~/.agents/skills is read by Cursor, Codex and Copilot
    if opt["hooks"]:
        install_guard(o, f".cursor/hooks/{GUARD}")
        cmd = f"python3 .cursor/hooks/{GUARD}" if scope == "project" else f"python3 ./hooks/{GUARD}"
        o.append_json(".cursor/hooks.json", ["hooks", "beforeShellExecution"], {"command": cmd}, defaults={"version": 1})
    if opt["mcp"] and b.mcp:
        o.merge_json(".cursor/mcp.json", ["mcpServers"], {n: mcp_entry(d, "cursor") for n, d in b.mcp.items()})


def r_copilot(o, b, scope, opt):
    adir = ".github/agents" if scope == "project" else ".copilot/agents"
    for n, a in b.agents.items():
        meta = {"name": n, "description": a.meta["description"]}
        if a.meta.get("readonly"):
            meta["tools"] = ["read", "search"]
        if a.meta.get("model"):
            meta["model"] = a.meta["model"]
        hs = [h for h in a.meta.get("handoffs", []) if h in b.agents]
        if hs:
            meta["handoffs"] = [{"label": f"Hand off to {h}", "agent": h,
                                 "prompt": f"Continue as {h} using the artifacts produced above.", "send": False} for h in hs]
        o.write(f"{adir}/{n}.agent.md", fm.render(meta, agent_body(a, b)))
    shared_skills(o, b, ".agents/skills")
    if scope == "project":
        for n, w in b.workflows.items():
            o.write(f".github/prompts/{n}.prompt.md",
                    fm.render({"description": w.meta.get("description", ""), "agent": "agent"}, wf_body(w, "${input:task}")))
        o.block(".github/copilot-instructions.md",
                "Follow the AI ecosystem in `AGENTS.md`: SDLC agents live in `.github/agents/`, skills in `.agents/skills/`, "
                "workflows in `.github/prompts/`.")
        if opt["mcp"] and b.mcp:
            o.merge_json(".vscode/mcp.json", ["servers"], {n: mcp_entry(d, "copilot") for n, d in b.mcp.items()})
    elif opt["mcp"] and b.mcp:
        o.notes.append("Copilot user-scope MCP is configured in your VS Code profile (MCP: Open User Configuration); not edited.")


def r_windsurf(o, b, scope, opt):
    if scope == "user":
        o.block(".codeium/windsurf/memories/global_rules.md", short_index(b, WINDSURF_GLOBAL_LIMIT - 120))
        return
    d = ".windsurf/rules"
    for n, s in b.skills.items():
        txt = fm.render({"trigger": "model_decision", "description": str(s.meta.get("description", n))}, s.body)
        o.write(f"{d}/{n}.md", limit_text(txt, WINDSURF_RULE_LIMIT, f"{s.origin} skill {n}"))
    for n, a in b.agents.items():
        txt = fm.render({"trigger": "manual", "description": "Role: " + a.meta["description"]}, agent_body(a, b))
        o.write(f"{d}/agent-{n}.md", limit_text(txt, WINDSURF_RULE_LIMIT, f"core/agents/{n}.md"))
    for n, w in b.workflows.items():
        txt = fm.render({"description": w.meta.get("description", "")}, wf_body(w, "the user's request"))
        o.write(f".windsurf/workflows/{n}.md", limit_text(txt, WINDSURF_RULE_LIMIT, f"core/workflows/{n}.md"))


def gemini_cmd(desc, prompt):
    return f"description = {toml_str(desc)}\nprompt = {toml_multiline(prompt.rstrip() + chr(10) + chr(10) + 'Task: {{args}}' + chr(10))}\n"


def r_gemini(o, b, scope, opt):
    for n, w in b.workflows.items():
        o.write(f".gemini/commands/{n}.toml", gemini_cmd(w.meta.get("description", n), wf_body(w, "{{args}}").replace("Input: {{args}}", "").rstrip()))
    for n, a in b.agents.items():
        o.write(f".gemini/commands/agent/{n}.toml", gemini_cmd(f"Act as the {n} agent: {a.meta['description']}",
                                                               f"Adopt this role for the task.\n\n{agent_body(a, b)}"))
    for n, s in b.skills.items():
        o.write(f".gemini/commands/skill/{n}.toml", gemini_cmd(f"Apply skill {n}: {str(s.meta.get('description', ''))[:200]}", s.body))
    o.block("GEMINI.md" if scope == "project" else ".gemini/GEMINI.md",
            "@./AGENTS.md" if scope == "project" else index_text(b, scope))
    if opt["mcp"] and b.mcp:
        o.merge_json(".gemini/settings.json", ["mcpServers"], {n: mcp_entry(d, "gemini") for n, d in b.mcp.items()})


def r_kiro(o, b, scope, opt):
    d = ".kiro/steering"
    for n, s in b.skills.items():
        o.write(f"{d}/{n}.md", fm.render({"inclusion": "auto", "name": n, "description": str(s.meta.get("description", n))}, s.body))
    for n, a in b.agents.items():
        o.write(f"{d}/agent-{n}.md", fm.render({"inclusion": "manual"}, agent_body(a, b)))
    for n, w in b.workflows.items():
        o.write(f"{d}/workflow-{n}.md", fm.render({"inclusion": "manual"}, wf_body(w, "the user's request")))
    if scope == "user":
        o.block(f"{d}/AGENTS.md", index_text(b, scope))
    if opt["mcp"] and b.mcp:
        o.merge_json(".kiro/settings/mcp.json", ["mcpServers"], {n: mcp_entry(d_, "kiro") for n, d_ in b.mcp.items()})


RENDERERS = {"claude": r_claude, "codex": r_codex, "cursor": r_cursor, "copilot": r_copilot,
             "windsurf": r_windsurf, "gemini": r_gemini, "kiro": r_kiro}


def render(o, b, targets, scope, opt):
    o.notes = getattr(o, "notes", [])
    if scope == "project":
        o.block("AGENTS.md", index_text(b, scope))
    for t in targets:
        RENDERERS[t](o, b, scope, opt)
