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
3. Classify the issue as **settled** or **unsettled** (see "Settled vs. unsettled" below) and say
   which rule fired in chat before proceeding. If unsettled, follow the "specs/ workflow" below
   before writing implementation code.
4. Stay inside your issue's module boundary (per `docs/architecture.md` §2's package layout) and
   its stated acceptance criteria. If you find related work that's out of scope, note it as a new
   issue instead of expanding the current one.

## Settled vs. unsettled (per constitution Principle VII)

Before claiming a sub-issue, check it against `docs/architecture.md`. It is **unsettled** if any
of the following is true:

1. It requires resolving a bullet explicitly listed in §13 (Open questions / risks).
2. It would add or change a row in §12 (Key design decisions, locked) — a genuine choice between
   real alternatives, not an implementation detail.
3. A component's interface, schema, algorithm, or threshold it depends on isn't fully pinned down
   in §2-§11 — you'd have to invent the missing part.
4. Two competent engineers implementing the same acceptance criteria could reasonably produce
   materially different, non-interchangeable designs.

Otherwise it's **settled** — every acceptance criterion already maps onto something
`docs/architecture.md` fully specifies. Sharp retroactive check: if merging the PR would require
editing §12 or §13, it was unsettled, and should have been caught before coding started.

## The specs/ workflow (unsettled issues only)

For any issue classified unsettled, before writing implementation code:

1. `/speckit-specify` → write `specs/<issue-number>-<slug>/spec.md` (what & why, grounded in the
   issue and `docs/architecture.md`). By default, feature-directory creation
   (`.specify/scripts/bash/create-new-feature.sh`) auto-numbers sequentially, not by issue number
   — invoke it with `--number <issue-number> --short-name <slug>` (zero-padded automatically,
   e.g. issue #6 → `006-<slug>`) so the folder is keyed to the GitHub issue. Note: if that number
   collides with an existing spec directory, the script auto-renumbers and prints a warning —
   confirm the resulting directory name still matches before continuing.
2. `/speckit-plan` → write `plan.md` in the same folder (how, concretely).
3. Run the `rubber-duck` pre-implementation review — as a separate agent pinned to an opus-tier
   model (see "Agent roles and model assignment" below) — against `plan.md` and `spec.md`:
   interview them relentlessly for gaps, unstated assumptions, and untested edge cases. Resolve or
   explicitly accept every question raised, then re-run the review against the revision rather
   than assuming the fix is sufficient — do this until a pass comes back clean.
4. `/speckit-tasks` → write `tasks.md` in the same folder; implement against it directly (not via
   a subagent — see "Agent roles and model assignment").
5. Commit all three files — they are a permanent record and MUST NOT be deleted, even after the
   issue is closed. They hold the full reasoning trail so `docs/architecture.md` doesn't have to;
   only add a short pointer/summary there, not the full spec/plan content.
6. The PR implementing the issue MUST link the `specs/<issue-number>-<slug>/` folder.

Settled issues skip this entirely — implement directly against the issue and
`docs/architecture.md`, as before. This is deliberate: running the full pipeline on settled issues
dilutes its value through overuse. This workflow applies going forward only; #4 and #5 were not
retroactively given `specs/` folders.

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

## Before merging a pull request (independent review gate)

Per constitution Principle III: passing CI is necessary but not sufficient. Before merging any PR
that introduces or changes non-trivial logic (geometry, numerical, statistical, filtering,
association, or classification code — not pure config/schema/scaffolding), you MUST get an
independent review of the diff from an agent or person who did not author it, and resolve or
explicitly accept its findings, before merging. This caught a real, CI-passing, self-tested bug
(a 180-degree bearing inversion in #5) that the original author's own tests missed entirely.

- Run a dedicated review subagent against the PR's diff/tests (see "Agent roles and model
  assignment" below for which one and which model) and address or explicitly dismiss (with
  reasoning) every finding before merging.
- Record what was reviewed and what was found (or "no findings") in the PR body, so the review
  step is auditable after the fact, not just a private, unverifiable claim.
- Do not skip this step because CI is green or because you (the agent) are confident in the
  change — confidence in your own output is exactly what this step exists to check.
- Scaffolding, config-only, and documentation-only PRs may skip this gate.
- **The human (not `@copilot` or any agent) is the merge-approval gate.** The agent does not
  request or rely on an automated `@copilot` approval to satisfy the repo's branch-protection
  approval requirement — the user reviews the final, verified PR and approves/merges it
  themselves.

## Agent roles and model assignment

Decided explicitly by the user (not a default) — three distinct roles, each with its own model
tier, used consistently across every sub-issue going forward:

1. **Spec/plan authoring and implementation**: done directly by the primary agent in the main
   session — not delegated to a subagent. This includes writing `spec.md`/`plan.md`, `tasks.md`,
   and all source code/tests.
2. **Rubber-duck review of `spec.md`/`plan.md`** (the specs/ workflow's step 3): run as a separate
   agent pinned to the highest-capability ("opus-tier") model available, specifically because this
   is the step that catches design-level flaws before any code is written — it's worth the extra
   cost. Re-run after every substantive revision rather than assuming a fix is sufficient (see
   "Rigorous pre-implementation review" below).
3. **Test/implementation review before merge**: run as a separate agent pinned to a sonnet-tier
   model, checking specifically that the written tests actually exercise the feature as
   implemented (not just that they pass), then performing final verification of the PR as a whole.
   This is the "independent review gate" above.

These are run as separate agent invocations (their own context window, reporting back findings),
not as parallel long-lived processes the user coordinates directly — but they are treated as
independent reviewers, not an extension of the authoring agent's own reasoning. Do not skip the
model pin by letting a review run on whatever the default happens to be; be explicit about the
model for both the rubber-duck and test-review steps.

## Recurring architecture-health pass

Per constitution Principle VII: after every 2-3 merged sub-issues, pause before claiming the next
one and do a dedicated architecture-health check-in (not tied to any single PR's diff):

- Re-read `docs/architecture.md` end to end against the current state of `src/`.
- Look specifically for: module-boundary violations (a component reaching into another's
  internals), logic duplicated across modules that should be shared, contracts that have quietly
  drifted from what the doc says, and scope creep accumulated across the recently merged PRs.
- Fix small findings immediately in a short follow-up PR. File a tracked issue for anything larger
  than a quick fix — don't expand the issue you're about to start to cover it.
- Note in chat/PR history that the pass happened and what (if anything) it found, so it's
  auditable rather than an invisible, unverifiable step.

## Rigorous pre-implementation review ("rubber-duck")

See "The specs/ workflow (unsettled issues only)" above — the `rubber-duck` interview of `plan.md`
is step 3 of that workflow and is required for every unsettled sub-issue.

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
