<!--
Sync Impact Report
- Version change: 1.2.0 → 1.3.0
- Rationale: Principle VII materially expanded. Previously "unsettled design" was left to an
  agent's unstructured judgment, with no written rule. Replaced with a concrete, checkable
  4-rule classification an agent MUST apply and state out loud before claiming any sub-issue.
  Added a requirement that every unsettled sub-issue gets a permanent, scoped, per-issue
  `specs/<issue-number>-<slug>/{spec,plan,tasks}.md` artifact trail (using Spec Kit's
  spec/plan/tasks structure), committed and never deleted — closing a gap where the only two
  places a design decision could live were an ephemeral issue/PR thread or a permanently-growing
  `docs/architecture.md`, with nothing scoped in between. Explicitly applies going forward only;
  #4 and #5 are not backfilled.
- Modified principles: VII. Recurring Architecture Health & Rigorous Pre-Implementation Review
  (expanded: concrete settled/unsettled rule, specs/ artifact requirement)
- Added sections: none
- Removed sections: none
- Templates requiring updates: .github/copilot-instructions.md (settled/unsettled checklist,
  specs/ workflow steps) — updated in the same change.
- Follow-up TODOs: none
-->
# Plug-and-Prove Constitution

## Core Principles

### I. Architecture-First Reference
`docs/architecture.md` is the single authoritative source of truth for system design. Every
sub-issue MUST be implemented consistent with the components, contracts, and data flow it
describes. If an implementation needs to deviate from or resolve an open question in that
document (see its §13 Open Questions), the same pull request MUST update the document. Agents
and contributors MUST read the relevant section(s) before writing code for an issue; the
architecture doc is read before the issue body is treated as sufficient context on its own.

### II. Offline & Simulated Only (NON-NEGOTIABLE)
This project is a simulated demonstration, not a production system. It MUST run fully offline on
a single machine: no cloud services, no network reachback beyond a local UDP send to a TAK
client, and no RF emissions. It MUST use only simulated or public data — never real sensors, real
drones, or real effector/defeat-system control. Any recommendation or cue record produced is for
logging/display only. Any change that would require real hardware, cloud infrastructure, or
network reachback to function is out of scope and MUST be rejected or deferred to a clearly
separate, explicitly-scoped future effort.

### III. Test-First & CI-Gated
Every change MUST ship with automated tests (`pytest`), and CI (tests + lint) MUST pass before
merge. Passing CI plus a fully checked acceptance criteria list is necessary, but it is NOT
sufficient on its own: a PR that introduces or changes non-trivial logic (any geometry, numerical,
statistical, filtering, association, or classification computation — not pure config/schema/
scaffolding) MUST also receive an independent review pass before merge, performed by an agent or
person who did not author the diff being reviewed. Self-authored tests passing is not evidence of
correctness on its own, because an author's blind spots are typically reproduced in their own
tests. The review outcome (what was checked, what was found, how it was resolved) MUST be
recorded in the PR body. Routine, narrowly-scoped, non-algorithmic changes (e.g. scaffolding,
config schema additions, documentation) MAY skip this independent pass.

### IV. Narrow, Contract-Bound Changes
Each issue/PR MUST stay within its assigned module boundary (per the package layout in
`docs/architecture.md` §2) and its own stated acceptance criteria. Scope creep into another
issue's territory is prohibited — if a gap is discovered, file or update a separate issue rather
than expanding the current one. Components MUST interact only through their documented contracts
(e.g. the `SensorAdapter` interface, the `Detection` schema, the `OutputAdapter` interface) so
that swapping or extending one component never requires changing another.

### V. Reproducibility
All randomness MUST flow through the project's single seeded RNG utility. Given the same seed and
configuration, a run MUST produce identical ground truth, detections, tracks, and classifications
across executions. Every component that introduces stochastic behavior MUST have a test asserting
this property.

### VI. Explainability
Every track, classification, and recommendation the system produces MUST carry a human-readable
reason, not just a label or a number. Every conformance-harness check result MUST state pass/fail
plus a one-line reason. This is a demo about trustworthy, inspectable automation — a correct but
unexplained answer does not satisfy this principle.

### VII. Recurring Architecture Health & Rigorous Pre-Implementation Review
Per-PR review (Principle III) checks one diff in isolation; it does not catch drift accumulating
*across* merged PRs. After every 2-3 merged sub-issues, an agent MUST perform a dedicated
architecture-health pass: re-read `docs/architecture.md` against the current state of `src/`, and
check for module-boundary violations, duplicated logic that should be shared, contracts that have
quietly drifted from what's documented, and any accumulated scope creep across the reviewed PRs.
Findings MUST either be fixed immediately (if small) or filed as a tracked issue (if larger than a
quick fix), not silently noted and dropped.

Separately, before claiming any sub-issue, an agent MUST classify it as **settled** or
**unsettled** against `docs/architecture.md`, and state that classification (and which rule fired)
in chat before proceeding. A sub-issue is **unsettled** if any of the following is true:

