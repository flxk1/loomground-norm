# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Smoke test — the plane imports, and its deontic + obligation modules run
against a real ``loomground_solver`` (not a stub).

Run with:

    PYTHONPATH=src:<path-to-loomground-solver>/src python -m pytest tests -q

Covers:
  * the package imports and exposes the declared public surface;
  * rule_extractor -> deontic: a sentence lifts to a grounded deontic
    formula with the right operator;
  * obligation_runtime: an Obligation is created from a rule, tracked
    against an injected SourceInstrument, and transitions through its
    state machine with a persisted, audited history;
  * subsumption_path + subsumption_validator: a chain with a deliberate
    gap is built and universal-only validation surfaces it.
"""

from __future__ import annotations

import pytest

# Fail fast, with an actionable message, if loomground_solver is not on the
# path — the whole point of this suite is exercising the real dependency.
pytest.importorskip(
    "loomground_solver",
    reason="loomground_solver not importable — set PYTHONPATH to include "
           "<loomground-solver>/src (see this file's module docstring).",
)

import loomground_norm as norm
from loomground_solver.temporal import Date, RelativeDeadline

SENTENCE = (
    "The controller shall notify the supervisory authority within 72 hours "
    "of becoming aware of a personal data breach."
)


def test_public_surface_imports():
    """Every name declared in loomground_norm.__all__ resolves."""
    for name in norm.__all__:
        assert hasattr(norm, name), f"declared but missing: {name}"
    assert norm.__version__


def test_rule_extractor_reads_the_five_slots():
    facets = norm.extract_rules(SENTENCE)
    assert facets, "extractor found no rule in a plainly operative sentence"
    f = facets[0]
    assert f.modal == "obligation"
    assert "controller" in f.subject.lower()
    assert f.raw_sentence


def test_deontic_lifts_a_grounded_obligation_formula():
    formulae = norm.extract_formulae(SENTENCE)
    assert formulae, "no deontic formula lifted"
    formula = formulae[0]
    assert formula.operator == norm.OP_OBLIGATION
    assert norm.obligation_is_grounded(formula)
    rendered = formula.render()
    assert rendered.startswith(f"{norm.OP_OBLIGATION}(")
    # the dual identity is exposed, never used to infer anything further.
    assert formula.dual().startswith("¬P(")


def test_deontic_conflict_detection_flags_same_bearer_same_action_clash():
    obligation = norm.formula_from_rule(
        norm.RuleFacet(subject="controller", modal="obligation",
                       action="disclose the incident", raw_sentence=SENTENCE,
                       confidence=0.9))
    prohibition = norm.formula_from_rule(
        norm.RuleFacet(subject="controller", modal="prohibition",
                       action="disclose the incident", raw_sentence=SENTENCE,
                       confidence=0.9))
    conflicts = norm.detect_conflicts([obligation, prohibition])
    assert len(conflicts) == 1
    assert conflicts[0]["kind"] == "deontic-conflict"


class _FakeParty:
    def __init__(self, role: str) -> None:
        self.role = role


class _FakeInstrument:
    """Minimal stand-in satisfying loomground_norm.ports.SourceInstrument
    structurally — no import from loomground_norm required to write one."""

    def __init__(self, ref: str) -> None:
        self.ref = ref
        self.parties = [_FakeParty("controller"), _FakeParty("processor")]
        self._signing_date = Date("2026-01-01")

    def resolve_deadline(self, rel: RelativeDeadline):
        return self._signing_date.add(rel)


def test_obligation_runtime_tracks_a_duty_end_to_end(tmp_path):
    facets = norm.extract_rules(SENTENCE)
    registry = norm.ObligationRegistry(tmp_path)
    contract = _FakeInstrument("dpa-1@1")

    rule_record = {"id": "rule:abc123", "norm": {
        "modal": facets[0].modal, "subject": facets[0].subject,
        "action": facets[0].action, "counterparty": "supervisory-authority",
    }}
    result = registry.instantiate(contract, [rule_record], actor="ingest")
    assert result["created"], "no obligation instantiated from an obligation-modal rule"

    oid = result["created"][0]
    obligation = registry.get(oid)
    assert obligation is not None
    assert obligation.state == "pending"
    assert obligation.obligor_role == "controller"

    # machine transition (the scheduler's job elsewhere; simulated here)
    updated = registry.advance(oid, "due_soon", reason="within warning window")
    assert updated["state"] == "due_soon"

    # human resolution requires a named actor and a reason.
    with pytest.raises(norm.ObligationError):
        registry.resolve(oid, "satisfied", actor="system", reason="")

    resolved = registry.resolve(oid, "satisfied", actor="dpo@example.org",
                                reason="notification sent within the deadline")
    assert resolved["state"] == "satisfied"
    assert registry.history(oid)[-1]["actor"] == "dpo@example.org"

    # persistence round-trips through a fresh registry over the same folder.
    reloaded = norm.ObligationRegistry(tmp_path)
    assert reloaded.get(oid).state == "satisfied"


def test_subsumption_chain_surfaces_a_retrieval_gap():
    # "ausnahme" (exception) is deliberately never supplied — a legitimate
    # omission — but "tatbestand" is missing too, which IS a retrieval gap.
    atoms = [
        {"role": "norm", "ref": "Art. 33(1) GDPR", "source": "§ 33 GDPR",
         "authority_tier": 1},
        {"role": "subsumtion", "ref": "breach-within-72h", "source": "case file",
         "authority_tier": 2},
        {"role": "ergebnis", "ref": "notification-due", "source": "case file",
         "authority_tier": 2},
    ]
    chain = norm.build_subsumption(atoms)
    assert not chain.complete
    assert any(g.kind == "retrieval" for g in chain.gaps)

    report = norm.validate_subsumption(chain)
    assert report.legal_system == "(universal-only)"
    assert not report.ok
    codes = {f.code for f in report.violations}
    assert "U2-retrieval-gap" in codes
