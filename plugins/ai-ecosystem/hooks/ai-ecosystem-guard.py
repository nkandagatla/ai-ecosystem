#!/usr/bin/env python3
"""ai-ecosystem guard hook: blocks catastrophic shell commands and requires human approval
for deploy/destroy/publish actions. Works as:
  - Claude Code PreToolUse hook (matcher "Bash"): JSON with tool_input.command on stdin.
  - Cursor beforeShellExecution hook: JSON with "command" on stdin.
Stdlib only. Customize with AI_ECOSYSTEM_GUARD=off (disable) or extra regexes in
AI_ECOSYSTEM_GUARD_DENY / AI_ECOSYSTEM_GUARD_ASK (separated by ';;').
"""
import json
import os
import re
import sys

DENY = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\$HOME)(\s|$)", "recursive delete of / or home"),
    (r"\bgit\s+push\b.*(--force|-f\b).*\b(main|master)\b", "force-push to main/master"),
    (r"\bgit\s+push\b.*\b(main|master)\b.*(--force|-f\b)", "force-push to main/master"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
    (r"\bmkfs(\.\w+)?\b|\bdd\s+if=.*\bof=/dev/(sd|nvme|disk)", "disk format/overwrite"),
    (r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b", "piping remote script into a shell"),
    (r"--no-verify\b", "skipping git hooks"),
]
ASK = [
    (r"\bterraform\s+(apply|destroy)\b|\btofu\s+(apply|destroy)\b", "terraform apply/destroy"),
    (r"\bcdk\s+(deploy|destroy)\b|\bpulumi\s+(up|destroy)\b|\bsam\s+deploy\b", "infrastructure deploy/destroy"),
    (r"\baws\s+\S+\s+(delete|terminate|remove|put-bucket-policy|attach-\S*policy)", "AWS destructive/IAM change"),
    (r"\baz\s+.*\b(delete|purge)\b|\bgcloud\s+.*\bdelete\b", "cloud resource deletion"),
    (r"\bkubectl\s+(delete|drain|apply\s+.*-n\s*prod)", "kubectl delete/drain/prod apply"),
    (r"\bhelm\s+(uninstall|delete)\b", "helm uninstall"),
    (r"\bgit\s+push\b.*(--force|-f\b|--force-with-lease)", "force-push"),
    (r"\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-[a-z]*f", "discarding local changes"),
    (r"\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b|\bgh\s+release\s+create\b", "publishing a release/package"),
    (r"\bdrop\s+(database|table|schema)\b|\btruncate\s+table\b", "destructive SQL"),
]


def extra(var):
    return [(r, "custom rule") for r in os.environ.get(var, "").split(";;") if r.strip()]


def classify(cmd):
    for rx, why in DENY + extra("AI_ECOSYSTEM_GUARD_DENY"):
        if re.search(rx, cmd, re.I):
            return "deny", why
    for rx, why in ASK + extra("AI_ECOSYSTEM_GUARD_ASK"):
        if re.search(rx, cmd, re.I):
            return "ask", why
    return "allow", ""


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        data = {}
    is_cursor = "cursor_version" in data or data.get("hook_event_name") == "beforeShellExecution"
    cmd = data.get("command") or (data.get("tool_input") or {}).get("command") or ""
    decision, why = ("allow", "") if os.environ.get("AI_ECOSYSTEM_GUARD") == "off" else classify(cmd)
    msg = f"ai-ecosystem guard: {why} requires explicit human approval" if decision == "ask" else f"ai-ecosystem guard blocked: {why}"
    if is_cursor:
        out = {"permission": decision}
        if decision != "allow":
            out.update(user_message=msg, agent_message=msg + ". Ask the user before retrying.")
        print(json.dumps(out))
        return 0
    if decision == "deny":
        print(msg, file=sys.stderr)
        return 2
    if decision == "ask":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": msg}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
