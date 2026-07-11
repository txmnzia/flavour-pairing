// Produce the DEPLOYED pairing data (base + curation applied) so the ranking
// probes test what users actually see. Requires python3 on PATH — same
// dependency the deploy workflow has.
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

export default function setup() {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const root = path.resolve(here, "..", "..");
  const out = path.join(here, ".deployed.json");
  mkdirSync(here, { recursive: true });
  copyFileSync(path.join(root, "web", "public", "pairings.json"), out);
  execFileSync("python3", [
    path.join(root, "pipeline", "apply_curation_json.py"),
    path.join(root, "pipeline", "curation.json"),
    out,
  ]);
}
