# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""The obligation scheduler — a deterministic, replayable ``tick``.

Sweeps one folder's open obligations against the calendar and advances each to
the state its deadline arithmetic warrants (:func:`target_state`), emitting an
UNGATED :class:`FollowUp` proposal per arrival state. The one host coupling is
inverted behind a single injected port:

  * :class:`InstrumentSource` — resolves the
    :class:`~loomground_norm.ports.SourceInstrument` a given obligation's
    deadline is relative to (``get(ref: str) -> Optional[SourceInstrument]``).
    :mod:`.obligation_runtime` already takes an instrument per call; the
    scheduler needs the equivalent for its own per-obligation lookup. Without
    a source, a relative deadline stays unresolved (surfaced, never guessed).

This plane only PROPOSES. It attaches no verdict, no footprint, and no
decision to a follow-up — whether an action may fire, and what its disclosure
footprint is, is a governance concern a downstream consumer classifies on its
side. ``tick`` and its arithmetic core are fully implemented and tested below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _pydate
from typing import Any, Callable, Iterable, Optional, Protocol, runtime_checkable

from .obligation_runtime import Obligation, ObligationRegistry
from .ports import AuditSink, SourceInstrument
from loomground_solver.temporal import Date, Duration

__all__ = [
    "DEFAULT_WARNING_WINDOW", "target_state", "FollowUp", "SchedulerReport",
    "InstrumentSource", "ObligationScheduler",
]

DEFAULT_WARNING_WINDOW = Duration.parse("P14D")


def target_state(deadline: Date, as_of: Date, window: Duration) -> str:
    """Pure date arithmetic -> the state an open obligation should be in.

    Ported unchanged from the source module (no host coupling there)."""
    if as_of.as_date() > deadline.as_date():
        return "breached_candidate"
    if as_of.as_date() == deadline.as_date():
        return "due"
    warn_from = window.add_to(deadline, sign=-1)
    if as_of.as_date() >= warn_from.as_date():
        return "due_soon"
    return "pending"


_FORWARD = {"pending": 0, "due_soon": 1, "due": 2, "breached_candidate": 3}

# What the scheduler proposes at each arrival state, as an abstract action
# class. The plane assigns no verdict and no footprint — a consumer classifies
# those on its side.
ACTION_FOR_STATE = {
    "due_soon": "remind-obligor",
    "due": "remind-obligor",
    "breached_candidate": "surface-breach-candidate",
}

# Action classes that address a party (a reminder goes OUT to the obligor);
# the rest are internal (surfacing a breach candidate concerns no one).
_ADDRESSED = {"remind-obligor"}


@dataclass
class FollowUp:
    """One action the scheduler proposes — ungated. It carries what (the
    action class), when (the arrival state), and who is affected. It carries
    no footprint, no verdict, and no decision: a governance consumer
    classifies those on its side."""

    obligation_id: str
    action_class: str                      # remind-obligor | surface-breach-candidate
    target_state: str
    affected_parties: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"obligation_id": self.obligation_id, "action_class": self.action_class,
                "target_state": self.target_state,
                "affected_parties": self.affected_parties}


@dataclass
class SchedulerReport:
    as_of: str
    transitions: list[dict] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)   # ungated FollowUp dicts
    unresolved: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"as_of": self.as_of, "transitions": self.transitions,
                "proposals": self.proposals, "unresolved": self.unresolved,
                "candidates": self.candidates}


@runtime_checkable
class InstrumentSource(Protocol):
    """Resolve a contract-ref ("cid@version") to a
    :class:`~loomground_norm.ports.SourceInstrument`, or ``None``."""

    def get(self, ref: str) -> Optional[SourceInstrument]:
        ...


