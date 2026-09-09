# loomground-norm

General normative-reasoning plane: rule extraction, obligation state, and multi-hop subsumption over the loomground-deontic formula.

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

rule = extract_rules("The provider shall register the system before placing it on the market.")[0]
print(rule.subject, rule.modal, rule.action)
print(formula_from_rule(rule).operator)
```

```
the provider obligation register the system before placing it on the market
O
```

## Interface

| Direction | Symbol | Module |
|---|---|---|
| consumes | `OP_OBLIGATION`, `OP_PERMISSION`, `OP_PROHIBITION`, `INCIDENTS`, `DeonticFormula`, `formula_from_fields`, `detect_conflicts` | `deontic` (loomground-deontic) |
| consumes | `Dimension`, `temporal.Date`, `RelativeDeadline`, `norm_contract.Level` | `loomground_solver` |
| produces | `RuleFacet` — subject, modal, action, condition, exception; 24 EU languages | `rule_extractor`, `rule_extractor_llm` |
| produces | `DeonticFormula` per rule | `deontic_lift` |
| produces | `Obligation`, `ObligationRegistry` — dated, gated duty state; `SchedulerReport` from `tick` | `obligation_runtime`, `obligation_scheduler` |
| produces | `Subsumption` chain with `Gap`s; `ValidationReport` | `subsumption_path`, `subsumption_validator` |
| produces | `SpanNorm`, `RuleRegistry` — span placement, re-pinning, orphan tracking | `rule_registry` |
| ports | `SourceInstrument`, `AuditSink`, `RegionalPack`, `InstrumentSource`, `urn_minter` | `ports` |

Module map and plane boundary: `docs/plane-boundary.md`.

## Family

General normative-reasoning plane. Consumes: loomground-deontic (the language), loomground-solver (verdict vocabulary, temporal types, 5D edges) · consumed by: RVND governance server · pipeline position: applied plane in `source → loomground-ingest → loomground-versum → loomground-solver → applied or diagnostic planes`. Jurisdiction, regulator, and corpus facts enter through the ports above or live in the consuming plane.

## Status

Version 0.1.0 · 24 tests · loomground-solver >=0.2,<0.6 · loomground-deontic >=0.1,<0.2 · Python >=3.10 · 24 extraction languages.

## License

Apache-2.0 · `LICENSES/Apache-2.0.txt` · `NOTICE`
