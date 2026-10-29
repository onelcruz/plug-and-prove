# Copilot instructions for Plug-and-Prove

These are the runtime operating instructions for any Copilot session (chat, agent, or the
autonomous Copilot coding agent) working in this repository. Non-negotiable principles live in
`.specify/memory/constitution.md` — this file is the practical "how" that supports them.

## Before you write any code

1. Read `docs/architecture.md`. It is the authoritative design reference: components, the sensor
   adapter contract, the conformance harness's checks, the end-to-end data flow, locked design
   decisions, and open questions. Do not re-derive architecture that is already decided there.
2. Read the GitHub issue you're implementing in full, including its `Blocked by` line and
   acceptance criteria. Do not start an issue whose blockers aren't merged yet.
3. Stay inside your issue's module boundary (per `docs/architecture.md` §2's package layout) and
   its stated acceptance criteria. If you find related work that's out of scope, note it as a new
   issue instead of expanding the current one.

## While implementing

- Follow the package layout in `docs/architecture.md` §2 (`src/simulator/`, `src/adapters/`,
  `src/conformance/`, `src/fusion/`, `src/classification/`, `src/recommendation/`,
  `src/output/cot/`, `src/recordkeeping/`, `src/orchestrator.py`).
- All randomness must go through the project's single seeded RNG utility — never call
  `random`/`numpy.random` directly in simulator or test code.
- Components talk to each other only through their documented contracts (`SensorAdapter`,
  `Detection`, `OutputAdapter`, etc.). Don't reach into another component's internals.
- Every track, classification, and recommendation must carry a human-readable reason string, not
  just a label or score.
- If you resolve an open question from `docs/architecture.md` §13, or deviate from the documented
  design for a good reason, update that document in the same PR.

## Before opening a pull request

- Run the full test suite (`pytest`) locally and make sure it's green.
- Run the linter (`ruff check .`) and fix any findings.
- Make sure new code has tests covering the acceptance criteria in the issue — don't rely on
  manual verification alone unless the criterion explicitly calls for it (e.g. "manual
  verification in ATAK-CIV").

## Pull request conventions

- Title: short, descriptive, matches the issue title where practical.
- Body: reference the issue with `Closes #N` (or `Refs #N` if it's a partial step), and copy the
  issue's acceptance criteria checklist into the PR body with boxes checked for what's done.
- If you touched `docs/architecture.md`, call that out explicitly in the PR description so it's
  easy to spot in review.
- Keep PRs scoped to one issue. Don't bundle unrelated issues into a single PR.

## Commit messages

Follow the existing repo convention: a short imperative summary line, a blank line, then context
on *why* the change was made (not just what changed), and reference the issue number. Include the
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer unless explicitly
told not to.

## When something is ambiguous

If an issue's acceptance criteria and `docs/architecture.md` don't give you enough to proceed
without guessing on something that materially affects the design (not just an implementation
detail), stop and ask rather than picking an arbitrary answer and moving on silently.
