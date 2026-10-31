# Copilot instructions — Plug-and-Prove

Principles: `.specify/memory/constitution.md`. Design source of truth: `docs/architecture.md`.
CI enforces lint (incl. RNG ban), import contracts, and tests — don't restate those rules, run them.

## Before writing code
1. Read the issue in full. If a `Blocked by` issue isn't merged, stop.
2. Read the `docs/architecture.md` sections the issue touches. Never re-decide a §12 row.
3. Triage. The issue is **unsettled** if any is true, otherwise **settled**:
   1. It resolves a §13 open question.
   2. It adds or changes a §12 locked decision.
   3. An interface, schema, algorithm, or threshold it depends on isn't pinned down in §2–§11.
   4. Two competent engineers could build materially different designs from the same criteria.
   Write the classification and the rule that fired as the first line of the PR body.

## Unsettled issues only: specs first
In `specs/<issue#>-<slug>/`, in order:
1. `/speckit-specify` — create the folder with
   `.specify/scripts/bash/create-new-feature.sh --number <issue#> --short-name <slug>`;
   confirm the folder name (the script renumbers on collision).
2. `/speckit-clarify` — every question answered in spec.md or explicitly accepted as a risk.
3. `/speckit-plan`, then `/speckit-tasks`.
4. `/speckit-analyze` — fix all CRITICAL/HIGH findings before implementing; paste its
   summary table into the PR body.
5. Implement against tasks.md. Commit all artifacts; never delete them. Add only a one-line
   pointer in `docs/architecture.md`.

## While implementing
- Stay inside the issue's package (§2). Out-of-scope gaps become new issues.
- Every track, classification, and recommendation carries a human-readable reason string.
- Geometry/numeric/filtering code needs at least one known-answer test with an externally
  derived expected value, and a round-trip test where an inverse exists. Tests that only
  re-run your own formula don't count.
- If you resolve a §13 question or deviate from the design, update `docs/architecture.md`
  in the same PR and say so in the PR body.

## Before opening a PR
Run `ruff check . && lint-imports && pytest`. All green.

## Before merging non-trivial logic
Request an independent review: `gh pr edit <N> --add-reviewer "@copilot"`. Address or
dismiss (with reasoning) every finding, and record the outcome in the PR body.
Scaffolding, config-only, and docs-only PRs skip this.

## Ambiguity
If the issue and the architecture doc leave a design-affecting choice open, stop and ask.

Commits: imperative summary, blank line, why, issue number,
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
