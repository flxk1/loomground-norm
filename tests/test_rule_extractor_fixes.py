# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Targeted regression tests for the legal-frame-field fixes.

Each test exercises one named fix against a short public EU statute
sentence (GDPR Art. 33(1), NIS2 Art. 21(1)/23(1), AI Act Art. 73(1)-(2),
DSA Art. 13(1)) so a future regression has a sentence-level reproduction,
not just an aggregate metric.
"""

from __future__ import annotations

from loomground_norm.rule_extractor import extract_rules

GDPR_33_1 = (
    "In the case of a personal data breach, the controller shall without "
    "undue delay and, where feasible, not later than 72 hours after having "
    "become aware of it, notify the personal data breach to the "
    "supervisory authority competent in accordance with Article 55, "
    "unless the personal data breach is unlikely to result in a risk to "
    "the rights and freedoms of natural persons."
)

NIS2_23_1 = (
    "Member States shall ensure that essential and important entities "
    "notify, without undue delay, their CSIRT or, where applicable, their "
    "competent authority of any incident that has a significant impact on "
    "the provision of their services."
)

NIS2_21_1 = (
    "Member States shall ensure that essential and important entities "
    "take appropriate and proportionate technical, operational and "
    "organisational measures to manage the risks posed to the security of "
    "network and information systems."
)

AI_ACT_73_1 = (
    "Providers of high-risk AI systems shall report any serious incident "
    "to the market surveillance authorities of the Member States where "
    "that incident occurred."
)

AI_ACT_73_2 = (
    "The reporting referred to in paragraph 1 shall be done immediately "
    "after the provider has established a causal link between the AI "
    "system and the serious incident and, in any event, not later than 15 "
    "days after the provider becomes aware of the serious incident."
)

DSA_13_1 = (
    "Providers of intermediary services which do not have an "
    "establishment in the Union but which offer services in the Union "
    "shall designate, in writing, a legal or natural person as their "
    "legal representative in one of the Member States where the provider "
    "offers its services."
)


def _one(sentence: str):
    facets = extract_rules(sentence)
    assert facets, f"no rule extracted from: {sentence!r}"
    return facets[0]


# ── fix: deadline (single and multiple) ─────────────────────────────────────

def test_deadline_populated_from_not_later_than():
    f = _one(GDPR_33_1)
    assert "72 hours" in f.deadline
    assert "without undue delay" in f.deadline


def test_deadline_captures_all_timing_cues_not_just_the_first():
    f = _one(AI_ACT_73_2)
    assert "immediately" in f.deadline
    assert "15 days" in f.deadline
    # both halves present, not just whichever the regex saw first
    assert f.deadline.count(";") >= 1


# ── fix: counterparty ────────────────────────────────────────────────────────

def test_counterparty_populated_from_to_phrase():
    f = _one(GDPR_33_1)
    assert "supervisory authority" in f.counterparty


def test_counterparty_populated_from_direct_object_no_to():
    f = _one(NIS2_23_1)
    assert "csirt" in f.counterparty.lower()


# ── "Member States shall ensure that X …" keeps Member States as subject ───
#
# ensurer is reserved for a future bearer distinction and is always "".

def test_member_states_ensure_sentence_keeps_member_states_as_subject():
    f = _one(NIS2_21_1)
    assert f.subject == "member states"
    assert f.ensurer == ""
    assert "ensure that" in f.action.lower()


def test_ensurer_field_is_reserved_and_always_empty():
    f = _one(NIS2_23_1)
    assert f.subject == "member states"
    assert f.ensurer == ""


# ── fix: leading clause moved out of the subject into condition ────────────

def test_leading_in_the_case_of_clause_moved_to_condition():
    f = _one(GDPR_33_1)
    assert f.subject == "the controller"
    assert "personal data breach" in f.condition


# ── fix: hedge is not a condition ───────────────────────────────────────────

def test_where_applicable_hedge_is_not_captured_as_a_condition():
    f = _one(NIS2_23_1)
    assert f.condition == ""


# ── fix: adverbial between modal and verb no longer breaks the action ──────

def test_adverbial_between_modal_and_verb_does_not_truncate_the_action():
    f = _one(GDPR_33_1)
    assert f.action.startswith("notify")
    assert "without undue delay" not in f.action
    assert "where feasible" not in f.action


# ── fix: normalised action_verb ─────────────────────────────────────────────

def test_action_verb_is_normalised():
    f = _one(DSA_13_1)
    assert f.action_verb == "designate"
    f2 = _one(GDPR_33_1)
    assert f2.action_verb == "notify"


# ── fix: coordinated subject is not truncated at "and" ──────────────────────

def test_coordinated_subject_is_not_truncated_at_the_conjunction():
    f = _one("Essential and important entities shall take appropriate and "
             "proportionate technical, operational and organisational "
             "measures to manage the risks posed to the security of "
             "network and information systems.")
    assert f.subject == "essential and important entities"


# ── fix: locative "where" is not mistaken for a trigger condition ──────────

def test_locative_where_clause_is_not_a_condition():
    f = _one(DSA_13_1)
    assert f.condition == ""


# ── fix: passive addressee handling ─────────────────────────────────────────
#
# A "by …" match only tells _is_agentless_passive the agent is NAMED (so
# the construction is not an abstention case) — it says nothing about
# whether that "by" belongs to the main clause or an embedded relative
# clause ("Member States shall designate a national authority, which shall
# be supervised by the Commission" is active; "by the Commission" is the
# relative clause's agent, not this rule's). The subject is never rewritten
# to resolve this, in either voice, and there is no cross-sentence
# carry-forward either.

def test_agentless_passive_with_no_prior_context_flags_unresolved():
    f = _one("The report shall be made available to the Commission within "
             "30 days.")
    assert f.subject == "the report"
    assert f.addressee_resolved is False
    assert f.deadline == "within 30 days"


def test_agentless_passive_is_never_resolved_from_a_preceding_sentence():
    """No cross-sentence guessing: an agentless passive stays unresolved
    even when an EARLIER sentence in the same call names a clear bearer."""
    f = _one("The controller shall notify the breach. The register shall "
             "be maintained.")
    assert f.subject == "the controller"
    content = ("The controller shall notify the breach. "
               "The register shall be maintained.")
    facets = extract_rules(content)
    assert len(facets) == 2
    assert facets[0].subject == "the controller"
    assert facets[1].subject == "the register"
    assert facets[1].addressee_resolved is False


def test_passive_with_a_by_agent_keeps_the_grammatical_subject():
    """A named agent resolves the addressee flag — it does NOT become the
    subject. Byte-identical to a37b0f1: subject="the register"."""
    f = _one("The register shall be maintained by the Commission.")
    assert f.subject == "the register"
    assert f.addressee_resolved is True


def test_passive_with_a_pronoun_agent_also_keeps_the_grammatical_subject():
    f = _one("The decision shall be reviewed by it within 30 days.")
    assert f.subject == "the decision"
    assert f.addressee_resolved is True


def test_by_agent_in_an_embedded_relative_clause_does_not_hijack_subject():
    """An ACTIVE sentence ("Member States shall designate …") whose
    embedded relative clause happens to contain a "by <agent>" phrase must
    not have its subject rewritten to that agent."""
    f = _one("Member States shall designate a national authority, which "
             "shall be supervised by the Commission.")
    assert f.subject == "member states"
    assert f.addressee_resolved is True
