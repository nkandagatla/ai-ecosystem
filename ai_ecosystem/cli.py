"""Command line interface. `ai-ecosystem [install|uninstall|update|validate|sync|build-plugin|list] ...`"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import __version__, model
from .out import Out, remove_paths, warn
from .paths import LOCK, ROOT, STATE_HOME, default_vendor_target, vendor_dir
from .render import ALIASES, TARGETS, render, resolve_target

COMMANDS = ["install", "uninstall", "update", "validate", "sync", "build-plugin", "list"]
PROJECT_MANIFEST = ".ai-ecosystem.json"


# ---------------------------------------------------------------- prompts
def parse_selection(raw, options, aliases=None):
    """Parse '1,3', 'claude cursor', 'all'/'a', or a mix. Raises ValueError with a helpful message."""
    aliases = aliases or {}
    raw = raw.strip()
    if raw.lower() in ("a", "all", "*"):
        return list(options)
    picked, bad = [], []
    for tok in [t for t in re.split(r"[\s,]+", raw) if t]:
        low = tok.lower()
        if tok.isdigit() and 1 <= int(tok) <= len(options):
            val = options[int(tok) - 1]
        elif low in options:
            val = low
        elif aliases.get(low) in options:
            val = aliases[low]
        elif tok in options:
            val = tok
        else:
            bad.append(tok)
            continue
        if val not in picked:
            picked.append(val)
    if bad:
        raise ValueError(f"unknown choice(s): {', '.join(bad)}. Use numbers 1-{len(options)}, names, or 'all'.")
    if not picked:
        raise ValueError("select at least one option")
    return picked


def _ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        raise SystemExit("\naborted (no input)")


def ask_multi(title, options, default, aliases=None):
    print(f"\n{title}")
    for i, o in enumerate(options, 1):
        print(f"  {i}) {o}")
    while True:
        r = _ask(f"Select (numbers or names, comma separated; 'all') [{default}]: ").strip() or default
        try:
            return parse_selection(r, options, aliases)
        except ValueError as e:
            print(f"  {e}")


def ask_one(title, options, default):
    while True:
        print(f"\n{title}")
        for i, o in enumerate(options, 1):
            print(f"  {i}) {o}")
        r = _ask(f"Select a number or name [{default}]: ").strip() or default
        try:
            sel = parse_selection(r, options, model.PROFILE_ALIASES)
            if len(sel) == 1:
                return sel[0]
            print("  choose exactly one")
        except ValueError as e:
            print(f"  {e}")


def csv(v):
    return [x.strip() for x in re.split(r"[\s,]+", v) if x.strip()] if v else None


# ---------------------------------------------------------------- manifest
def manifest_path(scope, root):
    return root / PROJECT_MANIFEST if scope == "project" else STATE_HOME / "manifest.json"


def load_manifest(scope, root):
    mp = manifest_path(scope, root)
    legacy = root / PROJECT_MANIFEST
    if mp.exists():
        return json.loads(mp.read_text())
    if scope == "user" and legacy.exists():  # v1 stored the user manifest at ~/.ai-ecosystem.json
        d = json.loads(legacy.read_text())
        d["_legacy"] = str(legacy)
        return d
    return None


def normalize_manifest(m):
    """v1 manifests stored files as a list (and blocks as 'path#block')."""
    if m and isinstance(m.get("files"), list):
        files, blocks = {}, {}
        for f in m["files"]:
            if f.endswith("#block"):
                blocks[f[:-6]] = "md"
            else:
                files[f] = None
        m["files"], m["blocks"] = files, blocks
        m.setdefault("json", {})
        m.setdefault("dirs", [])
        m["targets"] = m.get("ides", [])
    return m


def do_uninstall(scope, root, force=False):
    m = normalize_manifest(load_manifest(scope, root))
    if not m:
        raise SystemExit("no ai-ecosystem manifest found; nothing to uninstall")
    files = {k: v for k, v in m["files"].items()}
    # v1 manifests have no hashes: treat as ours
    for k, v in list(files.items()):
        if v is None:
            p = root / k
            from .out import sha
            files[k] = sha(p.read_bytes()) if p.exists() else ""
    kept = remove_paths(root, files, m.get("blocks", {}), m.get("json", {}), m.get("dirs", []), keep_modified=not force)
    mp = manifest_path(scope, root)
    mp.unlink(missing_ok=True)
    if m.get("_legacy"):
        Path(m["_legacy"]).unlink(missing_ok=True)
    if scope == "user":
        try:
            STATE_HOME.rmdir()
        except OSError:
            pass
    print(f"uninstalled from {root}" + (f" (kept {len(kept)} locally modified file(s); use --force to remove)" if kept else ""))


# ---------------------------------------------------------------- sync
def read_lock():
    d = {}
    if LOCK.exists():
        for line in LOCK.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def do_sync(latest=False, dest=None):
    lock = read_lock()
    repo = lock.get("repo", "https://github.com/nkandagatla/ai-cloud-skills")
    ref = None if latest else lock.get("ref")
    dest = Path(dest) if dest else (vendor_dir() or default_vendor_target())
    dest.parent.mkdir(parents=True, exist_ok=True)
    git = ["git", "-C", str(dest)]
    if not (dest / ".git").exists():
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", repo, str(dest)], check=True)
    subprocess.run(git + ["fetch", "--quiet", "origin"], check=True)
    target = ref or subprocess.run(git + ["rev-parse", "origin/HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(git + ["-c", "advice.detachedHead=false", "checkout", "--quiet", target], check=True)
    head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if latest and LOCK.exists() and os.access(LOCK, os.W_OK):
        LOCK.write_text(f"repo={repo}\nref={head}\n")
        print(f"updated vendor.lock -> {head}")
    print(f"ai-cloud-skills @ {head[:12]} -> {dest}")


# ---------------------------------------------------------------- install
def resolve_targets(t):
    if not t or t.strip().lower() in ("all", "a", "*"):
        return list(TARGETS)
    out = []
    for x in csv(t):
        r = resolve_target(x)
        if r not in TARGETS:
            raise SystemExit(f"unknown target '{x}'; choose from {', '.join(TARGETS)} (or 'all')")
        if r not in out:
            out.append(r)
    return out


def do_install(a, interactive, prev=None):
    scope = a.scope or (ask_one("Install scope:", ["project", "user"], "project") if interactive else "project")
    root = Path(a.home if scope == "user" else a.dir).expanduser().resolve()
    prev = prev if prev is not None else normalize_manifest(load_manifest(scope, root))
    if prev and prev.get("files") and any(v is None for v in prev["files"].values()):
        # v1 manifest: hashes unknown -> treat current content as ours
        from .out import sha
        prev["files"] = {k: (sha((root / k).read_bytes()) if (root / k).exists() else "") for k in prev["files"]}
    if a.targets:
        targets = resolve_targets(a.targets)
    elif interactive:
        targets = ask_multi("Target tools:", TARGETS, "all", ALIASES)
    else:
        targets = list(TARGETS)
    pname = a.profile or (ask_one("Profile:", model.profiles(), "general") if interactive else "general")
    pname = model.PROFILE_ALIASES.get(pname, pname)
    prof = model.load_profile(pname)
    agents_all, skills_all = model.avail_agents(), model.avail_skills()
    custom = False
    if a.agents:
        prof["agents"], custom = csv(a.agents), True
    elif interactive and _ask("\nCustomize agents/skills? [y/N]: ").strip().lower() in ("y", "yes"):
        prof["agents"] = ask_multi("Agents:", agents_all, ",".join(x for x in prof["agents"]))
        custom = True
    if a.skills or (custom and interactive and not a.agents):
        if a.skills:
            chosen = csv(a.skills)
        else:
            opts = skills_all + [e for e in prof["external_skills"] if e not in skills_all]
            chosen = ask_multi("Skills:", opts, ",".join(prof["skills"] + prof["external_skills"]))
        prof["skills"] = [x for x in chosen if x in skills_all]
        prof["external_skills"] = [x for x in chosen if x not in skills_all]
        custom = True
    for x in prof["agents"]:
        if x not in agents_all:
            raise SystemExit(f"unknown agent '{x}'; available: {', '.join(agents_all)}")
    if a.mcp is not None:
        prof["mcp"] = [] if a.mcp in ("", "none") else csv(a.mcp)
        for x in prof["mcp"]:
            if x not in model.avail_mcp():
                raise SystemExit(f"unknown MCP server '{x}'; available: {', '.join(model.avail_mcp())}")
    b = model.build(pname, prof)
    opt = {"hooks": not a.no_hooks, "mcp": not a.no_mcp}
    if interactive:
        print(f"\nPlan: scope={scope} root={root}\n  targets={','.join(targets)} profile={pname}\n"
              f"  agents={','.join(b.agents)}\n  skills={','.join(b.skills)}\n  workflows={','.join(b.workflows)}\n"
              f"  mcp={','.join(b.mcp) if opt['mcp'] else 'off'} hooks={'on' if opt['hooks'] else 'off'}")
        if not a.dry_run and _ask("Proceed? [Y/n]: ").strip().lower() in ("n", "no"):
            raise SystemExit("aborted")
    if not a.dry_run:
        root.mkdir(parents=True, exist_ok=True)
    o = Out(root, a.dry_run, prev, a.force)
    render(o, b, targets, scope, opt)
    # remove stale files from a previous install that this render no longer produces
    stale = {}
    if prev:
        stale = {k: v for k, v in prev.get("files", {}).items() if k not in o.files}
        stale_blocks = {k: v for k, v in prev.get("blocks", {}).items() if k not in o.blocks}
        stale_json = {k: v for k, v in prev.get("json", {}).items() if k not in o.json}
        if not a.dry_run:
            remove_paths(root, stale, stale_blocks, stale_json, [], keep_modified=not a.force)
    if a.dry_run:
        for f in sorted(set(o.planned)):
            print("  would write", f)
        for f in sorted(stale):
            print("  would remove", f)
    else:
        man = o.manifest(version=__version__, profile=pname, scope=scope, targets=targets, custom=custom,
                         agents=list(b.agents), skills=list(b.skills), mcp=list(b.mcp) if opt["mcp"] else [],
                         hooks=opt["hooks"], root=str(root))
        mp = manifest_path(scope, root)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(man, indent=2) + "\n")
        if prev and prev.get("_legacy"):
            Path(prev["_legacy"]).unlink(missing_ok=True)
    for n in getattr(o, "notes", []):
        warn(n)
    print(f"{'[dry-run] ' if a.dry_run else ''}scope={scope} profile={pname} targets={','.join(targets)} -> {root}: "
          f"{len(set(o.planned))} paths, {len(b.agents)} agents, {len(b.skills)} skills, {len(b.workflows)} workflows, "
          f"{len(b.mcp) if opt['mcp'] else 0} mcp servers" + (f"; kept {len(o.kept)} user-modified file(s)" if o.kept else ""))


def do_update(a):
    scope = a.scope or "project"
    root = Path(a.home if scope == "user" else a.dir).expanduser().resolve()
    m = normalize_manifest(load_manifest(scope, root))
    if not m:
        raise SystemExit("nothing to update (no manifest); run install first")
    a.targets = a.targets or ",".join(m.get("targets") or m.get("ides") or [])
    a.profile = a.profile or m["profile"]
    a.scope = scope
    if m.get("custom"):
        a.agents = a.agents or ",".join(m.get("agents", []))
        a.skills = a.skills or ",".join(m.get("skills", []))
    if a.mcp is None and "mcp" in m:
        a.mcp = ",".join(m["mcp"]) or "none"
    if "hooks" in m and not m["hooks"]:
        a.no_hooks = True
    do_install(a, False, prev=m)


def do_list():
    print("Profiles:")
    for n in model.profiles():
        print(f"  {n}: {model.load_profile(n)['description']}")
    print("Targets: " + ", ".join(TARGETS))
    print("Agents: " + ", ".join(model.avail_agents()))
    print("Core skills: " + ", ".join(model.avail_skills()))
    print("Workflows: " + ", ".join(model.avail_workflows()))
    print("MCP servers: " + ", ".join(model.avail_mcp()))


def parser():
    ap = argparse.ArgumentParser(prog="ai-ecosystem",
                                 description="Install SDLC agents, skills and workflows into Claude Code, Codex, Cursor, "
                                             "GitHub Copilot, Windsurf, Gemini CLI and Kiro. Interactive unless flags + --yes are given.")
    ap.add_argument("command", nargs="?", choices=COMMANDS, default="install")
    ap.add_argument("--version", action="version", version=f"ai-ecosystem {__version__}")
    ap.add_argument("--target", "--targets", "--ide", dest="targets", help=f"comma list of {','.join(TARGETS)} or all")
    ap.add_argument("--scope", choices=["project", "user"], help="project = repo files; user = global (~/.claude, ~/.codex, ...)")
    ap.add_argument("--profile", help="profile name (see `list`); aliases: " + ", ".join(model.PROFILE_ALIASES))
    ap.add_argument("--agents", help="comma list overriding the profile's agents")
    ap.add_argument("--skills", help="comma list overriding the profile's skills (core + ai-cloud-skills)")
    ap.add_argument("--mcp", help="comma list of MCP servers overriding the profile ('none' for none)")
    ap.add_argument("--no-mcp", action="store_true", help="do not write MCP server config")
    ap.add_argument("--no-hooks", action="store_true", help="do not install the safety guard hook")
    ap.add_argument("--dir", default=".", help="project directory for --scope project (default: cwd)")
    ap.add_argument("--home", default=str(Path.home()), help="home directory for --scope user (default: $HOME)")
    ap.add_argument("--yes", "-y", action="store_true", help="non-interactive; accept defaults")
    ap.add_argument("--dry-run", action="store_true", help="print what would change; write nothing")
    ap.add_argument("--force", action="store_true", help="overwrite/remove files even if modified locally")
    ap.add_argument("--latest", action="store_true", help="sync: track ai-cloud-skills HEAD and update vendor.lock")
    ap.add_argument("--check", action="store_true", help="build-plugin: fail if committed plugin output is stale")
    # v1 flag aliases
    ap.add_argument("--uninstall", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--update", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--sync", action="store_true", help="sync ai-cloud-skills before installing")
    ap.add_argument("--list", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--validate", action="store_true", help=argparse.SUPPRESS)
    return ap


def main(argv=None):
    a = parser().parse_args(argv)
    cmd = a.command
    for flag in ("uninstall", "update", "list", "validate"):
        if getattr(a, flag):
            cmd = flag
    if a.home != str(Path.home()):
        os.environ.setdefault("AI_ECOSYSTEM_HOME", str(Path(a.home).expanduser() / ".ai-ecosystem"))
        global STATE_HOME
        STATE_HOME = Path(os.environ["AI_ECOSYSTEM_HOME"])
    interactive = sys.stdin.isatty() and not a.yes
    if cmd == "list":
        return do_list()
    if cmd == "validate":
        from . import validate
        errs, warns = validate.run()
        for w in warns:
            print("warning:", w)
        for e in errs:
            print("error:", e)
        print(f"validate: {len(errs)} error(s), {len(warns)} warning(s)")
        return 1 if errs else 0
    if cmd == "build-plugin":
        from . import plugin
        if a.check:
            d = plugin.check()
            if d:
                print("plugin output is stale:\n  " + "\n  ".join(d))
                return 1
            print("plugin output is up to date")
            return 0
        print("built", plugin.build(ROOT))
        return 0
    if cmd == "sync" or a.sync:
        do_sync(latest=a.latest)
        if cmd == "sync":
            return 0
    if cmd == "uninstall":
        scope = a.scope or (ask_one("Uninstall scope:", ["project", "user"], "project") if interactive else "project")
        return do_uninstall(scope, Path(a.home if scope == "user" else a.dir).expanduser().resolve(), a.force)
    if cmd == "update":
        return do_update(a)
    return do_install(a, interactive)


if __name__ == "__main__":
    sys.exit(main())
