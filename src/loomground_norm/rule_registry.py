# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Rule registry — every span-norm as a typed, persisted, audited record.

The unit is the **span**: one contiguous passage of source text (a contract
clause, a statutory sentence, a Randnummer) carries exactly one norm.
:class:`SpanNorm` and :class:`Anchor` are the plane's typed record of that.

This module ports rvnd's ``server/src/workspaces/rule_registry.py`` *placement*
behavior — span placement, per-user cross-folder indexing, document
re-anchoring, orphan tracking, and the reverse/search queries — with every
host coupling replaced by an injected port. What stays a port:

  * **anchoring** (``anchor_resolver``) — placing a span onto the
    instruments/jurisdictions/regulators that govern it is legal-domain work
    (rvnd's ``legal_world.WorldMap`` + ``corpus.ingest.candidates_from_text``).
    The registry takes an injected ``anchor_resolver: Callable[[RuleFacet],
    list]``; without one, ``anchors`` stays empty — a visible, legitimate
    answer, never invented.
  * **URN minting** (``urn_minter``) — canonical URN minting is the identity
    spine's job (rvnd's ``urn.mint_canonical``), not this plane's. An injected
    ``urn_minter: Callable[[str], str]`` replaces the direct import; without
    one, ``SpanNorm.canonical_urn`` stays empty (visible, not invented).
  * **audit** (``audit_sink``) — the :class:`~loomground_norm.ports.AuditSink`
    pattern already used in :mod:`.obligation_runtime`; rvnd's signed mutation
    log is one implementation, :class:`~loomground_norm.ports.NullAuditSink`
    the standalone default.
  * **per-user mirror** (``user_root``) — rvnd mirrors every rule into
    ``~/.workspace/log/rule-registry.jsonl`` so a user can ask "every
    payment-term clause I hold across all my projects". That home-dir path is
    a host convention, NOT hardcoded here: inject ``user_root`` (the directory
    the ``rule-registry.jsonl`` mirror lives in); without it the per-user
    mirror is disabled and :meth:`user_items` returns ``[]`` (visible).
  * **legal-instrument segmentation** (``provision_splitter`` /
    ``host_anchor_resolver``) — cutting a *law's own text* into provisions and
    anchoring each to its host instrument is legal/governance work (rvnd's
    ``legal_norm_splitter`` + world map). :meth:`place_legal_text` takes those
    as injected callables; unlike the general-document path they have no
    default, so it abstains loudly when not wired.

Idempotent (keyed by source + pinpoint + span text), provenance-stamped, and
audited through the injected sink. Pure stdlib beyond the extractor.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .ports import AuditSink, NullAuditSink
from .rule_extractor import RuleFacet, extract_rules

