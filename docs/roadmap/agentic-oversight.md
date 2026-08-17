<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 flxk1 -->
# Roadmap slice — normative reasoning and agentic oversight

Status: **draft, not committed scope.** Non-normative.

A set of open problems in agentic oversight reaches this plane at two points:
**oversight duties as tracked state**, and **the verification gap**. Both are
general normative-reasoning problems that happen to bite hardest in an agentic
setting, which is what makes them admissible here at all.

The plane boundary holds throughout: no jurisdiction, no AI-oversight
vocabulary, no legal-entity map, and no parallel copy of the deontic operator or
incident model. Anything domain-specific arrives through `ports`.

---

## N1 · An oversight duty is a duty, and the runtime already tracks duties

"A human must review this before it takes effect" is an obligation with a bearer,
an action, a condition and a deadline. `obligation_runtime` already models
exactly that: a duty as tracked, dated, gated state against an injected
instrument.

What it does not yet carry is the distinction that decides whether oversight was
real: the difference between a duty **discharged**, a duty **waived**, and a duty
whose window **elapsed while nobody acted**. All three end with the action
proceeding. Only the first is oversight.

*Candidate shape.* Terminal states that separate the three, so an elapsed
oversight window is a recorded fact rather than an absence. The temporal
machinery is already injected from the solver's typed deadlines; this is a
distinction in the state machine, not new time handling.

*Why it matters here rather than in a host.* A host can record that a deadline
passed. Only the obligation runtime knows that the duty which lapsed was the one
the release depended on — and that is a normative relation, not a log entry.

---

## N2 · A subsumption chain is a competence claim

`subsumption_path` assembles a multi-hop chain with its gaps surfaced —
retrieval, context, reasoning, conflict, authority — rather than smoothed. That
discipline is the plane's most useful contribution to the oversight problem, for
a reason worth stating explicitly.

The verification gap is the observation that a system may produce work faster
than a supervisor can meaningfully check it, so that at some point review becomes
ceremonial. The gap is normally discussed as unmeasurable. It is not, at least
not entirely: a chain that a reviewer must accept **at the points where its own
gaps are surfaced** is a chain whose unverified extent is already enumerated.
Gaps are a lower bound on what the reviewer is taking on trust.

*Candidate shape.* Report the surfaced gaps of a chain as a **quantity** —
count and kind — so a consumer can carry it into a decision. The plane reports;
it does not decide what an acceptable gap count is, which is a host's policy and
would be a domain fact if fixed here.

---

## N3 · Competence is declared, never inferred

The obvious next move after N2 is to estimate whether a reviewer *could* have
understood what they approved, and to feed that estimate into an autonomy
decision. The plane should refuse it.

An inferred competence score is an unfalsifiable claim about a private human
capacity, and a system that mints one has manufactured the same false assurance
that makes ceremonial oversight dangerous in the first place. The correct
treatment is the one already established elsewhere in the family for how a human
review was formed: an absent declaration reads **undeclared**, never
*competent* and never *incompetent*.

*Candidate shape.* Competence and assistance enter through a port as
declarations with a provenance, and an absent declaration propagates as
undeclared into whatever consumes it. The plane defines the shape and the
propagation rule; it holds no catalogue of who is competent at what — that is a
domain fact and belongs to a consuming plane.

---

## N4 · The prerequisite that turned out not to exist

An earlier reading of this slice held that `rule_registry` and
`obligation_scheduler` were skeletons carrying unfinished host seams, and that
closing them was prerequisite to N1.

That was wrong, and it came from a stale README rather than from the code. Both
modules are implemented — span placement, document re-pinning, orphan tracking
and search in one; deadline arithmetic and per-state follow-up proposals in the
other — with their host couplings already inverted into injected ports, and
eighteen tests between them. What the README called "the port it is waiting on"
is the plane boundary working as designed: `rule_registry` deliberately does not
anchor norms onto governing instruments (a legal-domain concern), and
`obligation_scheduler` deliberately only proposes (a governance concern).

**N1 is therefore not blocked.** The genuine weakness on this plane is different
and narrower: twenty-four tests across nine modules is thin, and it went
unnoticed because a `conftest` root-resolution bug meant the suite silently
skipped rather than ran. Coverage is the precondition for trusting anything
below, and it is not itself a workstream.

---

## Sequencing

| Step | Item | Notes |
|---|---|---|
| 1 | N1 | terminal states separating discharged / waived / elapsed |
| 2 | N2 | gap count and kind reported as a quantity |
| 3 | N3 | competence and assistance as declarations through `ports` |

## Gates

`python3 -m pytest` green, and the plane's own boundary tests: no jurisdiction,
no AI-oversight vocabulary, no second copy of deontic's operator or incident
model. A step that introduces a catalogue of agent kinds, reviewer roles, or
oversight levels has left the plane and belongs to a consumer.

An `UNDECLARED` competence must never widen into a permission anywhere downstream
of this plane; where that cannot be guaranteed by this plane alone, it is stated
as a consumer obligation rather than assumed.
