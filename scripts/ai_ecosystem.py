#!/usr/bin/env python3
"""Render the neutral /core + a profile into native layouts for several AI IDEs/tools. Stdlib only."""
import argparse, json, os, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDES = ["cursor", "claude", "copilot", "windsurf"]
BEGIN, END = "<!-- ai-ecosystem:begin -->", "<!-- ai-ecosystem:end -->"
MANIFEST = ".ai-ecosystem.json"


def parse_md(path):
    t = Path(path).read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", t, re.S)
    if not m:
        return {}, t
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
            meta[k.strip()] = v
    return meta, m.group(2).lstrip("\n")


def load_profile(name):
    p = ROOT / "profiles" / f"{name}.json"
    if not p.exists():
        sys.exit(f"unknown profile '{name}'. available: {', '.join(x.stem for x in (ROOT/'profiles').glob('*.json'))}")
    d = json.loads(p.read_text())
    if d.get("extends"):
        base = load_profile(d["extends"])
        for k in ("agents", "skills", "workflows", "external_skills"):
            d[k] = list(dict.fromkeys(base.get(k, []) + d.get(k, [])))
    return d


def find_external(name):
    base = ROOT / "vendor" / "ai-cloud-skills" / "skills"
    if base.exists():
        for p in base.glob(f"*/{name}/SKILL.md"):
            return p.parent
    return None


def fm(**kw):
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in kw.items() if v is not None) + "---\n\n"


def q(s):
    return json.dumps(s)


class Out:
    def __init__(self, target, dry):
        self.target, self.dry, self.files = Path(target), dry, []

    def write(self, rel, text):
        self.files.append(rel)
        if not self.dry:
            p = self.target / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)

    def copytree(self, rel, src):
        for f in Path(src).rglob("*"):
            if f.is_file():
                r = f"{rel}/{f.relative_to(src)}"
                self.files.append(r)
                if not self.dry:
                    d = self.target / r
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, d)

    def block(self, rel, text):
        """Insert/replace a managed block, preserving user content."""
        self.files.append(rel + "#block")
        if self.dry:
            return
        p = self.target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        cur = p.read_text() if p.exists() else ""
        cur = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END) + r"\n?", "", cur, flags=re.S)
        p.write_text(cur.rstrip("\n") + ("\n\n" if cur.strip() else "") + f"{BEGIN}\n{text.rstrip()}\n{END}\n")


def build(args):
    prof = load_profile(args.profile)
    agents = {n: parse_md(ROOT / "core/agents" / f"{n}.md") for n in prof["agents"]}
    skills = {n: parse_md(ROOT / "core/skills" / n / "SKILL.md") for n in prof["skills"]}
    wfs = {n: parse_md(ROOT / "core/workflows" / f"{n}.md") for n in prof["workflows"]}
    ext = {}
    for n in prof.get("external_skills", []):
        d = find_external(n)
        if d:
            ext[n] = d
        else:
            print(f"  note: external skill '{n}' not found (run ./install.sh --sync or scripts/sync-cloud-skills.sh)", file=sys.stderr)
    return prof, agents, skills, wfs, ext


def index_text(prof, agents, skills, wfs, ext):
    L = ["# AI Ecosystem", "", f"Profile: **{prof['description']}**", "",
         "Work through the SDLC with dedicated agents. Read the matching role file before acting in that role.", "", "## Agents"]
    L += [f"- `{n}`: {m.get('description','')}" for n, (m, _) in agents.items()]
    L += ["", "## Skills"] + [f"- `{n}`: {m.get('description','')}" for n, (m, _) in skills.items()]
    for n, d in ext.items():
        m, _ = parse_md(d / "SKILL.md")
        L.append(f"- `{n}` (ai-cloud-skills): {m.get('description','')[:140]}")
    L += ["", "## Workflows"] + [f"- `{n}`: {m.get('description','')} Stages: {' -> '.join(m.get('agents', []))}" for n, (m, _) in wfs.items()]
    L += ["", "## Rules", "- Never commit secrets. Show a plan/diff before destructive or infrastructure changes.",
          "- Publishing, deploying, applying IaC, or sending messages requires explicit human approval.",
          "- Hand artifacts between stages through `docs/` (plan.md, adr/)."]
    return "\n".join(L) + "\n"


def to_cursor(o, prof, agents, skills, wfs, ext):
    for n, (m, b) in agents.items():
        o.write(f".cursor/agents/{n}.md", fm(name=n, description=q(m["description"])) + b + skill_refs(m, ".cursor/rules"))
    for n, (m, b) in skills.items():
        o.write(f".cursor/rules/{n}.mdc", fm(description=q(m["description"]), alwaysApply="false") + b)
    for n, d in ext.items():
        m, b = parse_md(d / "SKILL.md")
        o.write(f".cursor/rules/{n}.mdc", fm(description=q(m.get("description", n)), alwaysApply="false") + b)
    for n, (m, b) in wfs.items():
        o.write(f".cursor/rules/workflow-{n}.mdc", fm(description=q("Workflow: " + m["description"]), alwaysApply="false") + b)
        o.write(f".cursor/commands/{n}.md", b)
    o.write(".cursor/rules/ai-ecosystem.mdc", fm(description=q("AI ecosystem index"), alwaysApply="true") + index_text(prof, agents, skills, wfs, ext))


