#!/usr/bin/env node

const { execFileSync } = require("node:child_process");

const forbiddenTrackedPathspecs = [
  "build",
  "build_ddinter",
  "public",
  "mobile_pwa/dist",
  "mobile_pwa/coverage",
  ".cache",
  "node_modules",
  "mobile_pwa/node_modules",
  "data/raw/openfda_label",
  "data/raw/dailymed_spl",
  "data/raw/chembl",
  "data/raw/foodrugs",
  "data/raw/onsides",
  "data/raw/pharmgkb",
];

const ignoredSentinels = [
  "build/.generated-check",
  "build_ddinter/.generated-check",
  "public/.generated-check",
  "mobile_pwa/dist/.generated-check",
  "mobile_pwa/coverage/.generated-check",
  ".cache/.generated-check",
  "node_modules/.generated-check",
  "mobile_pwa/node_modules/.generated-check",
  "data/raw/openfda_label/.generated-check",
  "data/raw/dailymed_spl/.generated-check",
  "data/raw/chembl/.generated-check",
  "data/raw/foodrugs/.generated-check",
  "data/raw/onsides/.generated-check",
  "data/raw/pharmgkb/.generated-check",
];

function git(args, options = {}) {
  return execFileSync("git", args, {
    encoding: "utf8",
    stdio: options.stdio || ["ignore", "pipe", "pipe"],
  });
}

function fail(message, details = "") {
  console.error(message);
  if (details) {
    console.error(details.trimEnd());
  }
  process.exitCode = 1;
}

const tracked = git(["ls-files", "--", ...forbiddenTrackedPathspecs]);
if (tracked.trim()) {
  fail(
    "Generated or cache files are tracked. Remove them from git and regenerate locally/CI instead:",
    tracked,
  );
}

for (const path of ignoredSentinels) {
  try {
    git(["check-ignore", "--quiet", path], { stdio: "ignore" });
  } catch (_error) {
    fail(`Expected generated path to be ignored by .gitignore: ${path}`);
  }
}

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log("Generated output boundaries look correct.");
