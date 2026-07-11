# Skill library — flavour-pairing

Permanent operational skills for maintaining this project after the original
maintainer. Each skill is a self-sufficient procedure: a capable junior (or a
smaller model) following one skill plus its referenced docs should complete
the task without corrupting data.

## Orientation — read before any task

- Read `CLAUDE.md` (repo root) first — it defines the workflow: every feature
  idea becomes a GitHub issue, only the highest-priority open issue gets
  implemented, one branch per issue, merge to `main` and push immediately when
  complete.
- `pipeline/DATA.md` is the **authoritative data reference** — read it before
  touching `pairings.json`, `curation.json`, `merges.json`, or any pipeline
  script. `pipeline/ENRICHMENT.md` is the runbook for adding a new recipe
  corpus. `AUDIT.md` is the incident history — the scar stories behind every
  hard rule in these skills.
- Tests must always be green: `python3 pipeline/validate_pairings.py` (repo
  root) and `npm test` (in `web/`) before merging any change to data files,
  pipeline scripts, or ranking code. CI (`.github/workflows/validate.yml`)
  enforces both on every push to `main` and on every PR — a bare feature-branch
  push does NOT run CI (CLAUDE.md's "every push" wording is stale on this
  point), so run the gate locally before merging.
- **Owner sign-off gates** (owner: `txmnzia`, samuelouden@gmail.com): any
  change to `pairings.json` ingredient count or names, schema changes,
  removing features, and any destructive change to data files — confirm
  before merging. Everything else: merge and push without asking.

## The skills

| Skill | Use when |
|-------|----------|
| `validate-data` | Running/interpreting the consistency suite (`validate_pairings.py` + `npm test`); a CI or vitest probe fails; deriving the current deployed ingredient count; "did I break the data?" |
| `edit-pairing-data` | Any deliberate change to `web/public/pairings.json`, `pipeline/curation.json`, `badPairs`, or `web/public/taxonomy.json` — renames, deletions, merges, taxonomy fixes (owner sign-off gates apply). |
| `enrich-corpus` | Adding a new recipe corpus to the pairing database — scraping, ingredient mapping, NPMI computation, merging into the base (follows `pipeline/ENRICHMENT.md`). |
| `tune-ranking` | Changing ranking behaviour or constants in `web/src/db.ts` (penalties, rarity, diversity, coverage); evaluating against owner judgments (issues #50/#53); dev/holdout discipline. |
| `add-feature` | Implementing a backlog issue in the React app — branch/issue workflow, i18n (EN + FR), PWA/service-worker considerations, updating behaviour probes intentionally. |
| `deploy-and-debug` | GitHub Pages deploys (`deploy.yml`), the deploy-time curation transform, service-worker/caching issues, rollback via `git revert`, "the live app is wrong/stale". |
| `curation-tools` | Fixing or extending `curate.html` / `merge.html` / `annotate.html`; adding a new standalone HTML tool; GitHub-token/save problems; merge-integrity (`recordMerge`) questions. |
| `ingredient-images` | Missing/wrong ingredient image, ghost/transparent tiles, adding images for new ingredients, licensing/attribution, running the `fetch-images.yml` workflow (issue #48). |

Skills cross-reference each other by name where tasks hand off (e.g. any data
edit ends in `validate-data`; an image fix that turns into a rename escalates
to `edit-pairing-data`).
