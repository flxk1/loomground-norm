# loomground-norm — plane boundary and module map

Moved verbatim from README.md (2026-09-09, README canon). Reference material; the README carries the interface.

The general normative-**reasoning** plane: rule extraction, obligation
tracking, and multi-hop subsumption over norms. It does not define the
deontic language — `loomground-deontic` is the language (the three modal
operators O/P/F, the eight Hohfeld incidents, the formula carrier, the
grammar and algebra) — this plane consumes it and builds the reasoning atop
it: extracting a rule's operative slots, lifting them into deontic's formula,
tracking the resulting duty as dated state, and assembling multi-hop
subsumption chains. It formalises *any* norm — not only AI-governance rules —
into one typed shape a reasoning host can act on.

**Plane / ships.** Sits between deontic/solver and the domains that apply
norms: rule extraction, obligation state, subsumption chains — no
jurisdiction, no AI-oversight vocabulary, no legal-entity map, and no
parallel copy of deontic's operator or incident model. Ships the extraction
and state machines that operate on deontic's typed formula; every
domain-specific fact (which jurisdiction, which regulator, which curated
artifact catalogue) arrives through an injected port or lives in the
consuming plane.

**Consumes** `deontic` (`loomground-deontic`):

- `deontic.{OP_OBLIGATION,OP_PERMISSION,OP_PROHIBITION,VALID_OPERATORS}` —
  the three SDL modals. There is no fourth "right" operator: a surface
  "right" lifts to a permission (a liberty) at the operator layer; a
  claim-right is carried by the Hohfeld incident instead.
- `deontic.{INCIDENTS,classify_incident,extract_counterparty,classify_condition_kind,correlative,opposite,is_advantage}` —
  the eight-incident Hohfeld vocabulary and its classifiers. This plane adds
  only the facet-enrichment adapter that mutates an extracted rule in place
  (`loomground_norm.hohfeld.attach_incidents`) — deontic's own incidents
  module deliberately does not touch a host's rule object.
  `loomground_norm.rule_extractor.RuleFacet` carries the vocabulary itself
  from deontic; no local copy.
- `deontic.{DeonticFormula,formula_from_fields,is_grounded,detect_conflicts}` —
  the formula carrier, its well-formedness/groundedness predicate, and
  same-bearer/same-action candidate-conflict detection.
  `loomground_norm.deontic_lift.formula_from_rule` is the one adapter this
  plane adds: it reads a `RuleFacet`'s primitive fields and calls deontic's
  own `formula_from_fields` — no operator-mapping table of its own.

**Consumes** `loomground_solver`:

- `loomground_solver.dimensions.Dimension` — the 5D edge model, for
  callers that project a deontic formula onto dimensioned edges.
- `loomground_solver.temporal.{Date,RelativeDeadline,TemporalError}` —
  typed deadlines for the obligation runtime.
- `loomground_solver.norm_contract.Level` — the shared
  pass/violation/escalate verdict vocabulary, reused by the subsumption
  validator rather than redeclared.

No other dependency. The plane carries no governance, no corpus, no
jurisdiction pack, no persistence backend of its own — a host wires those in
through `loomground_norm.ports` (`SourceInstrument`, `AuditSink`,
`LegalSystemPack`), the same seam discipline `loomground_solver.ports` uses
for its own hosts.

**Consumed by** RVND's governance server (the AI-oversight application of
this plane) and, in time, any other normative domain built the same way — a
contracts pack, a compliance pack, a legal-instrument pack. Governance is one
application of the normative language, not its owner; a consumer that wants
jurisdiction-specific citation rules, a curated deliverable catalogue, or an
entity/world map builds that on top, it does not become part of this plane.

## Module map

| Module | What it does | Status |
|---|---|---|
| `rule_extractor` | Phase-1 regex extraction of a rule's five operative slots (subject/modal/action/condition/exception) across the 24 EU languages | real |
| `rule_extractor_llm` | Phase-2 LLM-gated extraction sharing Phase-1's schema, confidence cap, and abstention discipline | real |
| `hohfeld` | facet-enrichment adapter: attaches `deontic`'s Hohfeld incident/counterparty/condition-kind to an extracted rule, in place — the vocabulary itself is `deontic`'s | real |
| `deontic_lift` | lifts an extracted rule into `deontic`'s Standard Deontic Logic formula (O/P/F) via `deontic.formula_from_fields`; conflict detection is `deontic.detect_conflicts`, reused not redeclared | real |
| `obligation_runtime` | the obligation state machine — a duty as tracked, dated, gated state, against an injected instrument | real |
| `subsumption_path` | assembles a multi-hop subsumption chain with its gaps (retrieval/context/reasoning/conflict/authority) surfaced, never smoothed | real |
| `subsumption_validator` | validates a chain against universal norm theory, plus an optional injected regional jurisdiction pack | real |
| `rule_registry` | typed, persisted span-norm storage — span placement, document re-pinning, orphan tracking, search; URN minting and audit are injected ports | real |
| `obligation_scheduler` | the deterministic obligation `tick` — deadline arithmetic and per-state follow-up proposals; instrument resolution is an injected port | real |
| `ports` | the injected seams (`SourceInstrument`, `AuditSink`, `LegalSystemPack`) | real |

## Why every module carries an injected port rather than a host import

Several of the source modules this plane was extracted from mixed general
deontic-logic work with a direct import of something host-specific: an
ingest-classification framework, a legal-entity map, a runtime action-gate.
Every one of those couplings has been inverted into a port declared in
`ports.py` (or, for `rule_registry`, a `urn_minter` callable), so the module
is exercised against `loomground_solver` and `deontic` alone.

Two of those seams are frequently mistaken for unfinished work, so they are
worth stating positively:

- `rule_registry` produces spans and rules and deliberately does **not** anchor
  them onto governing instruments or jurisdictions. Placing a norm onto the
  entities that govern it is a legal-domain concern owned by a downstream
  consumer.
- `obligation_scheduler` only **proposes**. It attaches no verdict, no
  footprint and no decision to a follow-up; whether an action may fire is a
  governance concern a consumer classifies on its side.

Neither is a gap. They are the plane boundary working as intended — this plane
carries no jurisdiction and no AI-oversight vocabulary, and a consumer that
wants either builds it on top.

## Development

The family is a set of sibling repositories. For local development, check them
out beside this one and either install the pinned dev set

```
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

or, if the sibling packages are present but not installed, `tests/conftest.py` adds
their `src/` directories to the path so `pytest` runs from a fresh checkout
with no install step. Canonical resolution for CI is the git-revision pin set in
the `dev` extra of `pyproject.toml`. Release mechanics are in `RELEASING.md`.

No import-time dependency on rvnd, versum, or governance from this package.
The `loomground-deontic` entry is this plane's own direct dependency (the
deontic language). `tests/conftest.py` also puts a `loomground-governance` checkout
on the path, but that entry is there for `loomground_solver` itself:
`loomground_solver.methods.loomground` imports `loomground_governance` at
module import time (grammar/vocabulary), so nothing importing
`loomground_solver` — this plane included — runs without a governance
checkout on the path, its own "no governance, no domain/corpus coupling"
docstring notwithstanding. That is a solver-level fact, not something this
plane adds; a pinned install (`pip install loomground-solver`) resolves it
as a normal transitive dependency instead of a manual path.

The test suite exercises the plane against a real `loomground_solver`
checkout — no stub, no mock solver.
