<!--
Sync Impact Report
- Version change: 1.1.0 → 1.2.0
- Rationale: Added a new principle (VII) requiring a recurring, dedicated architecture-health
  review pass (not just per-PR review) and raised the rigor bar for pre-implementation design
  review ("rubber-duck") on issues with open design questions, to a relentless/Socratic
  interview standard rather than a light pass. Adopted after comparing this project's process
  against an external AI-agent workflow (Matt Pocock / AI Hero's 5-skill pipeline) and
  deliberately declining its strict test-first/TDD practice and its vertical-slice ticket
  structure, both evaluated and rejected for this project (see decision log below).
- Modified principles: none redefined
- Added sections: VII. Recurring Architecture Health & Rigorous Pre-Implementation Review
- Removed sections: none
- Templates requiring updates: .github/copilot-instructions.md (architecture-health cadence and
  rubber-duck procedure) — updated in the same change.
- Decision log (external workflow comparison, 2026-10-29): evaluated adopting Matt Pocock's
  grill-me/to-spec/to-tickets/tdd/improve-codebase-architecture pipeline wholesale. Adopted: a
  recurring architecture-health pass, and a stricter pre-code design-interview standard. Declined:
  strict test-first/TDD (tests continue to be written alongside/after implementation, per existing
  Principle III). Declined: re-slicing issues #6-#13 into vertical tracer-bullet tickets (the
  horizontal, by-architectural-layer decomposition is retained, because this epic's core claim —
  a new sensor adapter plugs in without touching core/fusion/display code — is best demonstrated
  by cleanly separated layer boundaries, which a vertical-slice-first structure would undercut).
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
quick fix), not silently noted and dropped. Separately, for any sub-issue whose design is not
already fully settled by `docs/architecture.md` (i.e. it would require resolving an open question
or making a new structural decision), an agent MUST produce a short implementation plan and
subject it to a rigorous, Socratic pre-implementation review — interviewing the plan relentlessly
for gaps, unstated assumptions, and untested edge cases, in the spirit of "rubber duck debugging"
applied before code exists rather than after — before writing implementation code. Issues whose
design is already fully settled in `docs/architecture.md` MAY skip this pre-implementation review.

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

**Version**: 1.2.0 | **Ratified**: 2026-10-29 | **Last Amended**: 2026-10-29
