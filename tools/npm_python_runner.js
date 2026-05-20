#!/usr/bin/env node
/*
 * Cross-platform npm helper for Python ETL scripts.
 *
 * npm scripts cannot portably express "try python3, then python, then py -3".
 * This helper keeps root package.json scripts short while still working on
 * Linux/macOS and common Windows Python installations.
 */
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const mode = process.argv[2];
const rest = process.argv.slice(3);
const repoRoot = path.resolve(__dirname, "..");

const snippets = {
  cli: "import sys; sys.path.insert(0, 'src'); from metabolic_safety_etl.cli import main; raise SystemExit(main(sys.argv[1:]))",
  test: "import sys, unittest; sys.path.insert(0, 'src'); suite = unittest.defaultTestLoader.discover('tests'); result = unittest.TextTestRunner(verbosity=2).run(suite); raise SystemExit(0 if result.wasSuccessful() else 1)",
};

if (!mode || !snippets[mode]) {
  console.error("Usage: node tools/npm_python_runner.js <cli|test> [...args]");
  process.exit(2);
}

const candidates = process.platform === "win32"
  ? [
      { command: "py", prefixArgs: ["-3"] },
      { command: "python", prefixArgs: [] },
      { command: "python3", prefixArgs: [] },
    ]
  : [
      { command: "python3", prefixArgs: [] },
      { command: "python", prefixArgs: [] },
    ];

let lastError = null;
for (const candidate of candidates) {
  const args = [...candidate.prefixArgs, "-c", snippets[mode], ...rest];
  const result = spawnSync(candidate.command, args, { cwd: repoRoot, stdio: "inherit" });
  if (result.error && result.error.code === "ENOENT") {
    lastError = result.error;
    continue;
  }
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  process.exit(result.status ?? 0);
}

console.error("No Python interpreter found. Tried: " + candidates.map((item) => [item.command, ...item.prefixArgs].join(" ")).join(", "));
if (lastError) console.error(lastError.message);
process.exit(127);
