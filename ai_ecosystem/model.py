"""Load profiles and neutral /core content into a Bundle."""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import fm
from .paths import CORE, PROFILES, vendor_dir

PROFILE_KEYS = ("agents", "skills", "workflows", "external_skills", "mcp")
PROFILE_ALIASES = {"iac": "infrastructure-as-code", "web": "web-app", "api": "api-backend", "k8s": "k8s-platform"}


@dataclass
class Item:
    name: str
    meta: dict
    body: str
    src: Path = None          # directory to copy (skills)
    origin: str = "core"      # core | ai-cloud-skills | workflow


@dataclass
class Bundle:
    profile: str
    prof: dict
    agents: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)      # core + external skills
    workflows: dict = field(default_factory=dict)
    mcp: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)


def read_md(path):
    return fm.parse(Path(path).read_text())


def profiles():
    return sorted(p.stem for p in PROFILES.glob("*.json"))


def load_profile(name, _seen=()):
    name = PROFILE_ALIASES.get(name, name)
    p = PROFILES / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"unknown profile '{name}'. available: {', '.join(profiles())}")
    if name in _seen:
        raise SystemExit(f"profile cycle: {' -> '.join(_seen + (name,))}")
    d = json.loads(p.read_text())
    if d.get("extends"):
        base = load_profile(d["extends"], _seen + (name,))
        for k in PROFILE_KEYS:
            d[k] = list(dict.fromkeys(base.get(k, []) + d.get(k, [])))
    for k in PROFILE_KEYS:
        d.setdefault(k, [])
    return d


def avail_agents():
    return sorted(p.stem for p in (CORE / "agents").glob("*.md"))


def avail_skills():
    return sorted(p.parent.name for p in (CORE / "skills").glob("*/SKILL.md"))


def avail_workflows():
    return sorted(p.stem for p in (CORE / "workflows").glob("*.md"))


def avail_mcp():
    return sorted(p.stem for p in (CORE / "mcp").glob("*.json"))


def find_external(name):
    v = vendor_dir()
    if v:
        for p in sorted((v / "skills").glob(f"*/{name}/SKILL.md")):
            return p.parent
    return None


def load_mcp(name):
    d = json.loads((CORE / "mcp" / f"{name}.json").read_text())
    d.setdefault("name", name)
    return d


def build(profile, prof):
    b = Bundle(profile, prof)
    for n in prof["agents"]:
        m, body = read_md(CORE / "agents" / f"{n}.md")
        b.agents[n] = Item(n, m, body)
    for n in prof["skills"]:
        d = CORE / "skills" / n
        m, body = read_md(d / "SKILL.md")
        b.skills[n] = Item(n, m, body, d)
    for n in prof["external_skills"]:
        if n in b.skills:
            continue
        d = find_external(n)
        if not d:
            b.missing.append(n)
            continue
        m, body = read_md(d / "SKILL.md")
        b.skills[n] = Item(n, m, body, d, "ai-cloud-skills")
    for n in prof["workflows"]:
        m, body = read_md(CORE / "workflows" / f"{n}.md")
        if set(m.get("agents", [])) <= set(b.agents):
            b.workflows[n] = Item(n, m, body, origin="workflow")
    for n in prof["mcp"]:
        b.mcp[n] = load_mcp(n)
    if b.missing:
        print(f"  note: {len(b.missing)} ai-cloud-skills not found ({', '.join(b.missing[:6])}{'...' if len(b.missing) > 6 else ''}); "
              "run `ai-ecosystem sync` (or ./install.sh --sync) to fetch them", file=sys.stderr)
    return b