def skill_refs(m, where):
    s = m.get("skills", [])
    return ("\n\n## Skills to load\n" + "\n".join(f"- {x}" for x in s) + "\n") if s else ""


def to_claude(o, prof, agents, skills, wfs, ext):
    for n, (m, b) in agents.items():
        o.write(f".claude/agents/{n}.md", fm(name=n, description=q(m["description"])) + b + skill_refs(m, ""))
    for n in skills:
        o.copytree(f".claude/skills/{n}", ROOT / "core/skills" / n)
    for n, d in ext.items():
        o.copytree(f".claude/skills/{n}", d)
    for n, (m, b) in wfs.items():
        o.write(f".claude/commands/{n}.md", fm(description=q(m["description"]), **{"argument-hint": q("[input]")}) + b)
    o.block("CLAUDE.md", "@AGENTS.md")


def to_copilot(o, prof, agents, skills, wfs, ext):
    o.block(".github/copilot-instructions.md", index_text(prof, agents, skills, wfs, ext))
    for n, (m, b) in agents.items():
        o.write(f".github/agents/{n}.agent.md", fm(name=n, description=q(m["description"])) + b + skill_refs(m, ""))
    for n, (m, b) in skills.items():
        o.write(f".github/instructions/{n}.instructions.md", fm(description=q(m["description"]), applyTo=q("**")) + b)
    for n, d in ext.items():
        m, b = parse_md(d / "SKILL.md")
        o.write(f".github/instructions/{n}.instructions.md", fm(description=q(m.get("description", n)), applyTo=q("**")) + b)
    for n, (m, b) in wfs.items():
        o.write(f".github/prompts/{n}.prompt.md", fm(description=q(m["description"]), mode="agent") + b)


def to_windsurf(o, prof, agents, skills, wfs, ext):
    for n, (m, b) in agents.items():
        o.write(f".windsurf/rules/agent-{n}.md", fm(trigger="model_decision", description=q("Role: " + m["description"])) + b + skill_refs(m, ""))
    for n, (m, b) in skills.items():
        o.write(f".windsurf/rules/{n}.md", fm(trigger="model_decision", description=q(m["description"])) + b)
    for n, d in ext.items():
        m, b = parse_md(d / "SKILL.md")
        o.write(f".windsurf/rules/{n}.md", fm(trigger="model_decision", description=q(m.get("description", n))) + b)
    for n, (m, b) in wfs.items():
        o.write(f".windsurf/workflows/{n}.md", fm(description=q(m["description"])) + b)
    o.write(".windsurf/rules/ai-ecosystem.md", fm(trigger="always_on") + index_text(prof, agents, skills, wfs, ext))


def uninstall(target):
    mp = target / MANIFEST
    if not mp.exists():
        sys.exit("no manifest found; nothing to uninstall")
    for rel in json.loads(mp.read_text())["files"]:
        if rel.endswith("#block"):
            p = target / rel[:-6]
            if p.exists():
                t = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END) + r"\n?", "", p.read_text(), flags=re.S).strip()
                p.unlink() if not t else p.write_text(t + "\n")
        else:
            (target / rel).unlink(missing_ok=True)
    mp.unlink()
    for d in sorted((p for p in target.rglob("*") if p.is_dir()), key=lambda x: -len(x.parts)):
        if not any(d.iterdir()):
            d.rmdir()
    print("uninstalled")


def main():
    ap = argparse.ArgumentParser(description="Install the AI ecosystem into a project")
    ap.add_argument("--ide", default="all", help="comma list of: " + ",".join(IDES) + " or all")
    ap.add_argument("--profile", default="general")
    ap.add_argument("--target", default=".", help="project directory (default: cwd)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--sync", action="store_true", help="(install.sh) sync ai-cloud-skills first")
    ap.add_argument("--list", action="store_true", help="list profiles/agents/workflows")
    args = ap.parse_args()
    target = Path(args.target).resolve()
    if args.list:
        for p in sorted((ROOT / "profiles").glob("*.json")):
            print(f"{p.stem}: {json.loads(p.read_text())['description']}")
        return
    if args.uninstall:
        return uninstall(target)
    ides = IDES if args.ide == "all" else [x.strip() for x in args.ide.split(",")]
    bad = [i for i in ides if i not in IDES]
    if bad:
        sys.exit(f"unknown ide: {bad}; choose from {IDES}")
    prof, agents, skills, wfs, ext = build(args)
    target.mkdir(parents=True, exist_ok=True)
    o = Out(target, args.dry_run)
    o.block("AGENTS.md", index_text(prof, agents, skills, wfs, ext))
    for i in ides:
        {"cursor": to_cursor, "claude": to_claude, "copilot": to_copilot, "windsurf": to_windsurf}[i](o, prof, agents, skills, wfs, ext)
    if not args.dry_run:
        (target / MANIFEST).write_text(json.dumps({"profile": args.profile, "ides": ides, "files": sorted(set(o.files))}, indent=2))
    print(f"{'[dry-run] ' if args.dry_run else ''}profile={args.profile} ides={','.join(ides)} -> {target}: {len(set(o.files))} files, {len(agents)} agents, {len(skills)+len(ext)} skills, {len(wfs)} workflows")


if __name__ == "__main__":
    main()
