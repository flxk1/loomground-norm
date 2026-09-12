# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Injected ports — the seam between the norm plane and its hosts.

Mirrors :mod:`loomground_solver.ports`: this plane carries no dated-instrument
model and no persistence/audit sink of its own; those arrive through the thin
Protocol ports defined here. A host wires in a concrete :class:`SourceInstrument`
(whatever dated, party-bearing instrument it tracks obligations against — a
contract instance is one example, while a compliance
undertaking or a settlement could be another) and a concrete :class:`AuditSink`
(its own signed mutation log, or none). :class:`NullAuditSink` is the no-op
default so the plane runs standalone.

Pure stdlib (``typing`` only).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from loomground_solver.temporal import Date, RelativeDeadline


@runtime_checkable
class SourceInstrument(Protocol):
    """The dated, party-bearing instrument an obligation is tracked against.

    Structural, not nominal: a host's own instrument class satisfies this by
    shape — no import edge
    back into the host is required.
    """

    ref: str          #: stable identity, e.g. "cid@version"
    parties: list     #: objects exposing at least a ``.role: str``

    def resolve_deadline(self, rel: RelativeDeadline) -> Optional[Date]:
        """Resolve a relative deadline against this instrument's known event
        dates; ``None`` when it cannot be resolved (never guessed)."""
        ...


@runtime_checkable
class RegionalPack(Protocol):
    """One rule-system's regional collision-resolution rules.

    Domain-neutral: the norm plane defines the universal layer of subsumption
    validation and treats the regional layer (which collision principles a
    rule-system recognises) as optional and injected. The principles are
    opaque tokens — this plane does not interpret them and carries no
    rule-system of its own; selecting which one applies is a consumer's
    decision. ``region`` is a free-form label the consumer chooses.
    """

    region: str
    collision_principles: tuple[str, ...]


@runtime_checkable
class AuditSink(Protocol):
    """Append one audit event to the host's trail."""

    def log(self, event: dict) -> Optional[str]:
        """Return an opaque receipt (e.g. a chain hash) or ``None``."""
        ...


class NullAuditSink:
    """No-op sink: the standalone default when no host audit trail is injected."""

    def log(self, event: dict) -> Optional[str]:
        return None
