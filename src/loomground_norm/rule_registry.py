# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Rule registry — every span-norm as a typed, persisted, audited record.

The unit is the **span**: one contiguous passage of source text (a contract
clause, a statutory sentence, a Randnummer) carries exactly one norm.
:class:`SpanNorm` is the plane's typed record of that.

This module ports the span-*placement* behavior — span placement, document
re-pinning, orphan tracking, and the search query — with every host coupling
replaced by an injected port. What stays a port:

  * **URN minting** (``urn_minter``) — canonical URN minting is the identity
    spine's job, not this plane's. An injected ``urn_minter: Callable[[str],
    str]`` replaces a direct import; without one, ``SpanNorm.canonical_urn``
    stays empty (visible, not invented).
  * **audit** (``audit_sink``) — the :class:`~loomground_norm.ports.AuditSink`
    pattern already used in :mod:`.obligation_runtime`; a host's signed
    mutation log is one implementation,
    :class:`~loomground_norm.ports.NullAuditSink` the standalone default.

The registry produces spans and rules. It does NOT anchor them onto governing
instruments/jurisdictions, and it does NOT segment a law's own text into
provisions — placing a norm onto the entities that govern it is a legal-domain
concern owned by a downstream consumer, not this general plane.

Idempotent (keyed by source + pinpoint + span text), provenance-stamped, and
audited through the injected sink. Pure stdlib beyond the extractor.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .ports import AuditSink, NullAuditSink
from .rule_extractor import RuleFacet, extract_rules

