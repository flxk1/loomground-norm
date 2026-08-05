# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""RuleRegistry — the ported placement behavior, exercised against fake ports.

Covers what was migrated from rvnd's
``server/src/workspaces/rule_registry.py`` behind the anchor_resolver /
urn_minter / audit_sink / user_root ports:

  * span placement with anchoring + URN minting delegated to injected ports,
    idempotent on (document, pinpoint, text), audited through the sink;
  * honest abstention: no anchor_resolver -> empty anchors, no urn_minter ->
    empty canonical_urn;
  * per-user cross-folder mirror (only when user_root is injected);
  * document re-anchoring: surviving spans migrate, vanished spans orphan
    (escalate), never silently dropped;
  * reverse index (rules_at) and search (modal / relation);
  * place_legal_text driven by injected provision-splitter + host-anchor ports,
    abstaining loudly when the splitter is absent;
  * place_into_registry routing (law vs document) and its never-raises contract.
"""

from __future__ import annotations

import pytest

pytest.importorskip("loomground_solver")
pytest.importorskip("deontic")

import loomground_norm as norm
from loomground_norm.rule_registry import RuleRegistry, Anchor, place_into_registry


# ── fakes satisfying the declared ports ─────────────────────────────────────────

def _anchor_resolver(facet):
    """Fake legal-domain anchoring: place every span on the GDPR (DE)."""
    return [Anchor("GDPR", "instrument", "cites", "test"),
            Anchor("DE", "jurisdiction", "governed_by", "owning order")]


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

def test_place_span_uses_anchor_and_urn_ports_and_audits(tmp_path):
    sink = _RecordingSink()
    reg = RuleRegistry(tmp_path, anchor_resolver=_anchor_resolver,
                       urn_minter=_urn_minter, audit_sink=sink)
    r = reg.place_span("The controller shall notify the authority.",
                       source_document="doc1",
                       facet=_facet("The controller shall notify the authority."))
    assert r["status"] == "created"
    assert [a["entity"] for a in r["anchors"]] == ["GDPR", "DE"]
    assert r["canonical_urn"].startswith("urn:test:rule-")   # _urn_seed used
    assert sink.events and sink.events[0]["extra"]["kind"] == "rule-item"

    # idempotent on (document, pinpoint, text): re-placing updates, not creates.
    again = reg.place_span("The controller shall notify the authority.",
                           source_document="doc1",
                           facet=_facet("The controller shall notify the authority."))
    assert again["status"] == "updated"
    assert again["id"] == r["id"]


def test_place_span_abstains_without_ports(tmp_path):
    reg = RuleRegistry(tmp_path)              # no anchor_resolver, no urn_minter
    r = reg.place_span("The controller shall notify the authority.",
                       source_document="doc1",
                       facet=_facet("The controller shall notify the authority."))
    assert r["anchors"] == []                 # visible: no anchoring performed
    assert r["canonical_urn"] == ""           # visible: no URN invented


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
    reg = RuleRegistry(tmp_path, anchor_resolver=_anchor_resolver)
    content = ("The controller shall notify the authority. "
               "The processor must not disclose the data.")
    out = reg.place_document(content, source_document="doc-multi")
    assert out["count"] >= 2
    assert out["created"] == out["count"]
    modals = {r["norm"]["modal"] for r in reg.workspace_items()}
    assert {"obligation", "prohibition"} <= modals


# ── re-anchoring + orphans ──────────────────────────────────────────────────────

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

def test_rules_at_and_search(tmp_path):
    reg = RuleRegistry(tmp_path, anchor_resolver=_anchor_resolver)
    reg.place_span("The controller shall notify the authority.",
                   source_document="d", facet=_facet("a"))
    reg.place_span("The processor must not disclose the data.",
                   source_document="d", pinpoint="cl.2",
                   facet=_facet("b", modal="prohibition"))

    assert len(reg.rules_at("GDPR")) == 2               # reverse index by anchor
    assert len(reg.rules_at("DE")) == 2
    assert len(reg.search(modal="prohibition")) == 1
    assert len(reg.search(relation="governed_by")) == 2
    assert reg.search(relation="enforced_by") == []     # no such anchor placed


# ── per-user mirror ─────────────────────────────────────────────────────────────

def test_user_mirror_aggregates_across_folders(tmp_path):
    user_root = tmp_path / "user-log"
    ws_a, ws_b = tmp_path / "a", tmp_path / "b"
    reg_a = RuleRegistry(ws_a, user="felix", user_root=user_root)
    reg_b = RuleRegistry(ws_b, user="felix", user_root=user_root)
    reg_a.place_span("The controller shall notify the authority.",
                     source_document="da", facet=_facet("a"))
    reg_b.place_span("The processor shall encrypt the data.",
                     source_document="db",
                     facet=_facet("b", subject="processor", action="encrypt"))

    # a fresh registry sees both workspaces' rules in the per-user store.
    all_mine = RuleRegistry(ws_a, user="felix", user_root=user_root).user_items()
    workspaces = {r["workspace"] for r in all_mine}
    assert len(all_mine) == 2
    assert workspaces == {str(ws_a), str(ws_b)}
    assert RuleRegistry(ws_a, user="felix", user_root=user_root).user_items(
        user="nobody") == []


def test_user_mirror_disabled_without_user_root(tmp_path):
    reg = RuleRegistry(tmp_path, user="felix")          # no user_root injected
    reg.place_span("The controller shall notify the authority.",
                   source_document="d", facet=_facet("a"))
    assert reg.user_items() == []                       # visible: no home-dir mirror


# ── legal-text placement (injected splitter + host anchoring) ────────────────────

def _splitter(content):
    return [{"text": "The provider shall register the system with the authority.",
             "pinpoint": "Art. 1"},
            {"text": "The operator must not delete the logs.",
             "pinpoint": "Art. 2"}]


def _host_anchors(code, pinpoint):
    return [Anchor(code, "instrument", "cites", pinpoint),
            Anchor("EU", "jurisdiction", "governed_by", "owning order")]


def test_place_legal_text_uses_injected_ports(tmp_path):
    reg = RuleRegistry(tmp_path, provision_splitter=_splitter,
                       host_anchor_resolver=_host_anchors)
    out = reg.place_legal_text("<the law's full text>", "AIACT",
                               source_document="ai-act")
    assert out["instrument"] == "AIACT"
    assert out["count"] >= 2
    assert out["provisions"] == 2
    # each placed span is anchored to its host instrument with the pinpoint basis.
    at_host = reg.rules_at("AIACT")
    assert at_host
    bases = {a["basis"] for r in at_host for a in r["anchors"]
             if a["entity"] == "AIACT"}
    assert {"Art. 1", "Art. 2"} <= bases


def test_place_legal_text_abstains_without_a_splitter(tmp_path):
    reg = RuleRegistry(tmp_path)
    with pytest.raises(NotImplementedError):
        reg.place_legal_text("<the law's full text>", "AIACT")


# ── place_into_registry routing + never-raises ──────────────────────────────────

def test_place_into_registry_routes_to_legal_text(tmp_path):
    out = place_into_registry(
        tmp_path, "<the law's full text>", source_document="ai-act",
        provision_splitter=_splitter, host_anchor_resolver=_host_anchors,
        host_detector=lambda c: "AIACT")
    assert out["instrument"] == "AIACT"
    assert out["count"] >= 2


def test_place_into_registry_routes_to_document(tmp_path):
    out = place_into_registry(
        tmp_path,
        "The controller shall notify the authority.",
        source_document="doc", anchor_resolver=_anchor_resolver)
    assert "instrument" not in out
    assert out["count"] >= 1


def test_place_into_registry_never_raises(tmp_path):
    def _boom(content):
        raise RuntimeError("splitter blew up")
    out = place_into_registry(
        tmp_path, "text", provision_splitter=_boom,
        host_detector=lambda c: "AIACT")
    assert out["placed"] == []
    assert "error" in out and "RuntimeError" in out["error"]
