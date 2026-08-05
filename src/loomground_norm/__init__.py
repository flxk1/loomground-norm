# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""loomground_norm — the general normative-reasoning plane.

Rule extraction, obligation tracking, and multi-hop subsumption over a
solver-neutral rule shape. This plane does not define the deontic language:
the three modal operators (O/P/F), the eight Hohfeld incidents, and the
formula carrier are `loomground-deontic`'s — this plane consumes them and
adds the reasoning on top (extraction, obligation state, subsumption). No
governance, no legal domain, no jurisdiction — those arrive through the
injected ports in :mod:`loomground_norm.ports`, or are added by a consumer
(RVND's AI-oversight layer, a future ``contracts`` or ``legal`` pack). The
package is imported unchanged by any host, the same discipline
:mod:`loomground_solver` follows toward :mod:`loomground_governance`.

Public surface, by module:

  * :mod:`.rule_extractor` — Phase-1 regex extraction of a rule's five
    operative slots (subject/modal/action/condition/exception) across 24 EU
    languages.
  * :mod:`.rule_extractor_llm` — Phase-2 LLM-gated extraction sharing
    Phase-1's schema and abstention discipline.
  * :mod:`.hohfeld` — the facet-enrichment adapter that attaches deontic's
    Hohfeld incident/counterparty/condition-kind to a batch of extracted
    rules, in place. The incident vocabulary itself is `deontic`'s.
  * :mod:`.deontic_lift` — lifts an extracted rule into `deontic`'s formula
    carrier and flags candidate same-bearer/same-action conflicts (deontic's
    own detector).
  * :mod:`.obligation_runtime` — the obligation state machine: a duty as
    tracked, dated, gated state against an injected
    :class:`~loomground_norm.ports.SourceInstrument`.
  * :mod:`.subsumption_path` — assembles a multi-hop subsumption chain
    (Norm -> Tatbestand -> Ausnahme -> Auslegung -> Subsumtion -> Ergebnis)
    with its gaps surfaced, never smoothed.
  * :mod:`.subsumption_validator` — validates a chain against universal norm
    theory, plus an optional injected, domain-neutral regional
    :class:`~loomground_norm.ports.RegionalPack`.
  * :mod:`.rule_registry` — typed, persisted span-norm storage (span
    placement, document re-pinning, orphan tracking) behind urn_minter /
    audit_sink ports.
  * :mod:`.obligation_scheduler` — the deterministic obligation ``tick``,
    emitting ungated follow-up proposals behind the InstrumentSource port.
  * :mod:`.ports` — the injected seams a host wires in.

The operators, incidents, formula carrier, and conflict detector below are
`loomground-deontic`'s — re-exported here under this plane's established
names so a consumer of the reasoning layer need not import both packages for
the common path. Import from `deontic` directly for anything not re-exported
here (the grammar, the algebra, the composition contract).
"""

from __future__ import annotations

from ._version import __version__

# rule_extractor — the five-slot Phase-1 surface read
from .rule_extractor import RuleFacet, FingerprintGate, extract_rules

# rule_extractor_llm — the Phase-2 LLM seam
from .rule_extractor_llm import Phase2Result, extract_rules_llm, PHASE2_CONFIDENCE_CAP

# hohfeld — the facet-enrichment adapter (mutates RuleFacet objects in place);
# the incident vocabulary itself comes straight from deontic, just below.
from .hohfeld import attach_incidents

# deontic — the language this plane consumes, not owns. Three operators
# (no fourth "right" modality — see deontic.operators), eight Hohfeld
# incidents, the formula carrier, and same-bearer/same-action candidate
# conflict detection.
from deontic import (
    OP_OBLIGATION, OP_PERMISSION, OP_PROHIBITION, VALID_OPERATORS,
    INCIDENTS, correlative, opposite, is_advantage,
    classify_incident, extract_counterparty, classify_condition_kind,
    DeonticFormula, detect_conflicts,
    is_grounded as obligation_is_grounded,
)

# deontic_lift — the rule-facet -> formula adapter deontic itself declines to
# own (see the module docstring)
from .deontic_lift import formula_from_rule, extract_formulae

# obligation_runtime — tracked, dated, gated duty state
from .obligation_runtime import (
    Obligation, ObligationRegistry, ObligationError,
    OPEN_STATES, TERMINAL_STATES,
)

# subsumption_path — the multi-hop chain, gaps surfaced
from .subsumption_path import Step, Gap, Subsumption, build as build_subsumption, ROLES, REQUIRED_ROLES

# subsumption_validator — universal + optional regional norm theory
from .subsumption_validator import Finding as SubsumptionFinding, ValidationReport, validate as validate_subsumption

# rule_registry — typed span-norm storage + placement (behind the
# urn_minter / audit_sink ports)
from .rule_registry import (
    SpanNorm, RuleRegistry, UrnMinter, place_into_registry,
)

# obligation_scheduler — the deterministic tick (behind the
# InstrumentSource port), emitting ungated follow-up proposals
from .obligation_scheduler import (
    target_state, FollowUp, SchedulerReport,
    ObligationScheduler, InstrumentSource,
)

# ports — the injected seams
from .ports import (
    SourceInstrument, AuditSink, NullAuditSink, RegionalPack,
)

__all__ = [
    "__version__",
    # rule_extractor
    "RuleFacet", "FingerprintGate", "extract_rules",
    # rule_extractor_llm
    "Phase2Result", "extract_rules_llm", "PHASE2_CONFIDENCE_CAP",
    # hohfeld (facet-enrichment adapter)
    "attach_incidents",
    # deontic (re-exported from loomground-deontic)
    "OP_OBLIGATION", "OP_PERMISSION", "OP_PROHIBITION", "VALID_OPERATORS",
    "INCIDENTS", "correlative", "opposite", "is_advantage",
    "classify_incident", "extract_counterparty", "classify_condition_kind",
    "DeonticFormula", "obligation_is_grounded", "detect_conflicts",
    # deontic_lift (the rule-facet -> formula adapter)
    "formula_from_rule", "extract_formulae",
    # obligation_runtime
    "Obligation", "ObligationRegistry", "ObligationError",
    "OPEN_STATES", "TERMINAL_STATES",
    # subsumption_path
    "Step", "Gap", "Subsumption", "build_subsumption", "ROLES", "REQUIRED_ROLES",
    # subsumption_validator
    "SubsumptionFinding", "ValidationReport", "validate_subsumption",
    # rule_registry
    "SpanNorm", "RuleRegistry", "UrnMinter", "place_into_registry",
    # obligation_scheduler
    "target_state", "FollowUp", "SchedulerReport",
    "ObligationScheduler", "InstrumentSource",
    # ports
    "SourceInstrument", "AuditSink", "NullAuditSink", "RegionalPack",
]
