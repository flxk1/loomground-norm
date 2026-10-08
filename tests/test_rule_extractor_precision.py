# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Precision regression tests for the rule extractor.

Pattern fall-through (a sentence whose first-tried pattern fails
validation must still try the next pattern, in English and German);
counterparty extraction must never read a thing, a pronoun, or an
unrelated clause's recipient as the party a duty is owed to; action_verb
must read strictly from the verb position; deadlines recognise spelled-
out numbers; a pronoun left behind by the fronted-clause split is
rejected; the Member-State ensurer field stays reserved.
"""

from __future__ import annotations

from loomground_norm.rule_extractor import extract_rules


def _one(sentence: str):
    facets = extract_rules(sentence)
    assert facets, f"no rule extracted from: {sentence!r}"
    return facets[0]


# ── pattern fall-through ─────────────────────────────────────────────────────

def test_german_wer_clause_still_fires_when_a_later_pattern_is_needed():
    # The Wer-clause bespoke pattern's own consequence group ("er hat zu
    # zahlen") must still be read after the OTHER bespoke DE pattern is
    # tried and rejected (its subject head "wer" is on the pronoun
    # stoplist) — the sentence must not come back empty.
    rs = extract_rules(
        "Wer gegen die Regel verstößt, wird bestraft; er hat zu zahlen.")
    assert rs, "German Wer-clause sentence produced no rule"


def test_article_requires_pattern_falls_through_to_the_bare_shall_pattern():
    # The first bespoke EN pattern ("Article N requires/obliges/… X to
    # VERB") can fail its own subject/modal check on some phrasings; the
    # sentence still has a second, independent "shall" clause the bare
    # pattern should catch.
    rs = extract_rules(
        "Article 5 requires them to notify the authority, and the "
        "provider shall notify the board.")
    assert rs, "no rule extracted"
    assert any("provider" in r.subject for r in rs)


# ── counterparty: never a thing, a pronoun, or an unrelated clause's ───────
# ── recipient ────────────────────────────────────────────────────────────

def test_counterparty_not_captured_for_infinitive_purpose_clause():
    f = _one("The provider shall report the incident pursuant to Article 73 "
              "to ensure compliance.")
    assert f.counterparty == ""


def test_counterparty_not_captured_for_a_thing_not_a_party():
    f = _one("The provider shall notify the authority of any changes made "
              "to the system.")
    # the real recipient (authority) comes from the direct-object form;
    # "the system" must never be read as the recipient.
    assert "system" not in f.counterparty.lower()
    assert "authority" in f.counterparty.lower()


def test_counterparty_not_a_locative_destination():
    f = _one("The deployer shall inform workers that they will be subject "
              "to the use of the system.")
    assert "use" not in f.counterparty.lower()


def test_counterparty_not_captured_for_a_geographic_destination():
    f = _one("The provider shall transmit the data to third countries only "
              "where adequate safeguards exist.")
    assert f.counterparty == ""


def test_counterparty_not_a_bare_pronoun_it():
    f = _one("The authority may request the provider to submit "
              "documentation to it within 10 days.")
    assert f.counterparty.lower() != "it"


def test_counterparty_not_a_bare_pronoun_whom():
    f = _one("The provider shall designate a representative to whom "
              "requests may be addressed.")
    assert f.counterparty.lower() != "whom"


def test_counterparty_direct_object_of_notify_with_of_clause():
    f = _one("The provider shall notify the authority of any changes.")
    assert "authority" in f.counterparty.lower()


def test_counterparty_to_phrase_with_party_noun_still_fires():
    f = _one("The controller shall communicate the breach to the data "
              "subject without undue delay.")
    assert "subject" in f.counterparty.lower()


# ── action_verb reads strictly from the verb position ───────────────────────

def test_action_verb_not_read_from_a_later_unrelated_clause():
    f = _one("The reporting referred to in paragraph 1 shall be done "
              "immediately after the provider has established a causal "
              "link between the AI system and the serious incident.")
    assert f.action_verb != "establish"


def test_action_verb_recognises_verify_and_respond():
    f1 = _one("The importer shall verify the conformity of the system "
               "before placing it on the market.")
    assert f1.action_verb == "verify"
    f2 = _one("The controller shall respond to requests within one month "
               "of receipt.")
    assert f2.action_verb == "respond"


# ── spelled-out numbers in deadlines ─────────────────────────────────────────

def test_deadline_recognises_spelled_out_numbers():
    f = _one("The controller shall respond to requests within one month "
              "of receipt.")
    assert "one month" in f.deadline
    f2 = _one("The provider shall submit the report within three days of "
               "the request.")
    assert "three days" in f2.deadline


# ── pronoun stoplist applied after the fronted-clause split ────────────────

def test_pronoun_subject_is_rejected_even_after_the_leading_split():
    rs = extract_rules(
        "Where the processor engages another processor, it shall inform "
        "the controller.")
    for r in rs:
        assert r.subject != "it"


# ── Member-State ensurer stays reserved ─────────────────────────────────────
#
# A bearer swap for "Member States shall ensure that X <verb> …" was tried
# and dropped: it stopped at noun homographs of operative duty verbs
# ("report", "request", "order", "fines", "documents") and at participles,
# producing a wrong bearer on a meaningful share of a real-text sample. The
# subject stays "member states" and ensurer stays reserved (always "").

def test_member_states_shall_ensure_keeps_member_states_as_subject():
    f = _one("Each Member State shall ensure that essential and important "
              "entities take appropriate measures.")
    assert f.subject == "each member state"
    assert f.ensurer == ""


def test_ensure_clause_with_report_homograph_keeps_member_states():
    f = _one("Member States shall ensure that the report of the authority "
              "is made public without undue delay.")
    assert f.subject == "member states"
    assert f.ensurer == ""
    assert f.addressee_resolved is True


def test_ensure_clause_with_request_homograph_keeps_member_states():
    f = _one("Member States shall ensure that the request for access to "
              "data is processed within a reasonable time.")
    assert f.subject == "member states"
    assert f.ensurer == ""
    assert f.addressee_resolved is True


def test_ensure_clause_with_order_homograph_keeps_member_states():
    f = _one("Member States shall ensure that the order to remove content "
              "is complied with immediately.")
    assert f.subject == "member states"
    assert f.ensurer == ""
    assert f.addressee_resolved is True


def test_ensure_clause_with_documents_participle_keeps_member_states():
    f = _one("Member States shall ensure that the documents submitted by "
              "the provider are kept for at least five years.")
    assert f.subject == "member states"
    assert f.ensurer == ""
    assert f.addressee_resolved is False


def test_ensure_clause_with_fines_homograph_keeps_member_states():
    f = _one("Member States shall ensure that the maximum amount of fines "
              "shall be 6 % of the total worldwide annual turnover.")
    assert f.subject == "member states"
    assert f.ensurer == ""
    assert f.addressee_resolved is True