__all__ = [
    "SpanNorm", "UrnMinter", "RuleRegistry", "place_into_registry",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rule_id(source_document: str, span_text: str) -> str:
    h = hashlib.sha256()
    h.update((source_document or "inline").encode("utf-8"))
    h.update(b"|")
    h.update(span_text.strip().encode("utf-8"))
    return "rule:" + h.hexdigest()[:24]


def _urn_seed(rid: str) -> str:
    """The content string a ``urn_minter`` mints the span's canonical URN from
    — ``"rule-" + <content hash>``, deterministic per (document, pinpoint,
    text) and stable across re-pinning, which mutates the record in place, so
    an injected minter reproduces the same identity-spine address."""
    return "rule-" + rid.partition(":")[2]


@dataclass
class SpanNorm:
    id: str
    span: dict                 # {document, start, end, pinpoint, text, ...}
    norm: dict                 # {modal, subject, action, condition, exception, language}
    kind: str = "rule"         # rule | clause | norm
    workspace: str = ""
    user: str = ""
    source: str = "ingest"
    canonical_urn: str = ""    # empty unless a urn_minter port is injected
    obligation_urns: list = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_from_facet(f: RuleFacet) -> dict:
    return {"modal": f.modal, "subject": f.subject, "action": f.action,
            "condition": f.condition, "exception": f.exception,
            "language": f.language,
            "incident": getattr(f, "incident", ""),
            "counterparty": getattr(f, "counterparty", ""),
            "condition_kind": getattr(f, "condition_kind", "")}


#: ``content -> urn`` — identity-spine minting, injected. See module docstring.
UrnMinter = Callable[[str], str]


class RuleRegistry:
    """Per-workspace store of :class:`SpanNorm` records.

    Persistence is one-scoped: ``<folder>/<subdir>/rule-items.jsonl``, so the
    folder's own rules travel with the folder. ``subdir`` is a neutral,
    configurable name (default ``"rule-items"``) — no domain is baked into the
    path.
    """

    def __init__(self, folder: str | Path, *, user: str = "",
                 subdir: str = "rule-items",
                 urn_minter: Optional[UrnMinter] = None,
                 audit_sink: Optional[AuditSink] = None):
        self.folder = Path(folder)
        self.user = user
        self.subdir = subdir
        self.urn_minter = urn_minter
        self.audit_sink = audit_sink or NullAuditSink()
        self.items: dict[str, dict] = {}     # id -> record (workspace scope)
        self.load()

    # ── persistence ───────────────────────────────────────────────────────────
    def _workspace_path(self) -> Path:
        return self.folder / self.subdir / "rule-items.jsonl"

    def load(self) -> None:
        p = self._workspace_path()
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.items[r["id"]] = r
        # Records written before an identity spine self-heal on open — but only
        # when a urn_minter is injected; without one, an empty urn stays empty
        # (visible abstention, never invented).
        if not self.urn_minter:
            return
        dirty = False
        for rid, r in self.items.items():
            if not r.get("canonical_urn"):
                r["canonical_urn"] = self.urn_minter(_urn_seed(rid))
                r.setdefault("obligation_urns", [])
                dirty = True
        if dirty:
            self._flush_workspace()

    def _flush_workspace(self) -> None:
        p = self._workspace_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                               for r in self.items.values())
                     + ("\n" if self.items else ""), encoding="utf-8")

    def _log(self, rec: dict) -> Optional[str]:
        try:
            return self.audit_sink.log({
                "event": "place-span", "store": str(self.folder),
                "rule_id": rec["id"],
                "actor": rec.get("source", "ingest"),
                "extra": {"kind": "rule-item",
                          "modal": rec["norm"].get("modal")}})
        except Exception:                                      # noqa: BLE001
            return None

    # ── placement ─────────────────────────────────────────────────────────────
    def place_span(self, span_text: str, *, source_document: str = "",
                   start: Optional[int] = None, end: Optional[int] = None,
                   kind: str = "rule", facet: Optional[RuleFacet] = None,
                   source: str = "ingest", pinpoint: str = "",
                   document_hash: str = "",
                   document_version: Optional[int] = None) -> dict:
        """Place one span (= one norm) and persist it.

        ``pinpoint`` (e.g. ``Art. 17(3)``) is recorded on the span.
        ``document_hash`` / ``document_version`` pin the span to one version of
        its source document so an amendment can re-pin (or orphan) it
        explicitly — see :meth:`reanchor_document`. Idempotent on
        (source_document, pinpoint, span text)."""
        if facet is None:
            facets = extract_rules(span_text)
            facet = facets[0] if facets else RuleFacet(raw_sentence=span_text)
        # Rule-DNA completeness: every span-norm carries the juridical-primitive
        # layer regardless of which path created it (attach_incidents skips
        # already-enriched facets). The incident vocabulary is deontic's.
        from .hohfeld import attach_incidents
        attach_incidents([facet])
        rid = _rule_id(source_document + "|" + pinpoint, span_text)
        now = _now()
        existing = self.items.get(rid)
        urn = self.urn_minter(_urn_seed(rid)) if self.urn_minter else ""
        if existing is None:
            rec = SpanNorm(
                id=rid,
                span={"document": source_document, "start": start, "end": end,
                      "pinpoint": pinpoint, "text": span_text.strip(),
                      "document_hash": document_hash,
                      "document_version": document_version},
                norm=_norm_from_facet(facet), kind=kind,
                workspace=str(self.folder), user=self.user, source=source,
                canonical_urn=urn,
                first_seen=now, last_seen=now).to_dict()
            self.items[rid] = rec
            self._flush_workspace()
            self._log(rec)
            return dict(rec, status="created")
        existing["last_seen"] = now
        if urn and not existing.get("canonical_urn"):
            existing["canonical_urn"] = urn
        self._flush_workspace()
        return dict(existing, status="updated")

    def add(self, facet: RuleFacet, *, source_document: str = "inline",
            span_text: str = "", user: str = "") -> SpanNorm:
        """Convenience wrapper over :meth:`place_span` for a single extracted
        :class:`RuleFacet`. Returns the stored :class:`SpanNorm`."""
        text = span_text or facet.raw_sentence
        if user:
            self.user = user
        rec = self.place_span(text, source_document=source_document, facet=facet)
        rec.pop("status", None)
        return SpanNorm(**rec)

    def reanchor_document(self, source_document: str, new_text: str, *,
                          new_hash: str, new_version: int,
                          actor: str = "ingest") -> dict:
        """Re-pin this document's spans to a new version of its text.

        For every span of ``source_document``: if the span text still occurs in
        ``new_text``, the record is re-pinned (new offsets, new hash/version);
        if it does not, the record is marked ``orphaned`` — it is NEVER silently
        dropped, and an orphan is an ESCALATE for the decision surface (the
        clause may have been amended, moved, or deleted; which one is a human
        call). Returns ``{migrated, orphaned, untouched}`` with ids."""
        migrated: list[str] = []
        orphaned: list[str] = []
        now = _now()
        for rid, rec in self.items.items():
            span = rec.get("span") or {}
            if span.get("document") != source_document:
                continue
            if span.get("document_version") == new_version:
                continue
            text = span.get("text") or ""
            idx = new_text.find(text) if text else -1
            if idx >= 0:
                span.update({"start": idx, "end": idx + len(text),
                             "document_hash": new_hash,
                             "document_version": new_version})
                rec.pop("orphaned", None)
                rec["last_seen"] = now
                migrated.append(rid)
            else:
                rec["orphaned"] = {"at_version": new_version, "hash": new_hash,
                                   "marked": now}
                rec["last_seen"] = now
                orphaned.append(rid)
            self._log(rec)
        if migrated or orphaned:
            self._flush_workspace()
        untouched = [rid for rid, rec in self.items.items()
                     if (rec.get("span") or {}).get("document") == source_document
                     and rid not in migrated and rid not in orphaned]
        return {"document": source_document, "new_version": new_version,
                "migrated": migrated, "orphaned": orphaned,
                "untouched": untouched,
                "escalate": bool(orphaned)}

    def orphans(self, source_document: str = "") -> list[dict]:
        """Spans stranded by a document update — the decision-surface feed."""
        out = []
        for rec in self.items.values():
            if not rec.get("orphaned"):
                continue
            if source_document and (rec.get("span") or {}).get("document") != source_document:
                continue
            out.append(rec)
        return out

    def place_document(self, content: str, *, source_document: str = "",
                       kind: str = "rule", source: str = "ingest") -> dict:
        """Extract one norm per span from a document and place each.
        Returns a summary with the placed rule ids."""
        placed = []
        for f in extract_rules(content):
            span = f.raw_sentence or ""
            if not span.strip():
                continue
            idx = content.find(span)
            r = self.place_span(span, source_document=source_document,
                                start=idx if idx >= 0 else None,
                                end=(idx + len(span)) if idx >= 0 else None,
                                kind=kind, facet=f, source=source)
            placed.append({"id": r["id"], "status": r["status"]})
        return {"placed": placed, "count": len(placed),
                "created": sum(p["status"] == "created" for p in placed)}

    # ── queries ───────────────────────────────────────────────────────────────
    def get(self, rid: str) -> Optional[SpanNorm]:
        r = self.items.get(rid)
        return SpanNorm(**r) if r else None

    def all(self) -> list[SpanNorm]:
        return [SpanNorm(**r) for r in self.items.values()]

    def search(self, *, modal: Optional[str] = None) -> list[dict]:
        out = []
        for r in self.items.values():
            if modal and r["norm"].get("modal") != modal:
                continue
            out.append(r)
        return out

    def workspace_items(self) -> list[dict]:
        return list(self.items.values())


def place_into_registry(folder: str, content: str, *, user: str = "",
                        source_document: str = "", source: str = "ingest",
                        subdir: str = "rule-items",
                        urn_minter: Optional[UrnMinter] = None,
                        audit_sink: Optional[AuditSink] = None) -> dict:
    """Best-effort hook for an ingest pipeline: place every span-norm in a
    document, per workspace. Never raises into the caller — a broken run
    returns an ``error`` field instead."""
    try:
        reg = RuleRegistry(folder, user=user, subdir=subdir,
                           urn_minter=urn_minter, audit_sink=audit_sink)
        return reg.place_document(content, source_document=source_document,
                                  source=source)
    except Exception as exc:                                   # noqa: BLE001
        return {"placed": [], "error": f"{type(exc).__name__}: {exc}"}
