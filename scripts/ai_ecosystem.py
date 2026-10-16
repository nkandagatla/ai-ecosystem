#!/usr/bin/env python3
"""Render the neutral /core + a profile into native layouts for several AI IDEs/tools. Stdlib only."""
import argparse, json, os, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDES = ["claude", "codex", "cursor", "copilot", "windsurf"]
ALIASES = {"github": "copilot", ".claude": "claude", ".codex": "codex", ".cursor": "cursor", ".github": "copilot", ".windsurf": "windsurf"}
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


def to_claude(o, prof, agents, skills, wfs, ext, user=False):
    for n, (m, b) in agents.items():
        o.write(f".claude/agents/{n}.md", fm(name=n, description=q(m["description"])) + b + skill_refs(m, ""))
    for n in skills:
        o.copytree(f".claude/skills/{n}", ROOT / "core/skills" / n)
    for n, d in ext.items():
        o.copytree(f".claude/skills/{n}", d)
    for n, (m, b) in wfs.items():
        o.write(f".claude/commands/{n}.md", fm(description=q(m["description"]), **{"argument-hint": q("[input]")}) + b)
    if user:
        o.block(".claude/CLAUDE.md", index_text(prof, agents, skills, wfs, ext))
    else:
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


def to_codex(o, prof, agents, skills, wfs, ext, user=False):
    """Codex reads AGENTS.md (project) / ~/.codex/AGENTS.md (user); skills and prompts live under .codex."""
    base = "" if user else ".codex/"
    for n, (m, b) in skills.items():
        o.write(f"{base}skills/{n}/SKILL.md" if user else f".codex/skills/{n}/SKILL.md", fm(name=n, description=q(m["description"])) + b)
    for n, d in ext.items():
        o.copytree(f"{base}skills/{n}" if user else f".codex/skills/{n}", d)
    for n, (m, b) in agents.items():
        o.write(f"{base}agents/{n}.md", fm(name=n, description=q(m["description"])) + b + skill_refs(m, ""))
    for n, (m, b) in wfs.items():
        o.write(f"{base}prompts/{n}.md", fm(description=q(m["description"])) + b)
    if user:
        o.block("AGENTS.md", index_text(prof, agents, skills, wfs, ext))


def to_user(ide, o, prof, agents, skills, wfs, ext):
    """User/global scope: o.target is the home directory."""
    if ide == "claude":
        to_claude(o, prof, agents, skills, wfs, ext, user=True)  # ~/.claude/*
    elif ide == "codex":
        # rooted at ~/.codex
        sub = Out(o.target / ".codex", o.dry)
        to_codex(sub, prof, agents, skills, wfs, ext, user=True)
        o.files += [".codex/" + f for f in sub.files]
    elif ide == "cursor":
        for n, (m, b) in agents.items():
            o.write(f".cursor/agents/{n}.md", fm(name=n, description=q(m["description"])) + b + skill_refs(m, ""))
        for n in skills:
            o.copytree(f".cursor/skills/{n}", ROOT / "core/skills" / n)
        for n, d in ext.items():
            o.copytree(f".cursor/skills/{n}", d)
        for n, (m, b) in wfs.items():
            o.write(f".cursor/commands/{n}.md", b)
    elif ide == "windsurf":
        w = ".codeium/windsurf"
        o.block(f"{w}/memories/global_rules.md", index_text(prof, agents, skills, wfs, ext))
        for n, (m, b) in wfs.items():
            o.write(f"{w}/global_workflows/{n}.md", fm(description=q(m["description"])) + b)
        for n, (m, b) in agents.items():
            o.write(f"{w}/global_workflows/agent-{n}.md", fm(description=q("Role: " + m["description"])) + b)
    elif ide == "copilot":
        print("  note: Copilot has no stable file-based user scope; use --scope project for .github (skipped)", file=sys.stderr)


def manifest_path(scope, target, home):
    return (home if scope == "user" else target) / MANIFEST


def uninstall(root, mp):
    if not mp.exists():
        sys.exit("no manifest found; nothing to uninstall")
    for rel in json.loads(mp.read_text())["files"]:
        if rel.endswith("#block"):
            p = root / rel[:-6]
            if p.exists():
                t = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END) + r"\n?", "", p.read_text(), flags=re.S).strip()
                p.unlink() if not t else p.write_text(t + "\n")
        else:
            (root / rel).unlink(missing_ok=True)
    mp.unlink()
    for d in sorted((p for p in root.rglob("*") if p.is_dir() and ".git" not in p.parts and not str(p).startswith(str(ROOT))), key=lambda x: -len(x.parts)):
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass
    print("uninstalled")


def ask_multi(title, options, default):
    print(f"\n{title}")
    for i, o_ in enumerate(options, 1):
        print(f"  {i}) {o_}")
    r = input(f"Select (comma numbers, 'a' = all) [{default}]: ").strip() or default
    if r.lower() == "a":
        return list(options)
    return [options[int(x) - 1] for x in re.split(r"[ ,]+", r) if x]


def ask_one(title, options, default):
    print(f"\n{title}")
    for i, o_ in enumerate(options, 1):
        print(f"  {i}) {o_}")
    r = input(f"Select [{default}]: ").strip() or default
    return options[int(r) - 1]


def csv(v):
    return [x.strip() for x in v.split(",") if x.strip()] if v else None


