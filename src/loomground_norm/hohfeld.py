# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""The Hohfeld facet-enrichment adapter — the one piece deontic declines to own.

``loomground-deontic`` ships the eight-incident vocabulary, the correlative/
opposite pairs, and the deterministic classifiers (:mod:`deontic.incidents`)
as pure language over primitive fields (``modal``, ``action``, ``raw``). It
explicitly does not touch a host's extracted-rule object: "The facet-
enrichment adapter that mutates extracted rule objects in place is
deliberately not here — it couples to the surface extractor and stays in the
reasoning layer." (see ``deontic.incidents`` module docstring). This module is
that adapter for :class:`~loomground_norm.rule_extractor.RuleFacet`: it reads
the incident, counterparty, and condition-kind straight from deontic's
classifiers and writes them onto a batch of facets, in place.

No incident vocabulary is redeclared here — import :data:`deontic.INCIDENTS`,
:func:`deontic.correlative`, :func:`deontic.opposite`,
:func:`deontic.is_advantage`, :func:`deontic.classify_incident`,
:func:`deontic.extract_counterparty`, and :func:`deontic.classify_condition_kind`
directly from the ``deontic`` package for the language itself; this module
carries only the mutator.
"""

from __future__ import annotations

from typing import Iterable

from deontic import classify_incident, classify_condition_kind, extract_counterparty

__all__ = ["attach_incidents"]


def attach_incidents(facets: list, roles: Iterable[str] = ()) -> int:
    """Enrich extracted RuleFacets with deontic's incident layer, in place.
    A rule's subject never becomes its own counterparty. Returns how many
    facets received an incident classification."""
    n = 0
    role_set = set(roles)
    for f in facets:
        if getattr(f, "incident", ""):
            continue
        f.incident = classify_incident(f.modal, f.action or "",
                                       f.raw_sentence or "")
        if f.incident:
            n += 1
        subject = getattr(f, "subject", "") or ""
        cp_roles = {r for r in role_set if r not in subject}
        f.counterparty = extract_counterparty(f.action or "",
                                              f.raw_sentence or "", cp_roles)
        f.condition_kind = classify_condition_kind(getattr(f, "condition", ""))
    return n