__all__ = [
    "Anchor", "SpanNorm", "AnchorResolver", "UrnMinter",
    "ProvisionSplitter", "HostAnchorResolver", "RuleRegistry",
    "place_into_registry",
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
    text) and stable across reanchoring, which mutates the record in place.
    Ported from rvnd's ``_span_urn`` so an injected minter reproduces the same
    identity-spine address."""
    return "rule-" + rid.partition(":")[2]


@dataclass
class Anchor:
    """One placement of a span onto a governing entity — an instrument, a
    jurisdiction, a regulator. Populated by an injected ``anchor_resolver``;
    empty is a legitimate, visible answer (no anchoring performed)."""

    entity: str               # entity code in a legal/entity map
    kind: str                 # instrument | jurisdiction | regulator
    relation: str             # cites | governed_by | enforced_by
    basis: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SpanNorm:
    id: str
    span: dict                 # {document, start, end, pinpoint, text, ...}
    norm: dict                 # {modal, subject, action, condition, exception, language}
    anchors: list = field(default_factory=list)   # [Anchor-dict, ...]
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


#: ``facet -> anchors`` — legal-domain placement, injected. See module docstring.
AnchorResolver = Callable[[RuleFacet], list]

#: ``content -> urn`` — identity-spine minting, injected. See module docstring.
UrnMinter = Callable[[str], str]

#: ``instrument text -> provisions`` — legal/governance segmentation, injected.
#: Each provision exposes ``.text``/``["text"]`` and ``.pinpoint``/``["pinpoint"]``.
ProvisionSplitter = Callable[[str], list]

#: ``(instrument_code, pinpoint) -> anchors`` for a law's own provision —
#: legal-domain host-instrument anchoring, injected. See :meth:`RuleRegistry.place_legal_text`.
HostAnchorResolver = Callable[[str, str], list]


def _anchor_dicts(anchors: list) -> list:
    return [a.to_dict() if isinstance(a, Anchor) else a for a in anchors]


def _prov_field(prov: Any, name: str) -> str:
    if isinstance(prov, dict):
        return prov.get(name, "") or ""
    return getattr(prov, name, "") or ""


class RuleRegistry:
    """Per-workspace (and optionally per-user) store of :class:`SpanNorm`
    records, placed on the legal map through injected ports.

    Persistence is two-scoped, matching rvnd:

      * **per workspace** — ``<folder>/legal-corpus/rule-items.jsonl``, so the
        folder's own rules travel with the folder;
      * **per user** — ``<user_root>/rule-registry.jsonl`` (only when
        ``user_root`` is injected), tagged with the originating workspace, so a
        user can query across all their projects.
    """

    def __init__(self, folder: str | Path, *, user: str = "",
                 user_root: Optional[str | Path] = None,
                 anchor_resolver: Optional[AnchorResolver] = None,
                 urn_minter: Optional[UrnMinter] = None,
                 audit_sink: Optional[AuditSink] = None,
                 provision_splitter: Optional[ProvisionSplitter] = None,
                 host_anchor_resolver: Optional[HostAnchorResolver] = None):
        self.folder = Path(folder)
        self.user = user
        self.user_root = Path(user_root) if user_root else None
        self.anchor_resolver = anchor_resolver
        self.urn_minter = urn_minter
        self.audit_sink = audit_sink or NullAuditSink()
        self.provision_splitter = provision_splitter
        self.host_anchor_resolver = host_anchor_resolver
        self.items: dict[str, dict] = {}     # id -> record (workspace scope)
        self.load()

    # ── persistence ───────────────────────────────────────────────────────────
    def _workspace_path(self) -> Path:
        return self.folder / "legal-corpus" / "rule-items.jsonl"

    def _user_path(self) -> Optional[Path]:
        return (self.user_root / "rule-registry.jsonl") if self.user_root else None

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

    def _mirror_user(self, rec: dict) -> None:
        """Append/refresh the rule in the per-user store, tagged with its
        workspace. Keyed by (user, workspace, id) so the same rule from two
        workspaces coexists. Best-effort and a no-op when no ``user_root`` is
        injected — the home-dir mirror is a host convention, not this plane's."""
        up = self._user_path()
        if up is None:
            return
        try:
            up.parent.mkdir(parents=True, exist_ok=True)
            rows: dict[tuple, dict] = {}
            if up.exists():
                for line in up.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        r = json.loads(line)
                        rows[(r.get("user", ""), r.get("workspace", ""), r["id"])] = r
            rows[(rec.get("user", ""), rec.get("workspace", ""), rec["id"])] = rec
            up.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                    for r in rows.values()) + "\n", encoding="utf-8")
        except Exception:                                      # noqa: BLE001
            pass     # user mirror is best-effort

    def _log(self, rec: dict) -> Optional[str]:
        try:
            return self.audit_sink.log({
                "event": "ingest", "folder_path": str(self.folder),
                "pair_id": rec["id"], "channel": "document",
                "actor": rec.get("source", "ingest"),
                "extra": {"kind": "rule-item",
                          "anchors": [a["entity"] for a in rec.get("anchors", [])],
                          "modal": rec["norm"].get("modal")}})
        except Exception:                                      # noqa: BLE001
            return None

    # ── placement ─────────────────────────────────────────────────────────────
    def place_span(self, span_text: str, *, source_document: str = "",
                   start: Optional[int] = None, end: Optional[int] = None,
                   kind: str = "rule", facet: Optional[RuleFacet] = None,
                   source: str = "ingest", anchors: Optional[list] = None,
                   pinpoint: str = "", document_hash: str = "",
                   document_version: Optional[int] = None) -> dict:
        """Place one span (= one norm) onto the legal map and persist it.

        Anchoring runs through the injected ``anchor_resolver`` unless
        ``anchors`` (precomputed) are supplied — used when the host instrument
        is known (ingesting a law's own articles). ``pinpoint`` (e.g.
        ``Art. 17(3)``) is recorded on the span. ``document_hash`` /
        ``document_version`` pin the span to one version of its source document
        so an amendment can re-anchor (or orphan) it explicitly — see
        :meth:`reanchor_document`. Idempotent on (source_document, pinpoint,
        span text)."""
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
        if anchors is None:
            anchors = _anchor_dicts(
                self.anchor_resolver(facet) if self.anchor_resolver else [])
        else:
            anchors = _anchor_dicts(anchors)
        urn = self.urn_minter(_urn_seed(rid)) if self.urn_minter else ""
        if existing is None:
            rec = SpanNorm(
                id=rid,
                span={"document": source_document, "start": start, "end": end,
                      "pinpoint": pinpoint, "text": span_text.strip(),
                      "document_hash": document_hash,
                      "document_version": document_version},
                norm=_norm_from_facet(facet), anchors=anchors, kind=kind,
                workspace=str(self.folder), user=self.user, source=source,
                canonical_urn=urn,
                first_seen=now, last_seen=now).to_dict()
            self.items[rid] = rec
            self._flush_workspace()
            self._mirror_user(rec)
            self._log(rec)
            return dict(rec, status="created")
        existing["last_seen"] = now
        if anchors and not existing.get("anchors"):
            existing["anchors"] = anchors
        if urn and not existing.get("canonical_urn"):
            existing["canonical_urn"] = urn
        self._flush_workspace()
        self._mirror_user(existing)
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
        """Migrate this document's spans to a new version of its text.

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
        """Extract one norm per span from a general document and place each.
        Returns a summary with the placed rule ids and their anchors."""
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
            placed.append({"id": r["id"], "status": r["status"],
                           "anchors": [a["entity"] for a in r["anchors"]]})
        return {"placed": placed, "count": len(placed),
                "created": sum(p["status"] == "created" for p in placed)}

    def place_legal_text(self, content: str, instrument_code: str, *,
                         source_document: str = "", source: str = "ingest",
                         provision_splitter: Optional[ProvisionSplitter] = None,
                         host_anchor_resolver: Optional[HostAnchorResolver] = None
                         ) -> dict:
        """Ingest a law's own text: cut it into provisions, extract the norm(s)
        in each, and place every one as an individual span-norm anchored to the
        host instrument (via ``host_anchor_resolver``) plus any in-text
        cross-refs (via ``anchor_resolver``).

        Provision segmentation and host-instrument anchoring are legal/governance
        work with no default — inject ``provision_splitter`` and (optionally)
        ``host_anchor_resolver`` on the registry or per call. Without a splitter
        this abstains loudly rather than silently placing nothing. One law, many
        norms: extraction is ungated so every article's operative norm enters
        the map individually."""
        splitter = provision_splitter or self.provision_splitter
        host_res = host_anchor_resolver or self.host_anchor_resolver
        if splitter is None:
            raise NotImplementedError(
                "place_legal_text needs a provision_splitter port — cutting a "
                "law into provisions is legal/governance work; inject one on "
                "the registry or pass it per call.")
        placed: list[dict] = []
        for prov in splitter(content):
            ptext = _prov_field(prov, "text")
            pinpoint = _prov_field(prov, "pinpoint")
            for f in extract_rules(ptext):
                span = (f.raw_sentence or "").strip()
                if not span:
                    continue
                anchors: Optional[list] = None
                if host_res is not None:
                    anchors = _anchor_dicts(host_res(instrument_code, pinpoint))
                    if self.anchor_resolver:
                        for a in _anchor_dicts(self.anchor_resolver(f)):
                            if a.get("entity") != instrument_code:
                                anchors.append(a)
                r = self.place_span(span, source_document=source_document,
                                    kind="norm", facet=f, source=source,
                                    anchors=anchors, pinpoint=pinpoint)
                placed.append({"id": r["id"], "status": r["status"],
                               "pinpoint": pinpoint,
                               "modal": r["norm"].get("modal")})
        return {"instrument": instrument_code, "placed": placed,
                "count": len(placed),
                "created": sum(p["status"] == "created" for p in placed),
                "provisions": len({p["pinpoint"] for p in placed})}

    # ── queries ───────────────────────────────────────────────────────────────
    def get(self, rid: str) -> Optional[SpanNorm]:
        r = self.items.get(rid)
        return SpanNorm(**r) if r else None

    def all(self) -> list[SpanNorm]:
        return [SpanNorm(**r) for r in self.items.values()]

    def rules_at(self, entity_code: str) -> list[dict]:
        """Reverse index: every span-norm placed at a given legal entity."""
        return [r for r in self.items.values()
                if any(a["entity"] == entity_code for a in r.get("anchors", []))]

    def search(self, *, modal: Optional[str] = None,
               relation: Optional[str] = None) -> list[dict]:
        out = []
        for r in self.items.values():
            if modal and r["norm"].get("modal") != modal:
                continue
            if relation and not any(a["relation"] == relation
                                    for a in r.get("anchors", [])):
                continue
            out.append(r)
        return out

    def workspace_items(self) -> list[dict]:
        return list(self.items.values())

    def user_items(self, *, user: Optional[str] = None) -> list[dict]:
        """Every span-norm in the per-user store (across workspaces), optionally
        filtered to one user. Empty when no ``user_root`` is injected."""
        up = self._user_path()
        if up is None or not up.exists():
            return []
        rows = [json.loads(l) for l in up.read_text(encoding="utf-8").splitlines()
                if l.strip()]
        return [r for r in rows if user is None or r.get("user", "") == user]


def place_into_registry(folder: str, content: str, *, user: str = "",
                        source_document: str = "", source: str = "ingest",
                        user_root: Optional[str | Path] = None,
                        anchor_resolver: Optional[AnchorResolver] = None,
                        urn_minter: Optional[UrnMinter] = None,
                        audit_sink: Optional[AuditSink] = None,
                        provision_splitter: Optional[ProvisionSplitter] = None,
                        host_anchor_resolver: Optional[HostAnchorResolver] = None,
                        host_detector: Optional[Callable[[str], Optional[str]]] = None,
                        code_normaliser: Optional[Callable[[str], str]] = None
                        ) -> dict:
    """Best-effort hook for an ingest pipeline: place every span-norm in a
    document onto the legal map, per workspace (+ per user when ``user_root`` is
    given). Never raises into the caller.

    If a ``host_detector`` recognises the document AS a legal instrument (and a
    ``provision_splitter`` is available), route to article-aware extraction so
    each provision's norm enters the map individually; otherwise treat it as a
    third-party document (clauses that cite laws). Host detection
    (``infer_host_instrument``) and code normalisation (``_CODE_ALIASES``) are
    legal/corpus work, injected — no host import here."""
    try:
        reg = RuleRegistry(folder, user=user, user_root=user_root,
                           anchor_resolver=anchor_resolver, urn_minter=urn_minter,
                           audit_sink=audit_sink,
                           provision_splitter=provision_splitter,
                           host_anchor_resolver=host_anchor_resolver)
        host = host_detector(content) if host_detector else None
        if host and (provision_splitter is not None or reg.provision_splitter is not None):
            code = code_normaliser(host) if code_normaliser else host
            return reg.place_legal_text(content, code,
                                        source_document=source_document, source=source)
        return reg.place_document(content, source_document=source_document, source=source)
    except Exception as exc:                                   # noqa: BLE001
        return {"placed": [], "error": f"{type(exc).__name__}: {exc}"}
