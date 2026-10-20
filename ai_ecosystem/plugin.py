"""Build the Claude Code plugin + marketplace from /core (`ai-ecosystem build-plugin`)."""
import filecmp
import json
import shutil
import tempfile
from pathlib import Path

from . import __version__, model
from .out import Out
from .paths import CORE, ROOT
from .render import GUARD, render

PLUGIN = "ai-ecosystem"
REPO = "https://github.com/nkandagatla/ai-ecosystem"


def build(dest_root):
    dest_root = Path(dest_root)
    pdir = dest_root / "plugins" / PLUGIN
    if pdir.exists():
        shutil.rmtree(pdir)
    prof = {"description": "All core agents, skills and workflows", "agents": model.avail_agents(),
            "skills": model.avail_skills(), "workflows": model.avail_workflows(), "external_skills": [], "mcp": []}
    b = model.build("all", prof)
    stage = Path(tempfile.mkdtemp())
    o = Out(stage)
    o.notes = []
    from .render import r_claude
    r_claude(o, b, "plugin", {"hooks": False, "mcp": False})
    pdir.mkdir(parents=True)
    for sub in ("agents", "skills"):
        shutil.copytree(stage / ".claude" / sub, pdir / sub)
    shutil.rmtree(stage)
    (pdir / "hooks").mkdir()
    shutil.copy2(CORE / "hooks" / GUARD, pdir / "hooks" / GUARD)
    hooks = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f'python3 "${{CLAUDE_PLUGIN_ROOT}}"/hooks/{GUARD}'}]}]}}
    (pdir / "hooks" / "hooks.json").write_text(json.dumps(hooks, indent=2) + "\n")
    (pdir / ".claude-plugin").mkdir()
    (pdir / ".claude-plugin" / "plugin.json").write_text(json.dumps({
        "name": PLUGIN, "version": __version__,
        "description": "SDLC agent team (planner, architect, developer, reviewer, tester, security, devops, docs, release), "
                       "engineering skills, workflows and a safety guard hook.",
        "author": {"name": "Nithin Kandagatla"}, "homepage": REPO, "repository": REPO, "license": "MIT",
        "keywords": ["sdlc", "agents", "skills", "workflows"]}, indent=2) + "\n")
    (dest_root / ".claude-plugin").mkdir(exist_ok=True)
    (dest_root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": PLUGIN, "owner": {"name": "Nithin Kandagatla"},
        "metadata": {"description": "AI ecosystem: SDLC agents, skills and workflows", "version": __version__},
        "plugins": [{"name": PLUGIN, "source": f"./plugins/{PLUGIN}", "description": "SDLC agents, skills, workflows and guard hook",
                     "version": __version__}]}, indent=2) + "\n")
    # the CLAUDE.md block writer in r_claude is irrelevant for plugins
    return pdir


def _tree(d):
    return sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())


def check():
    """Return a list of differing paths between committed plugin output and a fresh build."""
    tmp = Path(tempfile.mkdtemp())
    build(tmp)
    diffs = []
    for rel in ("plugins/" + PLUGIN, ".claude-plugin"):
        a, b = ROOT / rel, tmp / rel
        if not a.exists():
            diffs.append(rel)
            continue
        ta, tb = _tree(a), _tree(b)
        diffs += [f"{rel}/{x}" for x in sorted(set(ta) ^ set(tb))]
        diffs += [f"{rel}/{x}" for x in sorted(set(ta) & set(tb)) if not filecmp.cmp(a / x, b / x, shallow=False)]
    shutil.rmtree(tmp)
    return diffs