class ObligationScheduler:
    """Sweeps one folder's obligations against the calendar.

    The full sweep runs behind one injected port — no host coupling remains:

      * :class:`InstrumentSource` — resolves an obligation's contract-ref to a
        :class:`~loomground_norm.ports.SourceInstrument` for relative-deadline
        resolution (``_contract_for``); ``None`` leaves the deadline
        unresolved, surfaced in ``report.unresolved``.

    Every arrival state emits an UNGATED :class:`FollowUp` proposal — the
    plane proposes but never gates. The jurisdiction-neutral ``deadline_shift``
    handling and the weekend/public-holiday caveats travel with each transition.
    """

    def __init__(self, obligations: ObligationRegistry, *,
                instruments: Optional[InstrumentSource] = None,
                warning_window: Duration = DEFAULT_WARNING_WINDOW,
                deadline_shift: Optional[Callable[[Date], Date]] = None):
        self.obligations = obligations
        self.instruments = instruments
        self.window = warning_window
        self.deadline_shift = deadline_shift

    def _open(self) -> Iterable[Obligation]:
        for state in ("pending", "due_soon", "due"):
            yield from self.obligations.in_state(state)

    def _contract_for(self, ob: Obligation) -> Optional[SourceInstrument]:
        if self.instruments is None:
            return None
        return self.instruments.get(ob.contract_ref)

    # ── the tick ────────────────────────────────────────────────────────────
    def tick(self, as_of: Optional[Date] = None) -> SchedulerReport:
        """Sweep every open obligation against the calendar at ``as_of``.

        Deterministic and replay-safe: state advancement is monotone
        (``_FORWARD``) and idempotent — a second ``tick`` at the same ``as_of``
        produces no second transition and no duplicate proposal (proposals are
        emitted only alongside a transition, which fires once).

        Jurisdiction-neutral by default: the plane OBSERVES that a deadline
        falls on a weekend (a calendar fact) and flags that the governing
        law's extension rules may defer it; it APPLIES such a rule only when
        one is configured (``deadline_shift``, supplied by a jurisdiction
        pack). Public holidays are never resolved — the caveat travels with
        the transition. Runs behind the :class:`InstrumentSource` port."""
        as_of = as_of or Date(_pydate.today().isoformat())
        report = SchedulerReport(as_of=as_of.iso)
        for ob in list(self._open()):
            contract = self._contract_for(ob)
            deadline = ob.resolved_deadline(contract)
            if deadline is None:
                report.unresolved.append(ob.obligation_id)
                continue
            effective = (self.deadline_shift(deadline)
                         if self.deadline_shift else deadline)
            shifted = effective.iso != deadline.iso
            on_weekend = deadline.as_date().weekday() >= 5
            target = target_state(effective, as_of, self.window)
            if _FORWARD.get(target, 0) > _FORWARD.get(ob.state, 99):
                reason = f"as_of {as_of.iso} vs deadline {deadline.iso}"
                caveat = ""
                if shifted:
                    reason += (f" → effective {effective.iso} "
                               "(configured deadline-shift rule)")
                elif on_weekend and target in ("due", "breached_candidate"):
                    caveat = ("deadline falls on a weekend — extension rules "
                              "of the governing law may defer it; verify "
                              "before acting")
                    reason += f" ({caveat})"
                if target in ("due", "breached_candidate"):
                    caveat = (caveat + "; " if caveat else "") + \
                        "public holidays not checked"
                self.obligations.advance(ob.obligation_id, target, reason=reason)
                report.transitions.append(
                    {"obligation_id": ob.obligation_id, "from": ob.state,
                     "to": target, "deadline": deadline.iso,
                     "effective_deadline": effective.iso,
                     "weekend_deadline": on_weekend,
                     "shift_rule_applied": shifted,
                     "caveat": caveat})
                self._propose(report, ob.obligation_id, target)
        report.candidates = [o.obligation_id
                             for o in self.obligations.in_state("breached_candidate")]
        return report

    def _propose(self, report: SchedulerReport, oid: str, state: str) -> None:
        """Emit one UNGATED :class:`FollowUp` for an arrival state — recorded
        in ``report.proposals`` with no verdict and no decision. A governance
        consumer classifies footprint/verdict on its side."""
        action_class = ACTION_FOR_STATE.get(state)
        if action_class is None:
            return
        # A reminder going OUT to the obligor names the obligor as the affected
        # party — the action has an addressee by construction. Surfacing a
        # breach candidate is internal (no parties).
        ob = next((o for o in self.obligations.in_state(state)
                   if o.obligation_id == oid), None)
        affected = ((ob.obligor_role or "obligor",)
                    if action_class in _ADDRESSED and ob else ())
        follow_up = FollowUp(
            obligation_id=oid, action_class=action_class,
            target_state=state, affected_parties=affected)
        report.proposals.append(follow_up.to_dict())
