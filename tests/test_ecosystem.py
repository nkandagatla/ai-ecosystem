"""End-to-end and unit tests. Run: python3 -m unittest discover -s tests -v"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ai_ecosystem import fm, model  # noqa: E402
from ai_ecosystem.cli import parse_selection  # noqa: E402
from ai_ecosystem.render import ALIASES, TARGETS, WINDSURF_RULE_LIMIT  # noqa: E402

try:
    import tomllib
except ImportError:  # py<3.11
    tomllib = None

CLI = [sys.executable, str(ROOT / "scripts" / "ai_ecosystem.py")]
HAVE_VENDOR = model.vendor_dir() is not None


def run(*args, inp=None, check=True, env=None):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(CLI + list(args), input=inp, capture_output=True, text=True, env=e)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def tree(d):
    return sorted(str(p.relative_to(d)) for p in Path(d).rglob("*"))


class Tmp(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.proj = self.t / "proj"
        self.home = self.t / "home"
        self.proj.mkdir()
        self.home.mkdir()
        self.env = {"AI_ECOSYSTEM_HOME": str(self.home / ".ai-ecosystem")}

    def tearDown(self):
        shutil.rmtree(self.t)

    def install(self, *extra, scope="project"):
        return run("install", "--yes", "--scope", scope, "--dir", str(self.proj), "--home", str(self.home), *extra, env=self.env)


class TestFrontmatter(unittest.TestCase):
    def test_roundtrip(self):
        meta = {"name": "x", "description": "colon: inside, and 'quotes'", "skills": ["a", "b"], "readonly": True,
                "handoffs": [{"label": "Go", "agent": "dev", "send": False}], "text": "l1\nl2", "n": 3}
        m, b = fm.parse(fm.render(meta, "body\n"))
        self.assertEqual(m, meta)
        self.assertEqual(b, "body\n")

    def test_block_lists_and_nested(self):
        m, _ = fm.parse("---\ntools:\n  - read\n  - search\nnested:\n  k: v\n  l: [1, 2]\n---\nx")
        self.assertEqual(m, {"tools": ["read", "search"], "nested": {"k": "v", "l": [1, 2]}})

    def test_no_frontmatter(self):
        self.assertEqual(fm.parse("hello"), ({}, "hello"))

    def test_all_core_files_parse(self):
        for p in (ROOT / "core").rglob("*.md"):
            m, _ = fm.parse(p.read_text())
            self.assertTrue(m.get("name"), p)


class TestSelection(unittest.TestCase):
    def test_names_numbers_all(self):
        self.assertEqual(parse_selection("claude,cursor", TARGETS, ALIASES), ["claude", "cursor"])
        self.assertEqual(parse_selection("1, 3", TARGETS), ["claude", "cursor"])
        self.assertEqual(parse_selection("Claude .github 2", TARGETS, ALIASES), ["claude", "copilot", "codex"])
        self.assertEqual(parse_selection("all", TARGETS), TARGETS)
        self.assertEqual(parse_selection("a", TARGETS), TARGETS)
        with self.assertRaises(ValueError):
            parse_selection("claude,vim", TARGETS, ALIASES)
        with self.assertRaises(ValueError):
            parse_selection("99", TARGETS)


class TestValidate(unittest.TestCase):
    def test_validate_passes(self):
        r = run("validate")
        self.assertIn("0 error(s)", r.stdout)

    def test_plugin_up_to_date(self):
        run("build-plugin", "--check")
        pj = json.loads((ROOT / "plugins/ai-ecosystem/.claude-plugin/plugin.json").read_text())
        self.assertEqual(pj["name"], "ai-ecosystem")
        mk = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(mk["plugins"][0]["source"], "./plugins/ai-ecosystem")
        hj = json.loads((ROOT / "plugins/ai-ecosystem/hooks/hooks.json").read_text())
        self.assertIn("PreToolUse", hj["hooks"])


class TestProject(Tmp):
    def test_all_profiles_all_targets_roundtrip(self):
        for prof in model.profiles():
            with self.subTest(profile=prof):
                (self.proj / "README.md").write_text("mine\n")
                before = tree(self.proj)
                self.install("--profile", prof, "--target", "all")
                self.check_layout(prof)
                first = {p: (self.proj / p).read_bytes() for p in tree(self.proj) if (self.proj / p).is_file()}
                self.install("--profile", prof, "--target", "all")  # idempotent
                second = {p: (self.proj / p).read_bytes() for p in tree(self.proj) if (self.proj / p).is_file()}
                self.assertEqual(first, second)
                run("uninstall", "--yes", "--scope", "project", "--dir", str(self.proj), env=self.env)
                self.assertEqual(tree(self.proj), before)

    def check_layout(self, prof):
        p = self.proj
        b = model.build(prof, model.load_profile(prof))
        a0 = next(iter(b.agents))
        self.assertIn("ai-ecosystem:begin", (p / "AGENTS.md").read_text())
        self.assertIn("@AGENTS.md", (p / "CLAUDE.md").read_text())
        self.assertIn("@./AGENTS.md", (p / "GEMINI.md").read_text())
        for s in b.skills:
            for base in (".agents/skills", ".claude/skills"):
                m, _ = fm.parse((p / base / s / "SKILL.md").read_text())
                self.assertEqual(m["name"], s)
            self.assertTrue((p / ".kiro/steering" / f"{s}.md").exists())
            self.assertLessEqual(len((p / ".windsurf/rules" / f"{s}.md").read_text()), WINDSURF_RULE_LIMIT)
        for w in b.workflows:
            self.assertTrue((p / ".agents/skills" / w / "SKILL.md").exists())
            self.assertTrue((p / ".github/prompts" / f"{w}.prompt.md").exists())
            m, _ = fm.parse((p / ".github/prompts" / f"{w}.prompt.md").read_text())
            self.assertEqual(m.get("agent"), "agent")
            self.assertNotIn("mode", m)
            self.assertTrue((p / ".windsurf/workflows" / f"{w}.md").exists())
            if tomllib:
                d = tomllib.loads((p / ".gemini/commands" / f"{w}.toml").read_text())
                self.assertIn("{{args}}", d["prompt"])
        # agents
        m, _ = fm.parse((p / ".cursor/agents" / f"{a0}.md").read_text())
        self.assertIn("readonly", m)
        m, _ = fm.parse((p / ".github/agents" / f"{a0}.agent.md").read_text())
        self.assertEqual(m["name"], a0)
        if tomllib:
            for f in (p / ".codex/agents").glob("*.toml"):
                d = tomllib.loads(f.read_text())
                self.assertTrue(d["name"] and d["description"] and d["developer_instructions"])
            if (p / ".codex/config.toml").exists():
                tomllib.loads((p / ".codex/config.toml").read_text())
        if "reviewer" in b.agents:
            m, _ = fm.parse((p / ".claude/agents/reviewer.md").read_text())
            self.assertEqual(m["tools"], "Read, Grep, Glob")
            m, _ = fm.parse((p / ".github/agents/reviewer.agent.md").read_text())
            self.assertEqual(m["tools"], ["read", "search"])
        # legacy layouts must be gone
        for legacy in (".codex/skills", ".codex/prompts", ".cursor/commands", ".claude/commands", ".github/instructions"):
            self.assertFalse((p / legacy).exists(), legacy)
        # hooks + mcp
        s = json.loads((p / ".claude/settings.json").read_text())
        self.assertIn("ai-ecosystem-guard", json.dumps(s["hooks"]["PreToolUse"]))
        h = json.loads((p / ".cursor/hooks.json").read_text())
        self.assertEqual(h["version"], 1)
        if b.mcp:
            for f, key in ((".mcp.json", "mcpServers"), (".cursor/mcp.json", "mcpServers"), (".vscode/mcp.json", "servers"),
                           (".gemini/settings.json", "mcpServers"), (".kiro/settings/mcp.json", "mcpServers")):
                self.assertEqual(set(json.loads((p / f).read_text())[key]), set(b.mcp), f)

    def test_merges_preserve_user_config(self):
        (self.proj / ".claude").mkdir()
        (self.proj / ".claude/settings.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "mine"}]}]}}))
        (self.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"mine": {"command": "x"}, "playwright": {"command": "custom"}}}))
        (self.proj / "AGENTS.md").write_text("# My rules\n")
        (self.proj / ".codex").mkdir()
        (self.proj / ".codex/config.toml").write_text('model = "o3"\n\n[mcp_servers.playwright]\ncommand = "mine"\n')
        self.install("--profile", "web-app", "--target", "claude,codex")
        s = json.loads((self.proj / ".claude/settings.json").read_text())
        self.assertEqual(len(s["hooks"]["PreToolUse"]), 2)
        mcp = json.loads((self.proj / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(mcp["playwright"], {"command": "custom"})  # user's definition kept
        self.assertIn("context7", mcp)
        cfg = (self.proj / ".codex/config.toml").read_text()
        self.assertEqual(cfg.count("[mcp_servers.playwright]"), 1)
        if tomllib:
            tomllib.loads(cfg)
        run("uninstall", "--yes", "--dir", str(self.proj), env=self.env)
        self.assertEqual(json.loads((self.proj / ".claude/settings.json").read_text()),
                         {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "mine"}]}]}})
        self.assertEqual(json.loads((self.proj / ".mcp.json").read_text()), {"mcpServers": {"mine": {"command": "x"}, "playwright": {"command": "custom"}}})
        self.assertEqual((self.proj / "AGENTS.md").read_text(), "# My rules\n")
        self.assertEqual((self.proj / ".codex/config.toml").read_text().strip(), 'model = "o3"\n\n[mcp_servers.playwright]\ncommand = "mine"')

    def test_invalid_json_not_clobbered(self):
        (self.proj / ".cursor").mkdir()
        (self.proj / ".cursor/mcp.json").write_text("{ not json")
        r = self.install("--target", "cursor", "--profile", "web-app")
        self.assertIn("invalid JSON", r.stderr)
        self.assertEqual((self.proj / ".cursor/mcp.json").read_text(), "{ not json")

    def test_update_keeps_modified_and_removes_stale(self):
        self.install("--target", "claude", "--profile", "general")
        mod = self.proj / ".claude/agents/planner.md"
        mod.write_text(mod.read_text() + "\nmy tweak\n")
        self.install("--target", "claude", "--profile", "testing")  # architect not in testing
        self.assertFalse((self.proj / ".claude/agents/architect.md").exists())
        self.assertIn("my tweak", mod.read_text())
        run("update", "--yes", "--dir", str(self.proj), env=self.env)
        self.assertIn("my tweak", mod.read_text())
        run("update", "--yes", "--force", "--dir", str(self.proj), env=self.env)
        self.assertNotIn("my tweak", mod.read_text())

    def test_unowned_file_not_overwritten(self):
        (self.proj / ".claude/agents").mkdir(parents=True)
        (self.proj / ".claude/agents/planner.md").write_text("my own planner\n")
        r = self.install("--target", "claude")
        self.assertIn("not created by ai-ecosystem", r.stderr)
        self.assertEqual((self.proj / ".claude/agents/planner.md").read_text(), "my own planner\n")
        run("uninstall", "--yes", "--dir", str(self.proj), env=self.env)
        self.assertEqual((self.proj / ".claude/agents/planner.md").read_text(), "my own planner\n")

    def test_uninstall_prunes_only_created_dirs(self):
        (self.proj / ".github/workflows").mkdir(parents=True)
        (self.proj / "empty-mine").mkdir()
        self.install("--target", "copilot")
        run("uninstall", "--yes", "--dir", str(self.proj), env=self.env)
        self.assertTrue((self.proj / ".github/workflows").is_dir())
        self.assertTrue((self.proj / "empty-mine").is_dir())
        self.assertFalse((self.proj / ".github/agents").exists())

    def test_dry_run_writes_nothing(self):
        r = self.install("--dry-run", "--target", "all")
        self.assertIn("would write", r.stdout)
        self.assertEqual(tree(self.proj), [])

    def test_no_hooks_no_mcp(self):
        self.install("--target", "claude,cursor", "--profile", "web-app", "--no-hooks", "--no-mcp")
        self.assertFalse((self.proj / ".claude/settings.json").exists())
        self.assertFalse((self.proj / ".cursor/mcp.json").exists())

    def test_interactive_names(self):
        """Regression: typing names like `claude,cursor` at the Target tools prompt crashed (ValueError)."""
        if not shutil.which("script"):
            self.skipTest("util-linux `script` not available")
        # scope=1(project), targets by name (with one bad name first -> re-prompt), profile by name, no customize, proceed
        inp = "1\nclaude,vim\nclaude,cursor\nweb-app\nn\ny\n"
        cmd = " ".join(CLI + ["--dir", str(self.proj), "--home", str(self.home)])
        r = subprocess.run(["script", "-qec", cmd, "/dev/null"], input=inp, capture_output=True, text=True,
                           env=dict(os.environ, **self.env), timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("unknown choice(s): vim", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertTrue((self.proj / ".claude/agents/planner.md").exists())
        self.assertTrue((self.proj / ".cursor/agents/planner.md").exists())
        self.assertFalse((self.proj / ".github").exists())

    def test_interactive_numbers_and_all(self):
        if not shutil.which("script"):
            self.skipTest("util-linux `script` not available")
        cmd = " ".join(CLI + ["--dir", str(self.proj), "--home", str(self.home)])
        r = subprocess.run(["script", "-qec", cmd, "/dev/null"], input="1\nall\n1\nn\ny\n", capture_output=True, text=True,
                           env=dict(os.environ, **self.env), timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout)
        for d in (".claude", ".codex", ".cursor", ".github", ".windsurf", ".gemini", ".kiro"):
            self.assertTrue((self.proj / d).exists(), d)


class TestUser(Tmp):
    def test_user_scope_all_targets(self):
        before = tree(self.home)
        (self.home / ".codex").mkdir()
        (self.home / ".codex/AGENTS.md").write_text("personal\n")
        self.install("--profile", "web-app", "--target", "all", scope="user")
        h = self.home
        self.assertTrue((h / ".claude/agents/planner.md").exists())
        self.assertIn("ai-ecosystem:begin", (h / ".claude/CLAUDE.md").read_text())
        self.assertTrue((h / ".agents/skills/test-strategy/SKILL.md").exists())
        self.assertTrue((h / ".codex/agents/planner.toml").exists())
        self.assertTrue((h / ".copilot/agents/planner.agent.md").exists())
        self.assertTrue((h / ".cursor/agents/planner.md").exists())
        self.assertIn("./hooks/ai-ecosystem-guard.py", (h / ".cursor/hooks.json").read_text())
        self.assertLessEqual(len((h / ".codeium/windsurf/memories/global_rules.md").read_text()), 6000)
        self.assertTrue((h / ".gemini/commands/agent/planner.toml").exists())
        self.assertTrue((h / ".kiro/steering/AGENTS.md").exists())
        self.assertTrue((h / ".ai-ecosystem/manifest.json").exists())
        self.assertFalse((self.proj / "AGENTS.md").exists())
        self.assertFalse((h / ".claude.json").exists())
        run("uninstall", "--yes", "--scope", "user", "--home", str(h), env=self.env)
        self.assertEqual((h / ".codex/AGENTS.md").read_text(), "personal\n")
        (h / ".codex/AGENTS.md").unlink()
        (h / ".codex").rmdir()
        self.assertEqual(tree(h), before)

    def test_scopes_are_independent(self):
        self.install("--target", "claude", scope="user")
        self.install("--target", "claude", scope="project")
        run("uninstall", "--yes", "--scope", "project", "--dir", str(self.proj), env=self.env)
        self.assertTrue((self.home / ".claude/agents/planner.md").exists())
        self.assertEqual(tree(self.proj), [])


class TestGuard(unittest.TestCase):
    G = ROOT / "core/hooks/ai-ecosystem-guard.py"

    def call(self, payload):
        return subprocess.run([sys.executable, str(self.G)], input=json.dumps(payload), capture_output=True, text=True)

    def test_claude(self):
        self.assertEqual(self.call({"tool_input": {"command": "ls"}}).returncode, 0)
        r = self.call({"tool_input": {"command": "rm -rf /"}})
        self.assertEqual(r.returncode, 2)
        r = self.call({"tool_input": {"command": "terraform apply"}})
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_cursor(self):
        r = self.call({"cursor_version": "1", "hook_event_name": "beforeShellExecution", "command": "git push --force origin main"})
        self.assertEqual(json.loads(r.stdout)["permission"], "deny")
        r = self.call({"hook_event_name": "beforeShellExecution", "command": "npm test"})
        self.assertEqual(json.loads(r.stdout)["permission"], "allow")


if __name__ == "__main__":
    unittest.main()
