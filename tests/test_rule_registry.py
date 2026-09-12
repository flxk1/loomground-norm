# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""RuleRegistry — the span-placement core, exercised against fake ports.

Covers the placement behavior behind the urn_minter / audit_sink ports, with
NO legal-domain surface (no anchoring, no place_legal_text) and NO host
per-user mirror:

  * span placement with URN minting delegated to an injected port,
    idempotent on (document, pinpoint, text), audited through the sink;
  * honest abstention: no urn_minter -> empty canonical_urn;
  * a neutral, configurable store path (no "legal" in it);
  * a neutral audit-event shape using norm-plane terms;
  * document re-pinning: surviving spans migrate, vanished spans orphan
    (escalate), never silently dropped;
  * search by modal;
  * place_into_registry and its never-raises contract.
"""

from __future__ import annotations

import pytest

pytest.importorskip("loomground_solver")
pytest.importorskip("deontic")

import loomground_norm as norm
from loomground_norm.rule_registry import RuleRegistry, place_into_registry


# ── fakes satisfying the declared ports ─────────────────────────────────────────

def _urn_minter(content: str) -> str:
    return "urn:test:" + content


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list = []

    def log(self, event: dict):
        self.events.append(event)
        return "receipt-%d" % len(self.events)


def _facet(text, *, modal="obligation", subject="controller", action="notify"):
    return norm.RuleFacet(subject=subject, modal=modal, action=action,
                          raw_sentence=text, confidence=0.9)


# ── span placement ──────────────────────────────────────────────────────────────

def test_place_span_uses_urn_port_and_audits(tmp_path):
    sink = _RecordingSink()
    reg = RuleRegistry(tmp_path, urn_minter=_urn_minter, audit_sink=sink)
    r = reg.place_span("The controller shall notify the authority.",
                       source_document="doc1",
                       facet=_facet("The controller shall notify the authority."))
    assert r["status"] == "created"
    assert r["canonical_urn"].startswith("urn:test:rule-")   # _urn_seed used
    assert sink.events and sink.events[0]["extra"]["kind"] == "rule-item"

    # idempotent on (document, pinpoint, text): re-placing updates, not creates.
    again = reg.place_span("The controller shall notify the authority.",
                           source_document="doc1",
                           facet=_facet("The controller shall notify the authority."))
    assert again["status"] == "updated"
    assert again["id"] == r["id"]


def test_place_span_abstains_without_urn_minter(tmp_path):
    reg = RuleRegistry(tmp_path)              # no urn_minter
    r = reg.place_span("The controller shall notify the authority.",
                       source_document="doc1",
                       facet=_facet("The controller shall notify the authority."))
    assert r["canonical_urn"] == ""           # visible: no URN invented
    assert "anchors" not in r                  # legal-anchor surface gone


def test_place_persists_across_a_fresh_registry(tmp_path):
    reg = RuleRegistry(tmp_path, urn_minter=_urn_minter)
    r = reg.place_span("The processor shall encrypt the data.",
                       source_document="doc1",
                       facet=_facet("The processor shall encrypt the data.",
                                    subject="processor", action="encrypt"))
    reloaded = RuleRegistry(tmp_path, urn_minter=_urn_minter)
    assert reloaded.get(r["id"]) is not None
    assert reloaded.get(r["id"]).canonical_urn == r["canonical_urn"]


def test_place_document_places_each_operative_span(tmp_path):
    reg = RuleRegistry(tmp_path)
    content = ("The controller shall notify the authority. "
               "The processor must not disclose the data.")
    out = reg.place_document(content, source_document="doc-multi")
    assert out["count"] >= 2
    assert out["created"] == out["count"]
    modals = {r["norm"]["modal"] for r in reg.workspace_items()}
    assert {"obligation", "prohibition"} <= modals


# ── neutral store path + audit shape ─────────────────────────────────────────────

def test_store_path_is_neutral_and_configurable(tmp_path):
    reg = RuleRegistry(tmp_path)
    reg.place_span("The controller shall notify the authority.",
                   source_document="d", facet=_facet("x"))
    written = list(tmp_path.rglob("rule-items.jsonl"))
    assert written                                  # default neutral subdir used
    assert not any("legal" in str(p) for p in written)   # no legal-corpus path

    reg2 = RuleRegistry(tmp_path / "w2", subdir="norm-store")
    reg2.place_span("The processor shall encrypt the data.",
                    source_document="d",
                    facet=_facet("y", subject="processor", action="encrypt"))
    assert (tmp_path / "w2" / "norm-store" / "rule-items.jsonl").exists()


def test_audit_event_is_neutral(tmp_path):
    sink = _RecordingSink()
    reg = RuleRegistry(tmp_path, audit_sink=sink)
    reg.place_span("The controller shall notify the authority.",
                   source_document="d", facet=_facet("x"))
    ev = sink.events[0]
    assert "pair_id" not in ev and "channel" not in ev   # no host-only fields
    assert "anchors" not in ev.get("extra", {})          # legal surface gone
    assert ev["rule_id"].startswith("rule:")             # neutral norm-plane terms
    assert ev["event"] == "place-span"
    assert ev["extra"]["kind"] == "rule-item"


# ── re-pinning + orphans ─────────────────────────────────────────────────────────

def test_reanchor_document_migrates_and_orphans(tmp_path):
    reg = RuleRegistry(tmp_path)
    keep = "The controller shall notify the authority."
    gone = "The processor must not disclose the data."
    r_keep = reg.place_span(keep, source_document="doc1", document_version=1,
                            facet=_facet(keep))
    r_gone = reg.place_span(gone, source_document="doc1", document_version=1,
                            facet=_facet(gone, modal="prohibition",
                                         subject="processor", action="disclose"))

    new_text = "Preamble. " + keep + " Some amended tail."
    res = reg.reanchor_document("doc1", new_text, new_hash="h2", new_version=2)

    assert res["migrated"] == [r_keep["id"]]
    assert res["orphaned"] == [r_gone["id"]]
    assert res["escalate"] is True
    # migrated span re-pinned; orphaned span marked, never dropped.
    assert reg.get(r_keep["id"]).span["document_version"] == 2
    assert r_gone["id"] in {o["id"] for o in reg.orphans("doc1")}


# ── queries ─────────────────────────────────────────────────────────────────────

def test_search_by_modal(tmp_path):
    reg = RuleRegistry(tmp_path)
    reg.place_span("The controller shall notify the authority.",
                   source_document="d", facet=_facet("a"))
    reg.place_span("The processor must not disclose the data.",
                   source_document="d", pinpoint="cl.2",
                   facet=_facet("b", modal="prohibition"))

    assert len(reg.workspace_items()) == 2
    assert len(reg.search(modal="prohibition")) == 1
    assert len(reg.search(modal="obligation")) == 1
    assert reg.search(modal="permission") == []


# ── place_into_registry + never-raises ───────────────────────────────────────────

def test_place_into_registry_places_a_document(tmp_path):
    out = place_into_registry(
        tmp_path,
        "The controller shall notify the authority.",
        source_document="doc")
    assert "instrument" not in out          # no legal-text routing anymore
    assert out["count"] >= 1


def test_place_into_registry_never_raises(tmp_path, monkeypatch):
    import loomground_norm.rule_registry as rr

    def _boom(content):
        raise RuntimeError("extract blew up")

    monkeypatch.setattr(rr, "extract_rules", _boom)
    out = place_into_registry(tmp_path, "The controller shall notify.",
                              source_document="d")
    assert out["placed"] == []
    assert "error" in out and "RuntimeError" in out["error"]
