# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""ObligationScheduler.tick — the sweep, exercised against fake ports.

Covers the behavior behind the InstrumentSource port, with NO governance gate
(the scheduler proposes ungated; a consumer classifies verdict/footprint):

  * calendar-driven state advancement (pending -> due_soon -> due ->
    breached_candidate) by date arithmetic only;
  * determinism / replay safety (a second tick at the same as_of is a no-op);
  * the weekend caveat when no shift rule is configured;
  * a configured ``deadline_shift`` deferring the effective deadline;
  * an unresolvable relative deadline surfaced, never guessed;
  * ungated follow-up proposals (no footprint, no verdict, no decision), with
    the obligor named as affected party on outward reminders.
"""

from __future__ import annotations

import pytest

pytest.importorskip("loomground_solver")

import loomground_norm as norm
from loomground_norm.obligation_scheduler import ObligationScheduler
from loomground_solver.temporal import Date, Duration, RelativeDeadline, weekend_shift


# ── fakes satisfying the declared ports ─────────────────────────────────────────

class _FakeParty:
    def __init__(self, role: str) -> None:
        self.role = role


class _FakeInstrument:
    """Structural SourceInstrument: resolves a relative deadline off one event."""

    def __init__(self, ref: str, signing: str = "2026-01-01") -> None:
        self.ref = ref
        self.parties = [_FakeParty("processor"), _FakeParty("controller")]
        self._events = {"signing": Date(signing)}

    def resolve_deadline(self, rel: RelativeDeadline):
        return rel.resolve(self._events)


class _FakeInstrumentSource:
    def __init__(self, *instruments: _FakeInstrument) -> None:
        self._by_ref = {i.ref: i for i in instruments}

    def get(self, ref: str):
        cid = ref.partition("@")[0]
        return self._by_ref.get(ref) or self._by_ref.get(cid)


# ── helpers ─────────────────────────────────────────────────────────────────────

def _reg(tmp_path):
    return norm.ObligationRegistry(tmp_path)


def _seed(reg, oid, *, deadline_date=None, deadline_rel=None,
          state="pending", obligor="processor", contract_ref="dpa@1"):
    ob = norm.Obligation(
        obligation_id=oid, contract_ref=contract_ref, rule_id="rule:x",
        obligor_role=obligor,
        deadline_date=Date(deadline_date) if deadline_date else None,
        deadline_rel=deadline_rel, state=state)
    reg.items[oid] = dict(ob.to_dict(), first_seen="t", last_seen="t",
                          history=[{"state": state, "at": "t",
                                    "actor": "test", "reason": "seed"}])
    reg._flush()


# ── tests ───────────────────────────────────────────────────────────────────────

def test_tick_advances_states_by_calendar(tmp_path):
    reg = _reg(tmp_path)
    _seed(reg, "o-pending", deadline_date="2026-06-01")     # far future
    _seed(reg, "o-soon", deadline_date="2026-01-10")        # within 14d window
    _seed(reg, "o-due", deadline_date="2026-01-05")         # == as_of
    _seed(reg, "o-past", deadline_date="2025-12-20")        # past

    report = ObligationScheduler(reg).tick(as_of=Date("2026-01-05"))

    to = {t["obligation_id"]: t["to"] for t in report.transitions}
    assert "o-pending" not in to                     # no transition: still pending
    assert to["o-soon"] == "due_soon"
    assert to["o-due"] == "due"
    assert to["o-past"] == "breached_candidate"
    assert report.candidates == ["o-past"]
    assert reg.get("o-pending").state == "pending"


def test_tick_is_idempotent_and_replayable(tmp_path):
    reg = _reg(tmp_path)
    _seed(reg, "o-due", deadline_date="2026-01-05")
    sched = ObligationScheduler(reg)

    first = sched.tick(as_of=Date("2026-01-05"))
    assert len(first.transitions) == 1
    assert len(first.proposals) == 1

    second = sched.tick(as_of=Date("2026-01-05"))
    assert second.transitions == []                  # monotone: no second move
    assert second.proposals == []                    # no duplicate proposal
    assert reg.get("o-due").state == "due"


def test_weekend_caveat_flagged_without_shift(tmp_path):
    reg = _reg(tmp_path)
    _seed(reg, "o-sat", deadline_date="2026-01-03")  # a Saturday
    report = ObligationScheduler(reg).tick(as_of=Date("2026-01-03"))

    t = report.transitions[0]
    assert t["to"] == "due"
    assert t["weekend_deadline"] is True
    assert t["shift_rule_applied"] is False
    assert "weekend" in t["caveat"]
    assert "public holidays not checked" in t["caveat"]
    assert t["effective_deadline"] == "2026-01-03"   # no shift applied


def test_deadline_shift_defers_effective_deadline(tmp_path):
    reg = _reg(tmp_path)
    _seed(reg, "o-sat", deadline_date="2026-01-03")  # Saturday
    report = ObligationScheduler(
        reg, deadline_shift=weekend_shift).tick(as_of=Date("2026-01-03"))

    t = report.transitions[0]
    # Saturday deadline shifts to Monday 2026-01-05, still in the future ->
    # due_soon, not due.
    assert t["to"] == "due_soon"
    assert t["shift_rule_applied"] is True
    assert t["effective_deadline"] == "2026-01-05"
    assert t["caveat"] == ""                          # due_soon carries no caveat


def test_unresolved_relative_deadline_is_surfaced(tmp_path):
    reg = _reg(tmp_path)
    rel = RelativeDeadline(event="signing", offset=Duration.parse("P30D"))
    _seed(reg, "o-rel", deadline_rel=rel)

    # No InstrumentSource -> the relative deadline cannot resolve.
    report = ObligationScheduler(reg).tick(as_of=Date("2026-06-01"))
    assert report.unresolved == ["o-rel"]
    assert report.transitions == []


def test_instrument_source_resolves_relative_deadline(tmp_path):
    reg = _reg(tmp_path)
    rel = RelativeDeadline(event="signing", offset=Duration.parse("P30D"))
    _seed(reg, "o-rel", deadline_rel=rel, contract_ref="dpa@1")
    src = _FakeInstrumentSource(_FakeInstrument("dpa@1", signing="2026-01-01"))

    # Deadline resolves to 2026-01-31; as_of well past -> breached_candidate.
    report = ObligationScheduler(reg, instruments=src).tick(as_of=Date("2026-03-01"))
    assert report.unresolved == []
    assert report.transitions[0]["to"] == "breached_candidate"
    assert report.transitions[0]["deadline"] == "2026-01-31"


def test_outward_reminder_proposal_names_affected_party(tmp_path):
    reg = _reg(tmp_path)
    _seed(reg, "o-soon", deadline_date="2026-01-10", obligor="processor")

    report = ObligationScheduler(reg).tick(as_of=Date("2026-01-05"))
    prop = report.proposals[0]
    assert prop["action_class"] == "remind-obligor"
    assert prop["affected_parties"] == ("processor",)   # outward reminder names obligor
    assert prop["obligation_id"] == "o-soon"
    assert prop["target_state"] == "due_soon"
    # ungated: the plane proposes, it does not gate.
    assert "footprint" not in prop                       # governance vocab gone
    assert "verdict" not in prop and "decision" not in prop


def test_breach_candidate_proposal_is_internal_and_ungated(tmp_path):
    reg = _reg(tmp_path)
    _seed(reg, "o-past", deadline_date="2025-12-20")
    report = ObligationScheduler(reg).tick(as_of=Date("2026-01-05"))

    prop = report.proposals[0]
    assert prop["action_class"] == "surface-breach-candidate"
    assert prop["affected_parties"] == ()               # internal, no addressee
    assert "footprint" not in prop
    assert "decision" not in prop