1. Implementing it requires resolving a bullet explicitly listed in `docs/architecture.md` §13
   (Open questions / risks).
2. Implementing it would add or change a row in `docs/architecture.md` §12 (Key design decisions,
   locked) — i.e. it requires genuinely choosing between two or more real alternatives, not
   selecting internal implementation detail.
3. A component's interface, schema, algorithm, or threshold that the issue depends on is not
   fully pinned down in `docs/architecture.md` §2-§11 — the missing part would have to be invented.
4. Two competent engineers implementing the same acceptance criteria could reasonably produce
   materially different, non-interchangeable designs.

A sub-issue is **settled** only if every acceptance criterion already maps onto something
`docs/architecture.md` fully specifies, with no remaining decision beyond implementation detail.
A sharp retroactive check on the same rule: if merging the issue's PR requires editing §12 or §13,
it was unsettled, and that should have been caught before implementation began, not after.

For every **unsettled** sub-issue, an agent MUST, before writing implementation code: write a
`spec.md` (what & why) and a `plan.md` (how, concretely) under `specs/<issue-number>-<slug>/`,
subject `plan.md` to a rigorous, Socratic pre-implementation review — interviewing it relentlessly
for gaps, unstated assumptions, and untested edge cases, in the spirit of "rubber duck debugging"
applied before code exists rather than after — and write a `tasks.md` in the same folder to
implement against. These files are committed to the repository and MUST NOT be deleted once
written; they are the permanent, per-issue record of what was decided and why, scoped separately
from `docs/architecture.md` so that document records only the current, locked state of the design
rather than accumulating every issue's full reasoning trail. The PR implementing the issue MUST
link the `specs/<issue-number>-<slug>/` folder, and `docs/architecture.md` MUST be updated with
only a short pointer/summary of the resulting decision, not the full spec/plan content.
**Settled** sub-issues MAY skip the spec/plan/rubber-duck sequence entirely and proceed straight
to implementation against the issue and `docs/architecture.md` as before — applying this process
to settled issues is deliberately out of scope, to avoid diluting its value through overuse. This
`specs/` requirement applies going forward only; sub-issues merged before this principle was
adopted (#4, #5) are not backfilled.

## Scope & Technology Constraints

- **Stack**: Python, `numpy` for numerical/filtering code, `pydantic` for schema validation,
  `pytest` for testing. New dependencies MUST be justified against this demo's small scope and
  time budget before being added.
- **Tracking**: a hand-rolled constant-velocity Kalman filter, not a third-party tracking
  framework (e.g. Stone Soup), per the locked decision in `docs/architecture.md` §12.
- **TAK output**: direct Cursor-on-Target (CoT) over UDP to a single TAK client (ATAK-CIV or
  WinTAK). No FreeTAKServer and no public/Azure-hosted web version are in scope for this epic;
  the output layer MUST remain swappable so these can be added later as separate efforts without
  modifying upstream components.
- **Provenance**: all code is original work, built on personal equipment and personal time, using
  only simulated or public data. No code, data, or designs from any employer or customer program.
  No JAUS / RAS-G IOP messages, documents, or any other export-controlled or paid standards
  content.
- **No production hardening**: this is a demo artifact. Security accreditation, multi-user
  support, and production-grade operational hardening are explicitly out of scope.

## Agentic Development Workflow

- GitHub issues are the unit of work and the coordination mechanism between agents and sessions.
  Every PR MUST reference the issue it implements (e.g. `Closes #N`) and explicitly check off
  which acceptance criteria it satisfies.
- Issues carry explicit `Blocked by` dependencies. An agent MUST NOT begin work on a blocked issue
  until its blockers are merged, but independent, unblocked issues MAY be worked in parallel by
  separate agents/sessions, provided they touch disjoint modules per the architecture's package
  layout.
- Any design decision an agent makes that resolves an open question in `docs/architecture.md`
  §13, or that deviates from the documented design, MUST be written back into that document in the
  same PR — so later issues inherit the decision instead of re-deciding it.
- Day-to-day operating instructions for coding agents (how to run tests, commit conventions, PR
  expectations) live in `.github/copilot-instructions.md`. This constitution defines the
  non-negotiable principles; that file defines the runtime mechanics for following them.

## Governance

This constitution supersedes ad hoc practices and informal conventions for this project.
Amendments require updating this file with an incremented version (MAJOR for incompatible
principle removals/redefinitions, MINOR for new or materially expanded principles/sections, PATCH
for clarifications/wording) and a Sync Impact Report describing the change. Every PR is expected
to be consistent with these principles; a PR that cannot be made consistent MUST either be
rejected or amend this constitution explicitly, not silently diverge from it. Use
`.github/copilot-instructions.md` for routine, runtime development guidance that supports but does
not override these principles.

**Version**: 1.3.0 | **Ratified**: 2026-10-29 | **Last Amended**: 2026-10-29
