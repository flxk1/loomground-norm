# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Lift an extracted rule into deontic's formula — the adapter deontic itself declines to own.

``loomground-deontic`` is the general deontic language: the three SDL
operators (O/P/F — see ``deontic.operators`` for why there is no fourth
"right" modality), the eight Hohfeld incidents, and the formula carrier
(:class:`deontic.DeonticFormula`) built from primitive fields
(:func:`deontic.formula_from_fields`). It is deliberately built from those
primitive fields, not from a rule extractor's facet: "the adapter that reads
those fields off a host's extracted facet lives in the reasoning layer" (see
``deontic.formula`` module docstring). This module is that adapter for
:class:`~loomground_norm.rule_extractor.RuleFacet`.

No modal-to-operator table is redeclared here: deontic's own
:data:`deontic.MODAL_TO_OP` is total over the rule extractor's four surface
modal classes (obligation/permission/prohibition/right) and is reused as-is
inside :func:`deontic.formula_from_fields`. A surface "right" lifts to a
permission (``P``) at the operator layer, same as deontic's own default — a
claim-right is instead carried by the Hohfeld incident
(:mod:`loomground_norm.hohfeld` attaches it before this lift runs).
"""

from __future__ import annotations

from deontic import DeonticFormula, formula_from_fields

from .rule_extractor import FingerprintGate, RuleFacet, extract_rules

__all__ = ["formula_from_rule", "extract_formulae"]


def formula_from_rule(rule: RuleFacet) -> DeonticFormula:
    """Lift one :class:`RuleFacet` into a deontic :class:`DeonticFormula`.

    A thin field mapping onto :func:`deontic.formula_from_fields` — the
    operator mapping, confidence handling, and grounded-placeholder fallback
    are all deontic's, not reimplemented here. The Hohfeld incident and
    counterparty carry through when the facet already has them (see
    :func:`loomground_norm.hohfeld.attach_incidents`).
    """
    return formula_from_fields(
        rule.modal, rule.subject, rule.action,
        condition=rule.condition,
        exception=rule.exception,
        incident=getattr(rule, "incident", "") or "",
        counterparty=getattr(rule, "counterparty", "") or "",
        language=rule.language,
        raw_sentence=rule.raw_sentence,
        confidence=rule.confidence,
    )


def extract_formulae(content: str, *,
                     fingerprint_gate: "FingerprintGate | None" = None) -> list[DeonticFormula]:
    """Extract deontic formulae from normative content.

    Thin lift over :func:`~loomground_norm.rule_extractor.extract_rules`:
    every rule the extractor finds becomes one formula. Same gating contract
    as ``extract_rules`` — see its docstring for ``fingerprint_gate``.
    """
    rules = extract_rules(content, fingerprint_gate=fingerprint_gate)
    return [formula_from_rule(r) for r in rules]
