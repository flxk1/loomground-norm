# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""The obligation scheduler — a deterministic, replayable ``tick`` (skeleton).

Ported from ``server/src/workspaces/obligation_scheduler.py`` in rvnd. The
source module is real and tested there, but two of its dependencies are
host-specific in a way this staging pass has not yet inverted:

  * ``.action_gate`` — RVND's runtime action-gate (footprint x autonomy grade
    x standing approvals). The scheduler's proposals ("remind the obligor",
    "surface a breach candidate") are routed through it before anything
    fires. That is a genuine N -> G dependency in the source tree: a
    governance-specific runtime primitive consumed by a general-normative
    module. The fix is dependency inversion, not a straight copy — this
    plane should define an ``ActionGate`` protocol (a callable taking an
    abstract ``FollowUp`` and returning an abstract ``Decision``) in
    :mod:`.ports`, and RVND's own scheduling glue supplies ``action_gate.gate``
    as the concrete implementation. Nothing here should import
    ``ActionRequest``/``GateDecision``/``StandingApproval`` by name.
  * ``.contracts.instance.ContractRegistry`` — resolves the
    :class:`~loomground_norm.ports.SourceInstrument` a given obligation's
    deadline is relative to. :mod:`.obligation_runtime` already takes this as
    an injected instrument per call; the scheduler needs the equivalent for
    its own per-obligation contract lookup — a small ``InstrumentSource``
    protocol (``get(ref: str) -> Optional[SourceInstrument]``), not a direct
    import of RVND's contract registry.

The pure date-arithmetic core (:func:`target_state`) has no such coupling —
it is real below. The scheduler class itself is a signature-level skeleton:
wire the two ports above before it runs standalone.
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
    "ActionGate", "InstrumentSource", "ObligationScheduler",
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
# class + footprint tag — the vocabulary a host's own gate interprets. This
# plane assigns no verdict to either.
ACTION_FOR_STATE = {
    "due_soon": ("remind-obligor", ("external-publish",)),
    "due": ("remind-obligor", ("external-publish",)),
    "breached_candidate": ("surface-breach-candidate", ()),
}


@dataclass
class FollowUp:
    """One action the scheduler wants to take. Carries no verdict — a host's
    injected :class:`ActionGate` decides GO/CONDITIONAL/NO-GO; this plane
    only proposes."""

    obligation_id: str
    action_class: str                      # remind-obligor | surface-breach-candidate
    target_state: str
    footprint: tuple[str, ...] = ()
    affected_parties: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"obligation_id": self.obligation_id, "action_class": self.action_class,
                "target_state": self.target_state, "footprint": self.footprint,
                "affected_parties": self.affected_parties}


@dataclass
class SchedulerReport:
    as_of: str
    transitions: list[dict] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)   # {follow_up, decision}
    unresolved: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"as_of": self.as_of, "transitions": self.transitions,
                "proposals": self.proposals, "unresolved": self.unresolved,
                "candidates": self.candidates}


@runtime_checkable
class ActionGate(Protocol):
    """Injected gate: decide a proposed follow-up. RVND's
    ``action_gate.gate`` (wrapped to accept a :class:`FollowUp`) satisfies
    this; the plane ships no default — a scheduler run without one skips
    gating and returns proposals ungated (visible in the report, never
    silently applied)."""

    def __call__(self, follow_up: FollowUp) -> dict:
        """Return a JSON-shaped decision, e.g. ``{"verdict": "go"|"conditional"|"no-go", ...}``."""
        ...


@runtime_checkable
class InstrumentSource(Protocol):
    """Resolve a contract-ref ("cid@version") to a
    :class:`~loomground_norm.ports.SourceInstrument`, or ``None``."""

    def get(self, ref: str) -> Optional[SourceInstrument]:
        ...


class ObligationScheduler:
    """Sweeps one folder's obligations against the calendar.

    The full sweep is ported from rvnd's
    ``server/src/workspaces/obligation_scheduler.py`` behind two injected
    ports — no host coupling remains:

      * :class:`ActionGate` — decides a proposed :class:`FollowUp`. Without
        one, ``tick`` still runs and records each follow-up ungated
        (``decision`` is ``None`` in ``report.proposals``), never applying it;
      * :class:`InstrumentSource` — resolves an obligation's contract-ref to a
        :class:`~loomground_norm.ports.SourceInstrument` for relative-deadline
        resolution (``_contract_for``); ``None`` leaves the deadline
        unresolved, surfaced in ``report.unresolved``.

    The jurisdiction-neutral ``deadline_shift`` handling and the
    weekend/public-holiday caveats are ported verbatim.
    """

    def __init__(self, obligations: ObligationRegistry, *,
                instruments: Optional[InstrumentSource] = None,
                warning_window: Duration = DEFAULT_WARNING_WINDOW,
                action_gate: Optional[ActionGate] = None,
                deadline_shift: Optional[Callable[[Date], Date]] = None):
        self.obligations = obligations
        self.instruments = instruments
        self.window = warning_window
        self.action_gate = action_gate
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
        the transition. Ported from rvnd's
        ``obligation_scheduler.py::ObligationScheduler.tick`` behind the
        :class:`ActionGate` / :class:`InstrumentSource` ports."""
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
        """Emit one :class:`FollowUp` for an arrival state and, if an
        :class:`ActionGate` is injected, its verdict. Without a gate the
        follow-up is recorded ungated (``decision`` is ``None``) — visible in
        the report, never silently applied."""
        spec = ACTION_FOR_STATE.get(state)
        if spec is None:
            return
        action_class, footprint = spec
        # A reminder going OUT to the obligor names the obligor as the affected
        # party — the disclosure has an addressee by construction. Surfacing a
        # breach candidate is internal (no parties).
        ob = next((o for o in self.obligations.in_state(state)
                   if o.obligation_id == oid), None)
        affected = ((ob.obligor_role or "obligor",)
                    if "external-publish" in footprint and ob else ())
        follow_up = FollowUp(
            obligation_id=oid, action_class=action_class,
            target_state=state, footprint=tuple(footprint),
            affected_parties=affected)
        decision = self.action_gate(follow_up) if self.action_gate else None
        report.proposals.append({"follow_up": follow_up.to_dict(),
                                 "decision": decision})
