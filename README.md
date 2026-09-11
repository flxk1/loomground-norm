# loomground-norm

General normative-reasoning plane: rule extraction, obligation state, and multi-hop subsumption over the loomground-deontic formula.

## Problem

Rules extracted from text are not tracked as duties over time. Rule extraction, obligation state, multi-hop subsumption.

## Install

```
git clone https://github.com/flxk1/loomground-norm
cd loomground-norm
python3 -m pip install -e ".[dev]" -r requirements-dev.txt
python3 -m pytest
```

Sibling checkouts beside this one run without the install step (`tests/conftest.py`).

## Usage

```python
from loomground_norm import extract_rules, formula_from_rule

rule = extract_rules(sentence)[0]       # RuleFacet
formula_from_rule(rule).render()         # deontic formula
```

## Example

```
in : extract_rules("The operator must delete personal data within 30 days after the contract ends.")[0]
out: RuleFacet(subject='the operator', modal='obligation', modal_phrase='must', action='delete personal data within 30 days after the contract ends', condition='', exception='', consequence='', raw_sentence='The operator must delete personal data within 30 days after the contract ends.', language='en', confidence=0.7, condition_struct=None, incident='', counterparty='', condition_kind='', addressee_resolved=True)
```

## Language

The lift: a sentence of running text becomes a `RuleFacet(subject, modal, modal_phrase, action, condition, exception)`, then a `DeonticFormula`, in 24 EU languages.
Modal classes: obligation `O` · prohibition `F` · permission and right `P`; `where`/`if` = condition, `unless`/`except` = exception.

```
The operator shall not transfer personal data outside the EU.        → F(the operator : transfer personal data outside the EU)
The operator shall delete personal data unless a legal hold applies.  → O(the operator : delete personal data) unless [a legal hold applies]
Der Anbieter darf keine personenbezogenen Daten weitergeben.          → F(der anbieter : personenbezogenen Daten weitergeben)
```

Right side = `formula_from_rule(extract_rules(s)[0]).render()`. Fields and the 24-language modal table: [`docs/language-card.md`](docs/language-card.md).

## Interface

| Direction | Symbol | Module |
|---|---|---|
| consumes | `OP_OBLIGATION`, `OP_PERMISSION`, `OP_PROHIBITION`, `INCIDENTS`, `DeonticFormula`, `formula_from_fields`, `detect_conflicts` | `deontic` (loomground-deontic) |
| consumes | `Dimension`, `temporal.Date`, `RelativeDeadline`, `norm_contract.Level` | `loomground_solver` |
| produces | `RuleFacet`; 24 EU languages | `rule_extractor`, `rule_extractor_llm` |
| produces | `DeonticFormula` per rule | `deontic_lift` |
| produces | `Obligation`, `ObligationRegistry` — dated, gated duty state; `SchedulerReport` from `tick` | `obligation_runtime`, `obligation_scheduler` |
| produces | `Subsumption` chain with `Gap`s; `ValidationReport` | `subsumption_path`, `subsumption_validator` |
| produces | `SpanNorm`, `RuleRegistry` — span placement, re-pinning, orphan tracking | `rule_registry` |
| ports | `SourceInstrument`, `AuditSink`, `RegionalPack`, `InstrumentSource`, `urn_minter` | `ports` |

Module map and plane boundary: `docs/plane-boundary.md`.

## Family

General normative-reasoning plane. Consumes: loomground-deontic (the language), loomground-solver (verdict vocabulary, temporal types, 5D edges) · consumed by: RVND governance server · pipeline position: applied plane in `source → loomground-ingest → loomground-versum → loomground-solver → applied or diagnostic planes`. Jurisdiction, regulator and corpus facts enter through the ports.

## Status

Version 0.1.0 · 25 tests · loomground-solver >=0.2,<0.6 · loomground-deontic >=0.1,<0.3 · Python >=3.10.

## License

Apache-2.0 · `LICENSES/Apache-2.0.txt` · `NOTICE`