def main():
    ap = argparse.ArgumentParser(description="Install the AI ecosystem (interactive unless flags + --yes are given)")
    ap.add_argument("--target", "--targets", "--ide", dest="targets", help="comma list: claude,codex,cursor,copilot(.github),windsurf or all")
    ap.add_argument("--scope", choices=["project", "user"], help="project = repo-level; user = global (~/.claude, ~/.codex, ~/.cursor, ...)")
    ap.add_argument("--profile", help="general|web-app|testing|infrastructure-as-code (alias: iac)")
    ap.add_argument("--agents", help="comma list overriding the profile's agents")
    ap.add_argument("--skills", help="comma list overriding the profile's skills (core + external)")
    ap.add_argument("--dir", default=".", help="project directory for --scope project (default: cwd)")
    ap.add_argument("--home", default=str(Path.home()), help="home directory for --scope user (default: $HOME)")
    ap.add_argument("--yes", "-y", action="store_true", help="non-interactive; accept defaults for anything not given")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--update", action="store_true", help="re-render using the profile/targets recorded in the manifest")
    ap.add_argument("--sync", action="store_true", help="(install.sh) sync ai-cloud-skills first")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    interactive = sys.stdin.isatty() and not args.yes
    profiles = sorted(p.stem for p in (ROOT / "profiles").glob("*.json"))
    if args.list:
        for n in profiles:
            print(f"{n}: {load_profile(n)['description']}")
        return

    scope = args.scope or (ask_one("Install scope:", ["project", "user"], "1") if interactive else "project")
    root = Path(args.home if scope == "user" else args.dir).expanduser().resolve()
    mp = manifest_path(scope, root, root)
    if args.uninstall:
        return uninstall(root, mp)
    if args.update:
        if not mp.exists():
            sys.exit("nothing to update (no manifest); run install first")
        m = json.loads(mp.read_text())
        args.targets, args.profile = ",".join(m["ides"]), m["profile"]
        args.agents = args.agents or (",".join(m["agents"]) if m.get("custom") else None)
        args.skills = args.skills or (",".join(m["skills"]) if m.get("custom") else None)
        uninstall(root, mp)

    t = args.targets
    if not t:
        t = ",".join(ask_multi("Target tools:", IDES, "a")) if interactive else "all"
    ides = IDES if t == "all" else [ALIASES.get(x, x) for x in csv(t)]
    bad = [i for i in ides if i not in IDES]
    if bad:
        sys.exit(f"unknown target: {bad}; choose from {IDES}")
    pname = args.profile or (ask_one("Profile:", profiles, "1") if interactive else "general")
    pname = {"iac": "infrastructure-as-code"}.get(pname, pname)
    prof = load_profile(pname)
    avail_agents = sorted(p.stem for p in (ROOT / "core/agents").glob("*.md"))
    avail_skills = sorted(p.parent.name for p in (ROOT / "core/skills").glob("*/SKILL.md"))
    custom = False
    if args.agents:
        prof["agents"], custom = csv(args.agents), True
    elif interactive and input("\nCustomize agents/skills? [y/N]: ").strip().lower() == "y":
        prof["agents"] = ask_multi("Agents:", avail_agents, ",".join(str(avail_agents.index(a) + 1) for a in prof["agents"] if a in avail_agents))
        custom = True
    if args.skills or (custom and interactive):
        cur = prof["skills"] + prof.get("external_skills", [])
        if args.skills:
            chosen = csv(args.skills)
        else:
            opts = avail_skills + [e for e in prof.get("external_skills", []) if e not in avail_skills]
            chosen = ask_multi("Skills:", opts, ",".join(str(opts.index(c) + 1) for c in cur if c in opts))
        prof["skills"] = [x for x in chosen if x in avail_skills]
        prof["external_skills"] = [x for x in chosen if x not in avail_skills]
        custom = True
    for a in prof["agents"]:
        if a not in avail_agents:
            sys.exit(f"unknown agent '{a}'")
    for k in prof["skills"]:
        if k not in avail_skills:
            sys.exit(f"unknown core skill '{k}'")
    prof["workflows"] = [w for w in prof["workflows"] if set(parse_md(ROOT / "core/workflows" / f"{w}.md")[0].get("agents", [])) <= set(prof["agents"])]

    args.profile = pname
    _, agents, skills, wfs, ext = build(args)
    if interactive:
        print(f"\nPlan: scope={scope} root={root}\n  targets={','.join(ides)} profile={pname}\n  agents={','.join(agents)}\n  skills={','.join(list(skills) + list(ext))}\n  workflows={','.join(wfs)}")
        if not args.dry_run and input("Proceed? [Y/n]: ").strip().lower() == "n":
            sys.exit("aborted")
    root.mkdir(parents=True, exist_ok=True)
    o = Out(root, args.dry_run)
    if scope == "project":
        o.block("AGENTS.md", index_text(prof, agents, skills, wfs, ext))
    for i in ides:
        if scope == "user":
            to_user(i, o, prof, agents, skills, wfs, ext)
        elif i == "codex":
            to_codex(o, prof, agents, skills, wfs, ext)
        else:
            {"cursor": to_cursor, "claude": to_claude, "copilot": to_copilot, "windsurf": to_windsurf}[i](o, prof, agents, skills, wfs, ext)
    if args.dry_run:
        for f in sorted(set(o.files)):
            print("  would write", f)
    else:
        mp.write_text(json.dumps({"profile": pname, "scope": scope, "ides": ides, "custom": custom, "agents": list(agents), "skills": list(skills) + list(ext), "files": sorted(set(o.files))}, indent=2))
    print(f"{'[dry-run] ' if args.dry_run else ''}scope={scope} profile={pname} targets={','.join(ides)} -> {root}: {len(set(o.files))} files, {len(agents)} agents, {len(skills)+len(ext)} skills, {len(wfs)} workflows")


if __name__ == "__main__":
    main()
