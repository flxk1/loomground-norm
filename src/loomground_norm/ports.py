# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Injected ports — the seam between the norm plane and its hosts.

Mirrors :mod:`loomground_solver.ports`: this plane carries no dated-instrument
model and no persistence/audit sink of its own; those arrive through the thin
Protocol ports defined here. A host wires in a concrete :class:`SourceInstrument`
(whatever dated, party-bearing instrument it tracks obligations against — RVND's
``contracts.instance.ContractInstance`` is one instance, a compliance
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

    Structural, not nominal: a host's own instrument class (RVND's
    ``ContractInstance``, for one) satisfies this by shape — no import edge
    back into the host is required.
    """

    ref: str          #: stable identity, e.g. "cid@version"
    parties: list     #: objects exposing at least a ``.role: str``

    def resolve_deadline(self, rel: RelativeDeadline) -> Optional[Date]:
        """Resolve a relative deadline against this instrument's known event
        dates; ``None`` when it cannot be resolved (never guessed)."""
        ...


@runtime_checkable
class LegalSystemPack(Protocol):
    """One jurisdiction family's regional norm-theory rules.

    RVND's ``legal_systems.get(code)`` returns an object satisfying this
    shape; the norm plane defines the universal layer of subsumption
    validation and treats the regional layer (citation forms, collision
    principles) as optional and injected — jurisdiction-family selection
    is a legal-domain decision, not this plane's.
    """

    code: str
    citation_markers: tuple[str, ...]
    conflict_principles: tuple[str, ...]


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
