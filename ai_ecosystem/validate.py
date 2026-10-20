"""`ai-ecosystem validate`: lint /core, profiles and generated outputs."""
import json
import re
import shutil
import subprocess

from . import fm, model
from .paths import CORE, PROFILES, ROOT
from .render import WINDSURF_RULE_LIMIT

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def run(check_plugin=True):
    errs, warns = [], []
    agents, skills, wfs, mcps = model.avail_agents(), model.avail_skills(), model.avail_workflows(), model.avail_mcp()

    def meta(path):
        try:
            return fm.parse(path.read_text())
        except fm.FrontmatterError as e:
            errs.append(f"{path.relative_to(ROOT)}: bad frontmatter: {e}")
            return {}, ""

    for n in skills:
        p = CORE / "skills" / n / "SKILL.md"
        m, body = meta(p)
        if m.get("name") != n:
            errs.append(f"{p.relative_to(ROOT)}: name '{m.get('name')}' must equal directory '{n}'")
        if not NAME_RE.match(n) or len(n) > 64:
            errs.append(f"{p.relative_to(ROOT)}: name must be lowercase-hyphenated, <=64 chars")
        d = str(m.get("description") or "")
        if not d:
            errs.append(f"{p.relative_to(ROOT)}: description is required")
        elif len(d) > 1024:
            errs.append(f"{p.relative_to(ROOT)}: description > 1024 chars")
        if len(body) + 400 > WINDSURF_RULE_LIMIT:
            warns.append(f"{p.relative_to(ROOT)}: body will be truncated for Windsurf ({WINDSURF_RULE_LIMIT} char rule limit)")
    for n in agents:
        p = CORE / "agents" / f"{n}.md"
        m, _ = meta(p)
        if m.get("name") != n:
            errs.append(f"{p.relative_to(ROOT)}: name must equal file name")
        if not m.get("description"):
            errs.append(f"{p.relative_to(ROOT)}: description is required")
        if "readonly" in m and not isinstance(m["readonly"], bool):
            errs.append(f"{p.relative_to(ROOT)}: readonly must be true/false")
        for h in m.get("handoffs", []) or []:
            if h not in agents:
                errs.append(f"{p.relative_to(ROOT)}: handoff to unknown agent '{h}'")
    for n in wfs:
        p = CORE / "workflows" / f"{n}.md"
        m, _ = meta(p)
        if m.get("name") != n or not m.get("description"):
            errs.append(f"{p.relative_to(ROOT)}: name (= file name) and description are required")
        for a in m.get("agents", []) or []:
            if a not in agents:
                errs.append(f"{p.relative_to(ROOT)}: unknown agent '{a}'")
        if n in skills:
            errs.append(f"{p.relative_to(ROOT)}: workflow name collides with skill '{n}' (both render as skills)")
    for n in mcps:
        p = CORE / "mcp" / f"{n}.json"
        try:
            d = json.loads(p.read_text())
        except ValueError as e:
            errs.append(f"{p.relative_to(ROOT)}: invalid JSON: {e}")
            continue
        if ("command" in d) == ("url" in d):
            errs.append(f"{p.relative_to(ROOT)}: exactly one of 'command' or 'url' is required")
        if "_" in n:
            errs.append(f"{p.relative_to(ROOT)}: server names must not contain '_' (Gemini CLI restriction)")
    vend = model.vendor_dir()
    for pr in model.profiles():
        try:
            d = model.load_profile(pr)
        except SystemExit as e:
            errs.append(f"profiles/{pr}.json: {e}")
            continue
        for k, avail in (("agents", agents), ("skills", skills), ("workflows", wfs), ("mcp", mcps)):
            for x in d.get(k, []):
                if x not in avail:
                    errs.append(f"profiles/{pr}.json: unknown {k[:-1] if k != 'mcp' else 'mcp server'} '{x}'")
        for w in d.get("workflows", []):
            if w in wfs:
                need = set(fm.parse((CORE / "workflows" / f"{w}.md").read_text())[0].get("agents", []))
                if not need <= set(d["agents"]):
                    warns.append(f"profiles/{pr}.json: workflow '{w}' skipped (needs agents {sorted(need - set(d['agents']))})")
        for x in d.get("external_skills", []):
            if vend and not model.find_external(x):
                errs.append(f"profiles/{pr}.json: external skill '{x}' not found in ai-cloud-skills ({vend})")
    if not vend:
        warns.append("ai-cloud-skills not synced; external skill references not checked (run `ai-ecosystem sync`)")
    if check_plugin:
        from . import plugin
        stale = plugin.check()
        if stale:
            errs.append("plugins/ is out of date; run `ai-ecosystem build-plugin` (" + ", ".join(stale[:5]) + ")")
        if shutil.which("claude"):
            r = subprocess.run(["claude", "plugin", "validate", str(ROOT)], capture_output=True, text=True)
            if r.returncode != 0:
                errs.append("claude plugin validate failed: " + (r.stdout + r.stderr).strip()[:500])
    return errs, warns
