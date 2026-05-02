/**
 * Resolve o Python da venv do repo e executa dump_agent_diagnostics.py (npm run dump-diags).
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const py =
  process.platform === "win32"
    ? join(root, ".venv", "Scripts", "python.exe")
    : join(root, ".venv", "bin", "python");
const script = join(root, "scripts", "dump_agent_diagnostics.py");

if (!existsSync(py)) {
  console.error(
    "Interpretador da venv nao encontrado:",
    py,
    "(crie .venv e pip install -r requirements.txt).",
  );
  process.exit(1);
}

const result = spawnSync(py, [script, ...process.argv.slice(2)], {
  stdio: "inherit",
  cwd: root,
  shell: false,
});

process.exit(result.status === null ? 1 : result.status);
