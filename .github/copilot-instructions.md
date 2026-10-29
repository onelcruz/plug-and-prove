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

## Before merging a pull request (independent review gate)

Per constitution Principle III: passing CI is necessary but not sufficient. Before merging any PR
that introduces or changes non-trivial logic (geometry, numerical, statistical, filtering,
association, or classification code — not pure config/schema/scaffolding), you MUST get an
independent review of the diff from an agent or person who did not author it, and resolve or
explicitly accept its findings, before merging. This caught a real, CI-passing, self-tested bug
(a 180-degree bearing inversion in #5) that the original author's own tests missed entirely.

- If you have access to a dedicated review subagent (e.g. this environment's `code-review` agent
  type), run it against the PR's diff and address or explicitly dismiss (with reasoning) every
  finding before merging.
- If you don't have a review subagent available, request review from GitHub Copilot directly on
  the PR (`gh pr edit <N> --add-reviewer "@copilot"`) and wait for its review before merging.
- Record what was reviewed and what was found (or "no findings") in the PR body, so the review
  step is auditable after the fact, not just a private, unverifiable claim.
- Do not skip this step because CI is green or because you (the agent) are confident in the
  change — confidence in your own output is exactly what this step exists to check.
- Scaffolding, config-only, and documentation-only PRs may skip this gate.

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

Per constitution Principle VII: before writing implementation code for any sub-issue whose design
is **not** already fully settled by `docs/architecture.md` (i.e. it requires resolving an open
question from §13, or making a new structural decision not already locked in), write a short
implementation plan first and subject it to a rigorous Socratic pre-implementation review (the
`rubber-duck` agent type in this environment, or an equivalent independent design-review pass if
unavailable). This is an *interview*, not a light skim: it should relentlessly probe for unstated
assumptions, gaps the plan doesn't address, and untested edge cases, the same way you'd interview
a plan before trusting it with real stakes. Resolve or explicitly accept every question it raises
before starting implementation.

Issues whose design is already fully settled by `docs/architecture.md` (most of #6-#13 are, per
the existing package layout and contracts) MAY skip this step — don't dilute it by running it on
settled designs where there's nothing left to question.

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
