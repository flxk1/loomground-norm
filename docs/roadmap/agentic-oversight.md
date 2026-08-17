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

## N4 · Rule extraction is not the bottleneck, and should not be treated as one

It is tempting to route agentic-oversight work through `rule_extractor`, because
oversight policies arrive as prose. Two of this plane's modules are marked
skeleton for a stated reason — `rule_registry` and `obligation_scheduler` still
carry the seams left by the host-specific code they were extracted from.

Finishing those seams is worth more to this roadmap than any new extraction
surface, and it is prerequisite to N1: an obligation runtime without a
deterministic tick and without a resolved action-gate port cannot carry an
oversight duty end to end. **N4 sequences before N1.**

---

## Sequencing

| Step | Item | Notes |
|---|---|---|
| 1 | N4 | close the `obligation_scheduler` action-gate port and the `rule_registry` placement seam |
| 2 | N1 | terminal states separating discharged / waived / elapsed |
| 3 | N2 | gap count and kind reported as a quantity |
| 4 | N3 | competence and assistance as declarations through `ports` |

## Gates

`python3 -m pytest` green, and the plane's own boundary tests: no jurisdiction,
no AI-oversight vocabulary, no second copy of deontic's operator or incident
model. A step that introduces a catalogue of agent kinds, reviewer roles, or
oversight levels has left the plane and belongs to a consumer.

An `UNDECLARED` competence must never widen into a permission anywhere downstream
of this plane; where that cannot be guaranteed by this plane alone, it is stated
as a consumer obligation rather than assumed.
