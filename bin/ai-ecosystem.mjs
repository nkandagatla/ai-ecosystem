#!/usr/bin/env node
// npx wrapper: runs the stdlib-only Python CLI shipped in this package.
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const script = join(root, "scripts", "ai_ecosystem.py");
for (const py of process.platform === "win32" ? ["py", "python", "python3"] : ["python3", "python"]) {
  const r = spawnSync(py, [script, ...process.argv.slice(2)], { stdio: "inherit" });
  if (r.error && r.error.code === "ENOENT") continue;
  process.exit(r.status ?? 1);
}
console.error("ai-ecosystem needs Python 3.8+ on PATH (python3).");
process.exit(1);
