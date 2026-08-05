# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Validate a multi-hop / subsumption output against norm theory — two layers.

A built subsumption chain (``subsumption_path.Subsumption``) is only as good as
its conformance to the reasoning invariants. Those invariants come in two
layers:

  * UNIVERSAL norm theory — true in every rule-system: every step is sourced
    (provenance); a result must be reached *through* a subsumption (you cannot
    conclude without subsuming); every step carries an authority weight; a
    retrieval or conflict gap voids the chain.
  * REGIONAL norm theory — an injected, domain-neutral
    :class:`~loomground_norm.ports.RegionalPack`: a collision may only be
    resolved by a principle the rule-system recognises, and otherwise must
    escalate (never auto-resolved). The principle tokens are opaque; this
    plane does not interpret them.

The validator REUSES the substrate: universal checks mirror the norm-theory
contract's invariants; the regional check reads the injected pack — which
rule-system applies is a consumer's decision, so this plane carries no pack of
its own and runs universal-only when none is supplied. It returns a layered
report; it never repairs the chain or resolves a conflict — it judges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from loomground_solver.norm_contract import Level  # reuse PASS / VIOLATION / ESCALATE
from .ports import RegionalPack
from .subsumption_path import Subsumption


@dataclass
class Finding:
    layer: str               # "universal" | "regional"
    code: str
    level: Level
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"layer": self.layer, "code": self.code,
                "level": self.level.value, "message": self.message}


@dataclass
class ValidationReport:
    region: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def violations(self) -> list[Finding]:
        return [f for f in self.findings if f.level is Level.VIOLATION]

    @property
    def escalations(self) -> list[Finding]:
        return [f for f in self.findings if f.level is Level.ESCALATE]

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {"region": self.region, "ok": self.ok,
                "must_escalate": bool(self.escalations),
                "findings": [f.to_dict() for f in self.findings]}


def validate(sub: Subsumption, *, pack: Optional[RegionalPack] = None) -> ValidationReport:
    """Validate a subsumption chain. ``pack`` is the active, domain-neutral
    :class:`~loomground_norm.ports.RegionalPack` (a consumer chooses which
    rule-system it stands for); omitted, only the universal layer runs and the
    report's ``region`` reads ``"(universal-only)"``."""
    rep = ValidationReport(region=pack.region if pack else "(universal-only)")

    # ── UNIVERSAL (jurisdiction-agnostic norm theory) ───────────────────────
    for step in sub.steps:
        if not step.source:
            rep.findings.append(Finding("universal", "U1-provenance", Level.VIOLATION,
                                        f"step '{step.role}' has no source (Quellenbindung)"))
        if not isinstance(step.authority_tier, int):
            rep.findings.append(Finding("universal", "U3-authority", Level.VIOLATION,
                                        f"step '{step.role}' carries no authority weight"))
    roles = [s.role for s in sub.steps]
    if "ergebnis" in roles and "subsumtion" not in roles:
        rep.findings.append(Finding("universal", "U4-subsumtion", Level.VIOLATION,
                                    "an Ergebnis without a Subsumtion — conclusion not reached through subsumption"))
    for g in sub.gaps:
        if g.kind == "retrieval":
            rep.findings.append(Finding("universal", "U2-retrieval-gap", Level.VIOLATION,
                                        f"chain broken: {g.detail}"))
        if g.kind == "conflict":
            rep.findings.append(Finding("universal", "U5-conflict", Level.ESCALATE,
                                        f"unresolved collision: {g.detail}"))
        if g.kind in ("context", "authority"):
            rep.findings.append(Finding("universal", f"U-{g.kind}", Level.ESCALATE,
                                        f"{g.kind} gap surfaced: {g.detail}"))
    if not any(f.layer == "universal" for f in rep.findings):
        rep.findings.append(Finding("universal", "U0", Level.PASS,
                                    "universal norm theory satisfied"))

    # ── REGIONAL (the injected, domain-neutral pack, if any) ─────────────────
    if pack is None:
        rep.findings.append(Finding("regional", "R-none", Level.PASS,
                                    "no regional pack injected — regional layer skipped"))
        return rep

    # a collision may be resolved only by a principle the rule-system
    # recognises — otherwise it must escalate, never auto-resolve.
    if any(g.kind == "conflict" for g in sub.gaps):
        rep.findings.append(Finding("regional", "R1-collision-principle", Level.ESCALATE,
                                    f"resolve under {pack.region} principles "
                                    f"({', '.join(pack.collision_principles)}) — human, not auto"))
    if not any(f.layer == "regional" for f in rep.findings):
        rep.findings.append(Finding("regional", "R0", Level.PASS,
                                    f"regional ({pack.region}) norm theory satisfied"))
    return rep
