# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Rule extractor — Phase B2 (continued), EU-wide.

Once a fragment is classified as ``normative``, the rule extractor pulls
out its **operative structure** so downstream ND dispatchers can do real
work, not just see a type label.

Five operative slots per rule:

- **subject**: the regulated entity ("provider", "controller", "Tenant",
  "Der Verantwortliche", "le responsable", "il titolare").
- **modal**: deontic operator ("shall", "must not", "may", "muss",
  "dürfen nicht", "doit", "non può", "debe").
- **action**: what the subject is required / permitted / prohibited to do.
- **condition**: when the rule applies ("where", "if", "sofern", "si",
  "se", "indien", "jeżeli").
- **exception**: scoping carve-outs ("notwithstanding", "without prejudice
  to", "unbeschadet", "sans préjudice de", "fatto salvo").

The extractor is sentence-segmenting and returns one :class:`RuleFacet`
per detected rule. Whether a fragment is worth extracting from at all is a
separate, injectable decision (see ``fingerprint_gate`` on
:func:`extract_rules`) — a host with its own normative-fingerprint classifier
a host's routing layer wires it in; this module decides WHAT the
rules are, never WHETHER to look.

EU-wide coverage
----------------
Detection and extraction run over a per-language registry (``_PROFILES``)
covering the 24 official EU languages. English and German keep bespoke,
hand-tuned patterns (the indirect-operative-verb form, the German
``Wer``-clause). Every other language is driven by a generic
subject + modal + action builder parameterised by that language's deontic
verb table, determiners, and condition/exception connectives.

Confidence tiers for the deontic tables:
  TIER A (high)        en de fr it es nl pt sv da
  TIER B (medium)      pl cs sk ro sl hr el bg fi hu et
  TIER C (best-effort) lt lv ga mt   — recommend native-legal validation

A wrong or missing entry in a non-core table lowers *recall* (a candidate
rule is missed), it never fabricates a legal claim: extractor output is a
candidate, gated downstream by the confidence floor and the oversight dial.
This is still Phase-1 (regex); a Phase-2 local-LLM extractor is the planned
upgrade for embedded references and multi-sentence rule structures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

#: Injected pre-filter deciding whether content is worth extracting from —
#: see :func:`extract_rules`. The plane ships no implementation; a host
#: A host's normative fingerprint or another classifier wires
#: its own in.
FingerprintGate = Callable[[str], bool]


@dataclass
class RuleFacet:
    """One operative rule extracted from normative content."""

    subject: str = ""
    """The regulated subject. Lowercase canonical form when possible."""

    modal: str = ""
    """The deontic class: ``"obligation"`` / ``"prohibition"`` /
    ``"permission"`` / ``"right"``. Use :attr:`modal_phrase` for the
    surface form."""

    modal_phrase: str = ""
    """The matched surface phrase ("shall", "muss", "doit", "non può")."""

    action: str = ""
    """Verb phrase the rule binds the subject to."""

    condition: str = ""
    """The applicability condition, if any."""

    exception: str = ""
    """A scoping carve-out, if any."""

    consequence: str = ""
    """The fallback stated in an "otherwise …", "failing which …", or "or
    else …" branch: what happens if the rule's requirement is not met.
    Captured verbatim from the sentence; "" when no such branch is present."""

    raw_sentence: str = ""
    """The full original sentence the rule was extracted from."""

    language: str = "en"
    """ISO 639-1 code of the detected language (one of the 24 EU official
    languages, or ``"en"`` as the fallback)."""

    confidence: float = 0.0
    """Confidence the extraction is well-formed. 1.0 = all five slots
    populated; lower = some slots inferred or absent."""

    condition_struct: "dict[str, Any] | None" = None
    """Optional structured reading of :attr:`condition` (a
    :class:`workspaces.predicate.Predicate` dict). Populated only by
    :func:`workspaces.predicate.attach_predicates` when the deterministic parse is
    confident (>= 0.85, NT-12); ``None`` means *no struct, verbatim text only*
    — never a guessed structure. The verbatim ``condition`` always remains
    the authoritative legal text."""

    incident: str = ""
    """Hohfeldian position the rule creates, from `loomground-deontic`'s
    eight-incident vocabulary (the rule facet always names the ADDRESSEE's
    side): ``duty`` | ``privilege`` | ``power`` | ``immunity`` | ``disability``;
    "" = not classified. Populated by
    :func:`loomground_norm.hohfeld.attach_incidents` — a termination or
    consent right is a POWER (its exercise changes legal positions), not a
    mere permission."""

    counterparty: str = ""
    """The correlative role (obligee of a duty / party exposed to a power)
    when the rule names it; "" = not named (abstention)."""

    condition_kind: str = ""
    """``suspensive`` (condition triggers the effect) | ``resolutive``
    (condition extinguishes it) | "" (unclassified). Only unambiguous cues
    are classified — this bit flips an obligation's life cycle."""

    addressee_resolved: bool = True
    """False when the rule is an *agentless passive* construction ("X shall be
    established", no "by …" agent): the grammatical :attr:`subject` is the
    PATIENT, not the legal addressee. We do not guess the addressee (that would
    be judging, not transcribing) — we flag it so downstream routes the
    addressee question to the residual instead of asserting the patient. The
    subject is never rewritten to resolve this, in either voice."""

    deadline: str = ""
    """All timing cues the sentence attaches to the action, joined with
    "``; ``" when more than one fires in the same sentence: a relative
    period ("within 72 hours", "not later than 15 days after …", "within
    one month"), or an urgency cue ("without undue delay", "immediately",
    "as soon as possible"). "" = no timing cue found. Verbatim text, never
    computed into a date — that is :mod:`loomground_solver`'s job once a
    :class:`RelativeDeadline` is wanted."""

    action_verb: str = ""
    """A normalised lemma for the operative verb ("notify", "report",
    "designate", "assess", "impose", "cooperate", …) drawn from
    :data:`_ACTION_VERB_LEMMAS`. "" when the action's verb is not in the
    table — the verbatim :attr:`action` remains authoritative; this is a
    classification aid, not a replacement."""

    ensurer: str = ""
    """Reserved for a future "Member State(s) shall ensure that X …"
    bearer distinction (the Member State clause arranges a duty, X is who
    it actually binds). Not yet populated — always ""."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Per-language profile registry
# ---------------------------------------------------------------------------

def _phrase_to_regex(phrase: str) -> str:
    """Literal phrase → regex token with flexible internal whitespace."""
    return re.escape(phrase).replace(r"\ ", r"\s+")


# Accented Latin vowels and the like are NOT language-distinctive (ä is German
# *and* Finnish *and* Swedish; í is Spanish *and* Czech). Using them as detection
# signals causes a language to be chosen whose modal table can't parse the
# sentence. We detect on distinctive deontic words/phrases instead, and ignore
# any single-character ambiguous-diacritic marker.
_AMBIG_DIACRITICS = set("áàâãäéèêëíìîïóòôöõúùûüýÿñçåæøœœ")


def _marker_regex(markers: tuple[str, ...]) -> "re.Pattern[str] | None":
    """Compile a marker list for detection.

    - single-char markers that are ambiguous diacritics → dropped;
    - other single-char markers (ß, §, script chars) → raw substring;
    - multi-char / multi-word markers → wrapped in non-word boundaries so
      ``ska`` does not match inside ``skal`` and ``deve`` does not match
      inside ``devessero``.
    """
    parts: list[str] = []
    for m in markers:
        had_space = (m != m.strip())   # space-padded ⇒ whole-word intent
        t = m.strip()
        if not t:
            continue
        if len(t) == 1 and not had_space:
            # Bare single char = an in-word signal (ß, §). Ambiguous accented
            # vowels are dropped — they are not language-distinctive.
            if t.lower() in _AMBIG_DIACRITICS:
                continue
            parts.append(re.escape(t))
        else:
            # Whole word / phrase: bound by non-word edges so "o" matches only
            # standalone "o" and "ska" never matches inside "skal".
            parts.append(r"(?<!\w)%s(?!\w)" % _phrase_to_regex(t))
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)


@dataclass
class LanguageProfile:
    """Everything the extractor needs to read one language."""

    code: str
    modal_classes: dict[str, str]          # surface form -> deontic class
    determiners: tuple[str, ...] = ()       # leading articles (le, la, der…)
    condition_markers: tuple[str, ...] = ()
    exception_markers: tuple[str, ...] = ()
    detect_strong: tuple[str, ...] = ()     # one hit (weight 3) ⇒ likely this lang
    detect_weak: tuple[str, ...] = ()       # weight 1 each
    pronoun_stoplist: frozenset[str] = frozenset()
    negators: tuple[str, ...] = ()          # trailing negators (mag … NIET)
    bespoke_patterns: list[re.Pattern[str]] = field(default_factory=list)

    # Cached compiled artefacts (built lazily in __post_init__).
    rule_patterns: list[re.Pattern[str]] = field(default_factory=list)
    condition_pattern: re.Pattern[str] | None = None
    exception_pattern: re.Pattern[str] | None = None
    strong_re: re.Pattern[str] | None = None
    weak_re: re.Pattern[str] | None = None
    negator_re: re.Pattern[str] | None = None

    def __post_init__(self) -> None:
        if self.bespoke_patterns:
            self.rule_patterns = list(self.bespoke_patterns)
        else:
            self.rule_patterns = [self._build_generic_pattern()]
        self.strong_re = _marker_regex(self.detect_strong)
        self.weak_re = _marker_regex(self.detect_weak)
        if self.negators:
            alt = "|".join(_phrase_to_regex(n) for n in self.negators)
            self.negator_re = re.compile(r"(?<!\w)(?:%s)(?!\w)" % alt, re.IGNORECASE)
        if self.condition_markers:
            alt = "|".join(_phrase_to_regex(m) for m in self.condition_markers)
            self.condition_pattern = re.compile(
                r"\b(?:%s)\s+(?P<cond>[^.;,]+)" % alt, re.IGNORECASE)
        if self.exception_markers:
            alt = "|".join(_phrase_to_regex(m) for m in self.exception_markers)
            self.exception_pattern = re.compile(
                r"\b(?:%s)\s+(?P<exc>[^.;,]+)" % alt, re.IGNORECASE)

    def _build_generic_pattern(self) -> re.Pattern[str]:
        # Modal alternation, longest-first (alternation is left-to-right eager).
        modals = sorted(self.modal_classes, key=len, reverse=True)
        modal_alt = "|".join(_phrase_to_regex(m) for m in modals)
        det = ""
        if self.determiners:
            det_alt = "|".join(_phrase_to_regex(d) for d in self.determiners)
            det = r"(?:(?:%s)\s+)?" % det_alt
        # \w matches Unicode letters under Python 3 str patterns. The modal
        # is followed by a non-word lookahead so "ska" cannot match inside
        # "skal" (Danish) — the modal must be a whole token.
        return re.compile(
            r"(?P<subject>\b%s\w[\w\-]*(?:\s+\w[\w\-]*){0,4}?)"
            r"\s+(?P<modal>%s)(?!\w)\s+"
            r"(?P<action>\w[^.;]+?)(?:[.;]|\Z)" % (det, modal_alt),
            re.IGNORECASE,
        )


# --- English + German keep their bespoke, hand-tuned patterns --------------

_MODAL_CLASS_EN: dict[str, str] = {
    "shall not": "prohibition", "must not": "prohibition", "may not": "prohibition",
    "is prohibited": "prohibition", "are prohibited": "prohibition",
    # Passive-voice prohibition — common EU drafting ("X shall be prohibited").
    # Longest-first matching means these win over the bare "shall" below.
    "shall be prohibited": "prohibition", "shall be banned": "prohibition",
    "is banned": "prohibition", "are banned": "prohibition",
    "be prohibited": "prohibition",
    "shall": "obligation", "must": "obligation",
    "is required": "obligation", "are required": "obligation",
    "has the right": "right", "have the right": "right",
    "shall have the right": "right", "is entitled": "right", "are entitled": "right",
    "is empowered": "right", "are empowered": "right",
    "may": "permission",
}

#: English leading-negation. An obligation/permission modal whose ACTION opens
#: with a negator ("must never deploy", "may not disclose" that fell through as a
#: bare modal) binds the negation to the deontic operator: the rule is a
#: prohibition, not an obligation to do the negated thing. English only — German
#: "muss nicht" is an *exemption* (need-not), not a ban, and must never flip here.
#: Only a LEADING negator flips: a later "not" ("must ensure data is not shared")
#: states an obligation to prevent, and is left untouched.
_LEADING_NEG_EN = re.compile(r"^(?:never|not|no)\b\s*(?:ever\b\s*)?", re.IGNORECASE)


#: Indicative-passive obligations. A policy states many duties in the present
#: passive with no deontic modal ("logs are retained for two years", "personal
#: data is deleted within 30 days", "an incident is reported to the DPO"). These
#: are norms, not description — but only when the participle is a governance act
#: AND a deontic complement is present (a retention/notice deadline, or a named
#: recipient). The participle whitelist and the required complement each on their
#: own exclude descriptive passives ("is designed to be safe", "is trained on
#: public data"). The subject is the patient, so the addressee stays unresolved
#: (agentless passive), the same reading "shall be retained" already gets.
_GOV_PARTICIPLE = (
    r"retained|kept|stored|deleted|erased|destroyed|removed|redacted"
    r"|reported|escalated|notified|disclosed|shared|transferred|transmitted"
    r"|encrypted|anonymi[sz]ed|pseudonymi[sz]ed|logged|recorded|reviewed|audited"
    r"|obtained|renewed|reassessed|approved")
#: A deontic complement: a deadline/period, or a named recipient. Requiring one
#: is the precision guard that keeps the indicative pattern off bare description.
_DEADLINE = (
    r"(?:\b\d+\s+(?:day|week|month|year|hour|minute)s?\b"
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
    r"(?:day|week|month|year|hour|minute)s?\b"
    r"|\bwithin\b|\bno\s+later\s+than\b|\bat\s+all\s+times\b)")
_RECIPIENT = r"\bto\s+(?:the|a|an)\s+\w"
_IND_COMPLEMENT = r"(?:%s|%s)" % (_DEADLINE, _RECIPIENT)

#: Compound-rule fallback: the "otherwise …" branch states what happens if the
#: requirement is not met. The action group stops at ";", so this branch is
#: dropped unless captured here — leaving downstream free to invent a fallback.
_OTHERWISE_RE = re.compile(
    r"(?:;|,)?\s*(?:otherwise|failing\s+which|or\s+else|in\s+default\s+of\s+which)"
    r"\b[,:]?\s*(?P<conseq>[^.;]+)", re.IGNORECASE)


_MODAL_CLASS_DE: dict[str, str] = {
    "muss": "obligation", "müssen": "obligation",
    "ist verpflichtet": "obligation", "sind verpflichtet": "obligation",
    "hat": "obligation", "haben": "obligation",
    "dürfen nicht": "prohibition", "darf nicht": "prohibition",
    "dürfen keine": "prohibition", "darf keine": "prohibition",
    "ist berechtigt": "right", "hat das recht": "right",
    # Bare permission modal. Separated negation ("darf … nicht offenlegen") is
    # rewritten to prohibition downstream by the discontinuous-negator rule.
    "darf": "permission", "dürfen": "permission",
}

# Token for a subject word: an ordinary lowercase word, a Capitalised word, an
# all-caps acronym (AI, GPAI), each optionally hyphenated ("high-risk"). Widened
# from the original ``[A-Z][a-z]+|[a-z]+`` which dropped hyphens and acronyms,
# producing truncated bearers like "risk ai systems" for "high-risk AI systems".
_SUBJ_WORD = r"(?:[A-Z]+[a-z]*|[a-z]+)(?:-[A-Za-z]+)?"

_BESPOKE_EN = [
    re.compile(
        r"(?P<source>\bArt(?:icle|\.)\s*\d+(?:\(\d+\))?(?:\([a-z]\))?)"
        r"\s+(?:[\w\-]+\s+){0,3}?"
        r"(?P<verb>requires|obliges|prohibits|sets\s+out|establishes|imposes|mandates|stipulates|lays\s+down)"
        r"\s+(?P<subject>(?:that\s+)?[\w\-]+(?:\s+[\w\-]+){0,3})"
        r"\s+(?P<modal>to|from)\s+"
        r"(?P<action>[a-z][^.;]+?)(?:[.;]|\Z)",
        re.IGNORECASE),
    # Passive prohibition: "The following AI practices shall be prohibited",
    # "The use of an AI system that exploits … shall be prohibited". The
    # grammatical subject IS the prohibited practice, so it lands as the bearer
    # with a "be prohibited" action — the operator (F) is what this pattern
    # guarantees.
    #
    # The subject is a SINGLE flat lazy char-class capped at 120 chars, NOT a
    # ``(?:\s+WORD){0,8}?`` group. A lazy quantifier wrapping an alternation
    # that itself contains ``*`` (which ``_SUBJ_WORD`` does) backtracks
    # catastrophically on a long sentence that never reaches the modal — it
    # hung the extractor on the full Art. 5(1) sentence. One char-class +
    # one mandatory modal literal is linear. The 120-char cap means a very long
    # relative-clause subject simply doesn't match here (it falls through to the
    # bare-"shall" pattern) rather than freezing — a precision/​robustness
    # trade that Layer-2 (local LLM) resolves properly.
    re.compile(
        r"(?P<subject>(?:[Tt]he\s+)?[A-Za-z][^.;:]{0,280}?)"
        r"\s+(?P<modal>shall\s+be\s+prohibited|shall\s+be\s+banned"
        r"|is\s+prohibited|are\s+prohibited|is\s+banned|are\s+banned)"
        # Capture the practice enumerated after the colon ("… prohibited: the
        # placing on the market, …") as the action, so the formula is not empty.
        r"\s*:?\s*(?P<action>[^.;]*)(?:[.;]|\Z)",
        re.IGNORECASE),
    re.compile(
        # Subject is a flat lazy char-class (linear, like the passive pattern)
        # capped at 120 chars, so a long noun phrase ("The provider of a
        # high-risk AI system") is captured whole up to the modal, rather than
        # truncated to a fixed 4-word window.
        r"(?P<subject>(?:[Tt]he\s+)?[A-Za-z][^.;:]{0,120}?)"
        r"\s+"
        r"(?P<modal>shall\s+have\s+the\s+right|has?\s+the\s+right"
        r"|is\s+(?:required|prohibited|entitled|empowered)"
        r"|are\s+(?:required|prohibited|entitled|empowered)"
        r"|shall\s+not|must\s+not|may\s+not"
        r"|shall|must|may)"
        r"(?:,\s*[^,.;]{1,60},)?"
        r"\s+"
        r"(?P<action>[a-z][^.;]+?)(?:[.;]|\Z)",
        re.IGNORECASE),
    # "X requires <approval/consent/review/…>" — an approval obligation. Gated to
    # governance objects so it never fires on "requires 4 GB of memory". Tried
    # before the indicative pattern so a compound "X requires …; otherwise …"
    # matches the primary clause, leaving the branch for the consequence capture.
    re.compile(
        r"(?P<subject>(?:[Tt]he\s+|[Aa]\s+|[Aa]n\s+|[Ee]ach\s+|[Ee]very\s+|[Aa]ny\s+)?"
        r"[A-Za-z][\w\- ]{0,60}?)"
        r"\s+(?P<modal>requires?|shall\s+require)\s+"
        r"(?P<action>(?:prior\s+|documented\s+|written\s+|express\s+)?"
        r"(?:approval|consent|authori[sz]ation|sign-?off|review|verification"
        r"|a\s+quorum|two\s+signatures|dual\s+control)[^.;]*?)(?:[.;]|\Z)",
        re.IGNORECASE),
    # Indicative-passive obligation (present passive, no deontic modal), gated on
    # a governance participle plus a deontic complement (see _GOV_PARTICIPLE).
    # Tried after the modal patterns so a deontic sentence still prefers them.
    re.compile(
        r"(?P<subject>(?:[Tt]he\s+|[Aa]ny\s+|[Aa]ll\s+|[Ee]ach\s+|[Ee]very\s+)?"
        r"[A-Za-z][^.;:]{0,80}?)"
        r"\s+(?P<modal>is|are|was|were)\s+"
        r"(?=[^.;]*?" + _IND_COMPLEMENT + r")"
        r"(?P<action>(?:" + _GOV_PARTICIPLE + r")\b[^.;]+?)(?:[.;]|\Z)",
        re.IGNORECASE),
]

_BESPOKE_DE = [
    re.compile(
        r"(?P<subject>\b(?:[Dd]er|[Dd]ie|[Dd]as)?\s*[A-ZÄÖÜ][\wäöüß]+"
        r"(?:\s+[A-ZÄÖÜa-zäöüß][\wäöüß\-]*){0,4})"
        r"\s+"
        r"(?P<modal>muss|müssen|dürfen(?:\s+(?:nicht|keine?))?"
        r"|darf(?:\s+(?:nicht|keine?))?|ist\s+verpflichtet|sind\s+verpflichtet"
        r"|hat|haben)"
        r"\s*,?\s+"
        r"(?P<action>[\wäöüß][^.;]+?)(?:[.;]|\Z)",
        re.IGNORECASE),
    re.compile(
        r"(?P<subject>\bWer)\s+"
        r"(?P<action>[^,]+),\s+"
        r"(?P<modal>kann|wird|ist)\s+"
        r"(?P<consequence>[^.;]+)(?:[.;]|\Z)",
        re.IGNORECASE),
]


# Irish is verb-initial (VSO): the modal/verb leads and the subject follows
# ("Ní mór do X …" = "X must …"). The subject-first generic builder can't fit
# it, so Irish gets bespoke modal-first patterns (like German's Wer-clause).
_BESPOKE_GA = [
    re.compile(
        r"(?P<modal>ní\s+mór)\s+d(?:o|on|o'n|en)\s+"
        r"(?P<subject>\w[\w\-]*(?:\s+\w[\w\-]*){0,1})\s+"
        r"(?P<action>\w[^.;]+?)(?:[.;]|\Z)", re.IGNORECASE),
    re.compile(
        r"(?P<modal>ní\s+cheadaítear|toirmiscfear|féadfaidh|féadann|déanfaidh)\s+"
        r"(?:do\s+|don\s+)?"
        r"(?P<subject>\w[\w\-]*(?:\s+\w[\w\-]*){0,1})\s+"
        r"(?P<action>\w[^.;]+?)(?:[.;]|\Z)", re.IGNORECASE),
]
_BESPOKE_BY_LANG: dict[str, list[re.Pattern[str]]] = {"ga": _BESPOKE_GA}


def _modal_table(obligation=(), prohibition=(), permission=(), right=()) -> dict[str, str]:
    t: dict[str, str] = {}
    for k in obligation:    t[k] = "obligation"
    for k in prohibition:   t[k] = "prohibition"
    for k in permission:    t[k] = "permission"
    for k in right:         t[k] = "right"
    return t


# Generic (non-bespoke) language specs. Deontic verbs grouped by class.
# TIER A high · TIER B medium · TIER C best-effort (native validation advised).
_GENERIC_SPECS: dict[str, dict[str, Any]] = {
    # --- TIER A -----------------------------------------------------------
    "fr": dict(  # French
        modal=_modal_table(
            obligation=("doit", "doivent", "est tenu de", "sont tenus de", "est tenu d'"),
            prohibition=("ne doit pas", "ne peut pas", "ne peuvent pas", "il est interdit de"),
            permission=("peut", "peuvent"),
            right=("a le droit", "ont le droit")),
        determiners=("le", "la", "les", "l'", "un", "une"),
        condition=("si", "lorsque", "lorsqu'", "dans le cas où", "sauf si"),
        exception=("sans préjudice de", "sous réserve de", "nonobstant"),
        strong=("doit", "doivent", "est tenu", "ne doit pas", "il est interdit",
                "sans préjudice", "lorsque", "é", "è", "ê", "à", "ç"),
        weak=(" le ", " la ", " les ", " peut ", " si ")),
    "it": dict(  # Italian
        modal=_modal_table(
            obligation=("deve", "devono", "è tenuto a", "sono tenuti a", "è obbligato a"),
            prohibition=("non deve", "non può", "non possono", "è vietato"),
            permission=("può", "possono"),
            right=("ha diritto", "hanno diritto")),
        determiners=("il", "lo", "la", "i", "gli", "le", "un", "una"),
        condition=("se", "qualora", "quando", "salvo che"),
        exception=("fatto salvo", "salvo", "ferma restando", "fatti salvi"),
        strong=("deve", "devono", "è tenuto", "non può", "è vietato",
                "qualora", "fatto salvo", "ò", "à", "ù"),
        weak=(" il ", " la ", " può ", " se ", " gli ")),
    "es": dict(  # Spanish
        modal=_modal_table(
            obligation=("debe", "deben", "deberá", "deberán", "está obligado a"),
            prohibition=("no debe", "no podrá", "no podrán", "está prohibido"),
            permission=("puede", "pueden", "podrá"),
            right=("tiene derecho", "tienen derecho")),
        determiners=("el", "la", "los", "las", "un", "una"),
        condition=("si", "cuando", "siempre que", "salvo que"),
        exception=("sin perjuicio de", "salvo", "no obstante"),
        strong=("debe", "deben", "deberá", "está obligado", "está prohibido",
                "sin perjuicio", "ñ", "á", "í", "ó", "ú"),
        weak=(" el ", " la ", " los ", " puede ", " cuando ")),
    "nl": dict(  # Dutch
        modal=_modal_table(
            obligation=("moet", "moeten", "is verplicht", "zijn verplicht", "dient", "dienen"),
            prohibition=("mag niet", "mogen niet", "is verboden"),
            permission=("mag", "mogen", "kan", "kunnen"),
            right=("heeft het recht", "hebben het recht")),
        determiners=("de", "het", "een"),
        condition=("indien", "wanneer", "als", "tenzij"),
        exception=("onverminderd", "behoudens"),
        strong=("moet", "moeten", "is verplicht", "mag niet", "is verboden",
                "onverminderd", "indien", "behoudens"),
        weak=(" de ", " het ", " mag ", " dient "),
        neg=("niet", "geen")),
    "pt": dict(  # Portuguese
        modal=_modal_table(
            obligation=("deve", "devem", "está obrigado a", "fica obrigado a"),
            prohibition=("não pode", "não deve", "é proibido"),
            permission=("pode", "podem"),
            right=("tem direito", "têm direito")),
        determiners=("o", "a", "os", "as", "um", "uma"),
        condition=("se", "quando", "caso", "salvo se"),
        exception=("sem prejuízo de", "salvo", "não obstante"),
        strong=("deve", "devem", "está obrigado", "é proibido", "sem prejuízo",
                "ã", "õ", "ç", "á", "ê"),
        weak=(" o ", " os ", " as ", " pode ", " caso ")),
    "sv": dict(  # Swedish
        modal=_modal_table(
            obligation=("ska", "skall", "är skyldig att"),
            prohibition=("får inte", "ska inte"),
            permission=("får", "kan"),
            right=("har rätt", "har rätt att")),
        condition=("om", "när", "såvida inte"),
        exception=("utan hinder av", "med förbehåll för"),
        strong=("ska", "skall", "får inte", "är skyldig", "utan hinder",
                "å", "ä", "ö"),
        weak=(" om ", " när ", " får ")),
    "da": dict(  # Danish
        modal=_modal_table(
            obligation=("skal", "er forpligtet til"),
            prohibition=("må ikke", "kan ikke"),
            permission=("kan", "må"),
            right=("har ret til",)),
        condition=("hvis", "når", "medmindre"),
        exception=("uanset", "med forbehold for"),
        strong=("skal", "må ikke", "er forpligtet", "medmindre", "uanset",
                "å", "æ", "ø"),
        weak=(" hvis ", " når ", " kan ")),
    # --- TIER B -----------------------------------------------------------
    "pl": dict(  # Polish
        modal=_modal_table(
            obligation=("musi", "jest zobowiązany", "ma obowiązek", "są zobowiązani"),
            prohibition=("nie może", "zakazuje się", "nie wolno"),
            permission=("może", "mogą"),
            right=("ma prawo", "mają prawo")),
        condition=("jeżeli", "jeśli", "gdy", "chyba że"),
        exception=("bez uszczerbku dla", "z zastrzeżeniem"),
        strong=("musi", "jest zobowiązany", "nie może", "zakazuje się",
                "jeżeli", "z zastrzeżeniem", "ż", "ł", "ą", "ę", "ś", "ć"),
        weak=(" może ", " gdy ", " ma ")),
    "cs": dict(  # Czech
        modal=_modal_table(
            obligation=("musí", "je povinen", "jsou povinni"),
            prohibition=("nesmí", "je zakázáno"),
            permission=("může", "mohou", "smí"),
            right=("má právo", "mají právo")),
        condition=("pokud", "jestliže", "jestli"),
        exception=("aniž je dotčeno", "s výhradou"),
        strong=("musí", "je povinen", "nesmí", "je zakázáno", "jestliže",
                "ř", "č", "š", "ě", "ů"),
        weak=(" může ", " pokud ", " smí ")),
    "sk": dict(  # Slovak
        modal=_modal_table(
            obligation=("musí", "je povinný", "sú povinní"),
            prohibition=("nesmie", "je zakázané"),
            permission=("môže", "môžu", "smie"),
            right=("má právo", "majú právo")),
        condition=("ak", "pokiaľ", "ibaže"),
        exception=("bez toho aby", "s výhradou"),
        strong=("musí", "je povinný", "nesmie", "je zakázané", "pokiaľ",
                "ô", "ľ", "ť", "ž", "č"),
        weak=(" môže ", " ak ", " smie ")),
    "ro": dict(  # Romanian
        modal=_modal_table(
            obligation=("trebuie", "este obligat să", "are obligația"),
            prohibition=("nu trebuie", "este interzis", "nu poate"),
            permission=("poate", "pot"),
            right=("are dreptul", "au dreptul")),
        condition=("dacă", "în cazul în care", "cu excepția"),
        exception=("fără a aduce atingere", "sub rezerva"),
        strong=("trebuie", "este obligat", "este interzis", "are dreptul",
                "dacă", "fără a aduce atingere", "ă", "â", "ț", "ș"),
        weak=(" poate ", " pot ", " are ")),
    "sl": dict(  # Slovenian
        modal=_modal_table(
            obligation=("mora", "morajo", "je dolžan"),
            prohibition=("ne sme", "prepovedano je"),
            permission=("lahko", "sme"),
            right=("ima pravico", "imajo pravico")),
        condition=("če", "kadar", "razen če"),
        exception=("brez poseganja v", "ob upoštevanju"),
        strong=("mora", "je dolžan", "ne sme", "prepovedano", "razen če",
                "č", "š", "ž"),
        weak=(" lahko ", " če ", " sme ")),
    "hr": dict(  # Croatian
        modal=_modal_table(
            obligation=("mora", "moraju", "dužan je"),
            prohibition=("ne smije", "zabranjeno je"),
            permission=("može", "mogu", "smije"),
            right=("ima pravo", "imaju pravo")),
        condition=("ako", "kada", "osim ako"),
        exception=("ne dovodeći u pitanje", "podložno"),
        strong=("mora", "dužan je", "ne smije", "zabranjeno", "osim ako",
                "č", "ć", "š", "ž", "đ"),
        weak=(" može ", " ako ", " smije ")),
    "el": dict(  # Greek
        modal=_modal_table(
            obligation=("πρέπει", "υποχρεούται", "οφείλει"),
            prohibition=("δεν επιτρέπεται", "απαγορεύεται", "δεν πρέπει"),
            permission=("μπορεί", "δύναται"),
            right=("έχει δικαίωμα", "έχουν δικαίωμα")),
        condition=("εάν", "όταν", "εκτός εάν"),
        exception=("με την επιφύλαξη", "υπό την επιφύλαξη"),
        strong=("πρέπει", "υποχρεούται", "απαγορεύεται", "έχει δικαίωμα",
                "εάν", "με την επιφύλαξη"),
        weak=("μπορεί", "όταν", "δύναται")),
    "bg": dict(  # Bulgarian
        modal=_modal_table(
            obligation=("трябва", "длъжен е", "е длъжен"),
            prohibition=("не може", "забранява се", "не трябва"),
            permission=("може", "могат"),
            right=("има право", "имат право")),
        condition=("ако", "когато", "освен ако"),
        exception=("без да се засяга", "при спазване на"),
        strong=("трябва", "длъжен", "забранява се", "има право",
                "освен ако", "без да се засяга"),
        weak=("може", "когато", "ако")),
    "fi": dict(  # Finnish
        modal=_modal_table(
            obligation=("on velvollinen", "täytyy", "on velvoitettu"),
            prohibition=("ei saa", "on kielletty"),
            permission=("voi", "saa"),
            right=("on oikeus",)),
        condition=("jos", "kun", "ellei"),
        exception=("rajoittamatta", "jollei"),
        strong=("on velvollinen", "ei saa", "on kielletty", "on oikeus",
                "rajoittamatta", "ellei"),
        weak=(" jos ", " kun ", " voi ")),
    "hu": dict(  # Hungarian
        modal=_modal_table(
            obligation=("köteles", "kell"),
            prohibition=("tilos", "nem szabad", "nem lehet"),
            permission=("jogosult", "lehet"),
            right=("joga van", "jogosult")),
        condition=("ha", "amennyiben"),
        exception=("kivéve", "ennek sérelme nélkül"),
        strong=("köteles", "tilos", "jogosult", "amennyiben",
                "sérelme nélkül", "ő", "ű", "á", "é"),
        weak=(" ha ", " kell ", " lehet ")),
    "et": dict(  # Estonian
        modal=_modal_table(
            obligation=("peab", "on kohustatud"),
            prohibition=("ei tohi", "on keelatud"),
            permission=("võib",),
            right=("on õigus",)),
        condition=("kui", "juhul kui"),
        exception=("ilma et see piiraks", "piiramata"),
        strong=("peab", "on kohustatud", "ei tohi", "on keelatud", "on õigus",
                "õ", "ä", "ö", "ü"),
        weak=(" kui ", " võib ")),
    # --- TIER C (best-effort; native-legal validation advised) ------------
    "lt": dict(  # Lithuanian
        modal=_modal_table(
            obligation=("privalo", "turi"),
            prohibition=("negali", "draudžiama"),
            permission=("gali",),
            right=("turi teisę",)),
        condition=("jeigu", "jei", "kai"),
        exception=("nepažeidžiant",),
        strong=("privalo", "negali", "draudžiama", "turi teisę",
                "jeigu", "nepažeidžiant", "ž", "č", "š", "ū", "ė"),
        weak=(" gali ", " jei ", " turi ")),
    "lv": dict(  # Latvian
        modal=_modal_table(
            obligation=("ir pienākums", "nodrošina"),
            prohibition=("nedrīkst", "ir aizliegts"),
            permission=("var", "drīkst"),
            right=("ir tiesības",)),
        condition=("ja", "ja vien"),
        exception=("neskarot",),
        strong=("ir pienākums", "nedrīkst", "ir aizliegts", "ir tiesības",
                "neskarot", "ā", "ē", "ī", "ū", "ņ", "ļ"),
        weak=(" var ", " ja ", " drīkst ")),
    "ga": dict(  # Irish
        modal=_modal_table(
            obligation=("ní mór", "déanfaidh"),
            prohibition=("ní cheadaítear", "toirmiscfear"),
            permission=("féadfaidh", "féadann"),
            right=("tá ceart", "tá sé de cheart")),
        condition=("má", "i gcás"),
        exception=("gan dochar do",),
        strong=("ní mór", "déanfaidh", "ní cheadaítear", "féadfaidh",
                "gan dochar do", "á", "é", "í", "ó", "ú"),
        weak=(" má ", " i gcás ")),
    "mt": dict(  # Maltese
        modal=_modal_table(
            obligation=("għandu", "huwa obbligat"),
            prohibition=("ma jistax", "huwa pprojbit"),
            permission=("jista'", "jistgħu"),
            right=("għandu dritt",)),
        condition=("jekk", "meta"),
        exception=("mingħajr preġudizzju għal",),
        strong=("għandu", "huwa obbligat", "ma jistax", "huwa pprojbit",
                "mingħajr preġudizzju", "ġ", "ħ", "ż", "'"),
        weak=(" jekk ", " meta ")),
}


# Per-language pronoun stoplists — a rule's subject head matching one of
# these indicates casual prose, not a regulated entity. MUST be per-language:
# "il" is a French pronoun (he) but the Italian definite article (the), so a
# shared list would wrongly drop every Italian "Il <subject> …" rule.
_PRONOUNS_BY_LANG: dict[str, frozenset[str]] = {
    "en": frozenset({"i", "we", "you", "he", "she", "it", "they", "us", "them"}),
    "de": frozenset({"ich", "wir", "du", "er", "sie", "es", "ihr"}),
    "fr": frozenset({"je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "on", "lui"}),
    "it": frozenset({"io", "tu", "egli", "ella", "esso", "essi", "noi", "voi", "lui", "lei", "loro"}),
    "es": frozenset({"yo", "tú", "él", "ella", "ellos", "ellas", "nosotros", "vosotros"}),
    "nl": frozenset({"ik", "jij", "hij", "zij", "wij", "jullie", "ze"}),
    "pt": frozenset({"eu", "tu", "ele", "ela", "eles", "elas", "nós", "vós"}),
    "sv": frozenset({"jag", "du", "han", "hon", "vi", "ni", "de"}),
    "da": frozenset({"jeg", "du", "han", "hun", "vi", "de"}),
}
_EMPTY_PRONOUNS: frozenset[str] = frozenset()


def _build_registry() -> dict[str, LanguageProfile]:
    reg: dict[str, LanguageProfile] = {}
    reg["en"] = LanguageProfile(
        code="en", modal_classes=_MODAL_CLASS_EN,
        condition_markers=("where", "if", "provided that",
                           "in the case of", "in the case where"),
        exception_markers=("notwithstanding", "except as", "except where",
                           "except when", "except that", "unless",
                           "save where", "save that", "except to the extent",
                           "without prejudice to", "subject to"),
        detect_strong=(), detect_weak=(),
        pronoun_stoplist=_PRONOUNS_BY_LANG["en"], bespoke_patterns=_BESPOKE_EN)
    reg["de"] = LanguageProfile(
        code="de", modal_classes=_MODAL_CLASS_DE,
        condition_markers=("sofern", "soweit", "wenn", "falls"),
        exception_markers=("unbeschadet", "vorbehaltlich"),
        negators=("nicht", "kein", "keine", "keinen"),
        detect_strong=(" der verantwortliche ", " die verantwortlichen ",
                       " der schuldner ", " der gläubiger ", " der anbieter ",
                       " der auftragsverarbeiter ", " der lizenznehmer ",
                       " mitarbeiter ", " arbeitgeber ", " arbeitnehmer ",
                       " unbeschadet ", " sofern ", " soweit ", " gemäß ",
                       " müssen ", " dürfen ", " keine ", " keinen ",
                       " ist verpflichtet", " sind verpflichtet",
                       "§", "ä", "ö", "ü", "ß"),
        detect_weak=(" muss ", " hat ", " haben ", " wer "),
        pronoun_stoplist=_PRONOUNS_BY_LANG["de"], bespoke_patterns=_BESPOKE_DE)
    for code, spec in _GENERIC_SPECS.items():
        reg[code] = LanguageProfile(
            code=code,
            modal_classes=spec["modal"],
            determiners=tuple(spec.get("determiners", ())),
            condition_markers=tuple(spec.get("condition", ())),
            exception_markers=tuple(spec.get("exception", ())),
            detect_strong=tuple(spec.get("strong", ())),
            detect_weak=tuple(spec.get("weak", ())),
            negators=tuple(spec.get("neg", ())),
            pronoun_stoplist=_PRONOUNS_BY_LANG.get(code, _EMPTY_PRONOUNS),
            bespoke_patterns=_BESPOKE_BY_LANG.get(code, []),
        )
    return reg


_PROFILES: dict[str, LanguageProfile] = _build_registry()

# Back-compat alias (older code/tests referenced this name): the union view.
_PRONOUN_STOPLIST = frozenset().union(*_PRONOUNS_BY_LANG.values())

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜͰ-ϿЀ-ӿ])")

# Structural boundaries the sentence split misses: enumerated sub-paragraphs
# "(1) … (2) …" and "§ 2 …" section heads begin with "(" or "§", not a
# capital, so consecutive numbered duties (common in German contracts) would
# otherwise merge into one blob and only the first/none would match. Break on
# a newline that starts an enumerator or section marker, and on blank lines.
_STRUCT_SPLIT = re.compile(
    r"\n\s*(?=\(\s*\d+\s*\)|\(\s*[a-z]\s*\)|§\s*\d+|Art\.\s*\d+|Abs\.\s*\d+)"
    r"|\n\s*\n",
    re.I)


def _segment(content: str) -> list[str]:
    """Structural pre-split, then sentence split within each block — so an
    enumerated clause list yields one segment per duty, not one mega-blob."""
    out: list[str] = []
    for block in _STRUCT_SPLIT.split(content.strip()):
        block = (block or "").strip()
        if not block:
            continue
        out.extend(_SENTENCE_SPLIT.split(block))
    return out


# Unambiguous English deontic phrasing. English has no entry in the marker
# registry (it is the zero-baseline fallback), so a sentence containing strong
# English legal phrasing could be out-scored by incidental short-marker hits in
# another language's table — e.g. "the placing … the putting" scoring Maltese.
# When any of these fire, the sentence is English and detection short-circuits,
# so the bespoke EN patterns (incl. passive prohibition) run instead of a
# generic foreign profile that mis-parses it.
_EN_STRONG_RE = re.compile(
    r"(?<!\w)(?:"
    r"shall\s+be\s+prohibited|shall\s+be\s+banned|shall\s+not|shall\s+have\s+the\s+right"
    r"|shall|must\s+not|must|may\s+not"
    r"|is\s+prohibited|are\s+prohibited|is\s+required|are\s+required"
    r"|the\s+following|without\s+prejudice\s+to|the\s+controller|the\s+processor"
    r"|the\s+provider|the\s+deployer"
    r")(?!\w)",
    re.IGNORECASE,
)


def _detect_language(sentence: str) -> str:
    """Registry-driven detection across the 24 EU languages.

    English is the zero-baseline fallback. A non-English language is chosen
    only when its weighted marker score ≥ 2 (one strong hit, or two weak),
    which preserves the original EN/DE thresholds exactly. Unambiguous English
    deontic phrasing (:data:`_EN_STRONG_RE`) short-circuits to English first, so
    incidental short-marker noise in a foreign table cannot hijack an English
    legal sentence.
    """
    s = " " + sentence.lower() + " "
    if _EN_STRONG_RE.search(s):
        return "en"
    best_code, best_score = "en", 0
    for code, prof in _PROFILES.items():
        if code == "en":
            continue
        score = 0
        if prof.strong_re is not None:
            score += 3 * len(prof.strong_re.findall(s))
        if prof.weak_re is not None:
            score += 1 * len(prof.weak_re.findall(s))
        if score > best_score:
            best_score, best_code = score, code
    return best_code if best_score >= 2 else "en"


def _classify_modal(phrase: str, language: str) -> str:
    """Map a surface modal phrase to its deontic class, in the given language."""
    prof = _PROFILES.get(language) or _PROFILES["en"]
    p = phrase.lower().strip()
    for k in sorted(prof.modal_classes, key=len, reverse=True):
        if k in p:
            return prof.modal_classes[k]
    return "obligation"  # safe default when surface form not catalogued


def supported_languages() -> list[str]:
    """ISO 639-1 codes the extractor can read (the 24 EU official languages)."""
    return sorted(_PROFILES)


# Agentless-passive detection. Conservative and language-aware for the major
# drafting languages; defaults to "active" (resolved) when unsure, so it never
# over-flags. The signal: a passive auxiliary + participle in the modal/action,
# and NO explicit agent ("by …" / "par …" / "durch …" / "da …" / "por …").
_PASSIVE_AUX = {
    # "be/been retained", and the indicative "is/are/was/were <gov-participle>"
    # the indicative-obligation pattern reads — both are agentless unless a "by"
    # agent follows. "is required"/"is entitled" stay active: those participles
    # are periphrastic modals (subject is the addressee), not in _GOV_PARTICIPLE.
    "en": re.compile(r"\bbe(?:en)?\s+(?:\w+(?:ed|en|t|wn|de)|done|made)\b"
                     r"|\b(?:is|are|was|were)\s+(?:" + _GOV_PARTICIPLE + r")\b", re.I),
    "de": re.compile(r"\bwird\s+\w+(?:t|en)\b|\bist\s+zu\s+\w+en\b|\bwerden\s+\w+(?:t|en)\b", re.I),
    "fr": re.compile(r"\b(?:est|sont|être)\s+\w+(?:é|ée|és|ées)\b", re.I),
    "es": re.compile(r"\b(?:ser|es|son)\s+\w+(?:ado|ada|ados|adas|ido|ida)\b", re.I),
    "it": re.compile(r"\b(?:è|sono|essere|viene|vengono)\s+\w+(?:ato|ata|ati|ate|uto|ito)\b", re.I),
}
_AGENT_MARKER = {
    "en": re.compile(r"\bby\s+\w", re.I), "de": re.compile(r"\bdurch\s+\w|\bvon\s+\w", re.I),
    "fr": re.compile(r"\bpar\s+\w", re.I), "es": re.compile(r"\bpor\s+\w", re.I),
    "it": re.compile(r"\b(?:da|dal|dalla|dai)\s+\w", re.I),
}


def _is_agentless_passive(modal_phrase: str, action: str, lang: str) -> bool:
    """True when the construction is passive with no named agent.

    Then the grammatical subject is the patient, not the legal addressee.
    """
    aux = _PASSIVE_AUX.get(lang)
    if aux is None:
        return False
    hay = f"{modal_phrase} {action}"
    m = aux.search(hay)
    if not m:
        return False
    # Look for the agent marker ONLY in the window right after the passive verb
    # (the agent of THIS passive), not anywhere later — a trailing subordinate
    # clause ("…designed so it can be overseen by natural persons") names a
    # different verb's agent and must not count as resolving the main one.
    agent = _AGENT_MARKER.get(lang)
    if agent is not None:
        window = hay[m.end():m.end() + 30]
        if agent.search(window):
            return False   # "established by the provider" → agent named, resolved
    return True


#: Agent-NP promotion ("X shall be done by Y" -> subject Y) was tried and
#: dropped: the "by …" check above only tells us a passive's agent is
#: NAMED (so the construction is not agentless); it does not tell us the
#: match sits inside the MAIN clause rather than an embedded relative
#: clause ("Member States shall designate a national authority, which
#: shall be supervised by the Commission" has an agent, but it is the
#: relative clause's agent, not this rule's). Promoting it rewrote active
#: sentences' subjects too. :func:`_is_agentless_passive` stays the only
#: addressee signal — exactly :mod:`a37b0f1`'s behaviour: the grammatical
#: subject is kept either way, only the ``addressee_resolved`` flag moves.


# ---------------------------------------------------------------------------
# English post-processing: deadline, counterparty, action verb, the
# "Member States shall ensure that X …" bearer swap, the leading-clause and
# locative/hedge condition cleanups.
#
# These read genuine EU statute drafting conventions (deadline adverbials
# between modal and verb, "ensure that" delegation, "in the case of …"
# fronted triggers) and are deliberately gated to English: the generic and
# German pipelines are untouched, so their existing tests keep their exact
# behaviour.
# ---------------------------------------------------------------------------

#: Normalised lemma per surface verb form. "" (not in this table) means the
#: verbatim :attr:`RuleFacet.action` stays the only record — never guessed.
_ACTION_VERB_LEMMAS: dict[str, str] = {
    "notify": "notify", "notifies": "notify", "notified": "notify", "notifying": "notify",
    "report": "report", "reports": "report", "reported": "report", "reporting": "report",
    "inform": "inform", "informs": "inform", "informed": "inform", "informing": "inform",
    "communicate": "inform", "communicates": "inform", "communicated": "inform",
    "submit": "submit", "submits": "submit", "submitted": "submit", "submitting": "submit",
    "transmit": "submit", "transmits": "submit", "transmitted": "submit",
    "forward": "submit", "forwards": "submit", "forwarded": "submit",
    "designate": "designate", "designates": "designate", "designated": "designate",
    "appoint": "designate", "appoints": "designate", "appointed": "designate",
    "ensure": "ensure", "ensures": "ensure", "ensured": "ensure", "ensuring": "ensure",
    "assess": "assess", "assesses": "assess", "assessed": "assess", "assessing": "assess",
    "evaluate": "assess", "evaluates": "assess", "evaluated": "assess",
    "identify": "assess", "identifies": "assess", "identified": "assess",
    "adopt": "adopt", "adopts": "adopt", "adopted": "adopt",
    "establish": "establish", "establishes": "establish", "established": "establish",
    "impose": "impose", "imposes": "impose", "imposed": "impose",
    "fine": "impose", "fines": "impose",
    "take": "take measures", "takes": "take measures", "taken": "take measures",
    "implement": "take measures", "implements": "take measures", "implemented": "take measures",
    "cooperate": "cooperate", "cooperates": "cooperate", "cooperated": "cooperate",
    "exchange": "cooperate", "exchanges": "cooperate",
    "provide": "provide", "provides": "provide", "provided": "provide", "providing": "provide",
    "make": "make available", "makes": "make available",
    "publish": "publish", "publishes": "publish", "published": "publish",
    "keep": "keep records", "keeps": "keep records", "kept": "keep records",
    "document": "keep records", "documents": "keep records",
    "register": "register", "registers": "register", "registered": "register",
    "request": "request", "requests": "request", "requested": "request",
    "order": "order", "orders": "order", "ordered": "order",
    "require": "require", "requires": "require", "required": "require",
    "encourage": "encourage", "encourages": "encourage",
    "facilitate": "encourage", "facilitates": "encourage",
    "carry": "carry out", "carries": "carry out", "carried": "carry out",
    "conduct": "carry out", "conducts": "carry out", "conducted": "carry out",
    "supervise": "supervise", "supervises": "supervise",
    "monitor": "supervise", "monitors": "supervise", "monitored": "supervise",
    "enforce": "enforce", "enforces": "enforce", "enforced": "enforce",
    "lodge": "lodge complaint", "lodges": "lodge complaint",
    "investigate": "investigate", "investigates": "investigate", "investigated": "investigate",
    "refrain": "refrain", "refrains": "refrain",
    "apply": "apply", "applies": "apply", "applied": "apply",
    "comply": "comply", "complies": "comply", "complied": "comply",
    "delete": "delete", "deletes": "delete", "deleted": "delete",
    "retain": "retain", "retains": "retain", "retained": "retain",
    "disclose": "disclose", "discloses": "disclose", "disclosed": "disclose",
    "maintain": "maintain", "maintains": "maintain", "maintained": "maintain",
    "allocate": "allocate", "allocates": "allocate", "allocated": "allocate",
    "verify": "verify", "verifies": "verify", "verified": "verify",
    "respond": "respond", "responds": "respond", "responded": "respond",
}

#: A bare leading auxiliary (never the operative verb itself) that a passive
#: or infinitive action may still open with once adverbials are stripped
#: ("be done …", "to notify …") — skipped once, so the token checked next is
#: the real verb position, never a noun read off a later, unrelated clause.
_LEADING_AUX_TOKENS = frozenset({"be", "been", "to", "being"})


def _lemmatize_action_verb(action: str) -> str:
    """The lemma of THIS action's own verb — strictly the first token (after
    skipping at most one bare leading auxiliary), never a verb-shaped word
    read off a later, unrelated clause ("…has *established* a causal link…"
    is NOT this action's verb — "" is the honest answer there)."""
    tokens = re.findall(r"[A-Za-z]+", action or "")
    idx = 0
    if idx < len(tokens) and tokens[idx].lower() in _LEADING_AUX_TOKENS:
        idx += 1
    if idx < len(tokens):
        return _ACTION_VERB_LEMMAS.get(tokens[idx].lower(), "")
    return ""


#: Hedge words: "where applicable" / "where appropriate" / "where feasible" /
#: "as appropriate" etc. look like a condition to the generic marker scan but
#: scope the DUTY'S PERFORMANCE, not whether it applies — never a real
#: applicability condition.
_HEDGE_WORDS = frozenset({
    "applicable", "appropriate", "feasible", "relevant", "necessary",
    "possible", "technically feasible",
})

#: A time-period count — digits or the spelled-out form EU drafting uses
#: just as often ("within one month", "within three days").
_NUM_WORD = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve)")

#: One adverbial/timing unit: a relative deadline, an urgency cue, or a hedge.
#: Shared between the leading-adverbial strip (which pulls these out of the
#: action so the real verb surfaces) and the deadline collector (which reads
#: the same vocabulary out of the full sentence).
_ADV_UNIT_RE = re.compile(
    r"without\s+undue\s+delay"
    r"|immediately"
    r"|as\s+soon\s+as\s+possible"
    r"|in\s+any\s+event"
    r"|(?:not\s+later\s+than|no\s+later\s+than|within)\s+" + _NUM_WORD + r"\s*"
    r"(?:hours?|days?|weeks?|months?|years?)"
    r"(?:\s+(?:after|of|from)\s+[a-z][^,.;]{1,80})?"
    r"|where\s+(?:" + "|".join(sorted(_HEDGE_WORDS, key=len, reverse=True)) + r")"
    r"|as\s+(?:" + "|".join(w for w in sorted(_HEDGE_WORDS, key=len, reverse=True)
                             if " " not in w) + r")",
    re.IGNORECASE,
)

#: Deadline-only subset of :data:`_ADV_UNIT_RE` (timing cues, not hedges) —
#: used to decide whether a matched adverbial unit is worth recording in
#: :attr:`RuleFacet.deadline`.
_DEADLINE_ONLY_RE = re.compile(
    r"without\s+undue\s+delay"
    r"|immediately"
    r"|as\s+soon\s+as\s+possible"
    r"|(?:not\s+later\s+than|no\s+later\s+than|within)\s+" + _NUM_WORD + r"\s*"
    r"(?:hours?|days?|weeks?|months?|years?)"
    r"(?:\s+(?:after|of|from)\s+[a-z][^,.;]{1,80})?",
    re.IGNORECASE,
)

#: A leading/embedded adverbial clause, delimited by a comma (or the start of
#: the string) on one side and a comma (or the end of the string) on the
#: other — "shall *without undue delay and, where feasible, not later than
#: 72 hours after …,* notify" pulls three such units out in sequence, each
#: time exposing the next, until "notify" leads.
_ADV_CLAUSE_RE = re.compile(
    r"(?P<pre>^|,)\s*(?:and\s+|or\s+)?(?P<adv>" + _ADV_UNIT_RE.pattern + r")"
    r"(?:\s+(?:and|or))?\s*(?P<post>,|$)",
    re.IGNORECASE,
)


def _strip_adverbials(action: str, deadlines: list[str]) -> str:
    """Pull every leading/embedded timing-or-hedge clause out of ``action``,
    recording the timing ones (verbatim) into ``deadlines`` (de-duplicated,
    order preserved) so the operative verb is what is left in ``action``.

    This is what fixes "shall without undue delay and, where feasible, not
    later than 72 hours …, notify …" landing action="without undue delay
    and" — the boundary-trim that used to run first saw the embedded
    "where" and cut there before this pass could expose "notify".
    """
    guard = 0
    while guard < 12:
        guard += 1
        m = _ADV_CLAUSE_RE.search(action)
        if not m:
            break
        adv = m.group("adv")
        dm = _DEADLINE_ONLY_RE.fullmatch(adv)
        if dm and adv.lower() not in (d.lower() for d in deadlines):
            deadlines.append(adv)
        action = action[:m.start()] + " " + action[m.end():]
        action = re.sub(r",\s*,", ",", action)
        action = re.sub(r"^\s*,\s*", "", action)
        action = re.sub(r",\s*$", "", action)
        action = re.sub(r"\s{2,}", " ", action).strip()
    return action


def _collect_deadlines(sentence: str, existing: list[str]) -> None:
    """Scan the full sentence for timing cues :func:`_strip_adverbials`
    did not see (outside the action span), appending any not already
    recorded — "immediately … and, in any event, not later than 15 days
    …" (AI Act Art. 73(2)) needs both halves, not just the first match."""
    for m in _DEADLINE_ONLY_RE.finditer(sentence):
        frag = m.group(0)
        if frag.lower() not in (d.lower() for d in existing):
            existing.append(frag)


#: Verbs that name a recipient — the counterparty of a notify/report/inform
#: duty. Longest-first so "transmit" never shadows a longer surface form.
_COUNTERPARTY_VERBS = (
    r"notify|notifies|notifying|notified"
    r"|report|reports|reported|reporting"
    r"|inform|informs|informing"
    # "informed" alone is ambiguous with the adjective ("an *informed*
    # decision/consent/choice") — only read as the verb outside that idiom.
    r"|informed(?!\s+(?:decision|decisions|consent|choice|choices))"
    r"|submit|submits|submitted|submitting"
    r"|communicate|communicates|communicated|communicating"
    r"|transmit|transmits|transmitted|transmitting"
    r"|forward|forwards|forwarded|forwarding"
    r"|disclose|discloses|disclosed|disclosing"
    r"|made\s+available|make\s+available|makes\s+available|making\s+available"
)

#: Words that must NEVER be swallowed as a leading "modifier" of the
#: recipient NP — the communicative/duty verbs themselves, so "to *notify*
#: the authority" never reads as cp="notify the authority", and the common
#: infinitive-purpose verbs ("to *ensure* compliance") never get a chance to
#: be mistaken for the start of an NP either.
_COUNTERPARTY_NP_VERB_DENYLIST = (
    _COUNTERPARTY_VERBS +
    r"|ensure|ensures|ensured|ensuring"
    r"|respond|responds|responded|responding"
    r"|verify|verifies|verified|verifying"
    r"|request|requests|requested|requesting"
    r"|provide|provides|provided|providing"
    r"|take|takes|taken|taking|comply|complies|complied"
    r"|apply|applies|applied"
)

#: A party/institution noun — the only acceptable HEAD of a recipient NP.
#: Closed, deliberately: a recipient must be a party, never a thing ("the
#: system", "the use", "third countries", "compliance") and never a bare
#: pronoun ("it", "whom").
_PARTY_HEAD_NOUNS_RE_FRAGMENT = (
    r"member\s+states?|authorities|authority|csirts?|commission"
    r"|boards?|offices?|coordinators?|controllers?|providers?|deployers?"
    r"|recipients?|users?|subjects?|persons?|enisa|teams?"
    # "notified body/bodies" is a compound head in its own right — matched
    # whole so "notified" (also a verb-denylist form) never has to pass as
    # a bare modifier word to reach the "body" head.
    r"|notified\s+bod(?:y|ies)|bodies|body"
    r"|entities|entity|processors?|regulators?"
)

#: "notify/report/… [stuff] to (the/its/their/a/an) <0-2 non-verb modifier
#: words><party-noun head>" — attached to a communicative verb earlier in
#: the clause, the NP's head restricted to a party/institution noun (never a
#: thing, never a pronoun), and no verb (communicative or infinitive-purpose)
#: allowed inside the NP itself — this is what rejects "to ensure
#: compliance", "to the system", "to third countries", "to it", "to whom".
_COUNTERPARTY_TO_RE = re.compile(
    r"\b(?:" + _COUNTERPARTY_VERBS + r")\b[^.;]{0,160}?\bto\s+"
    r"(?:the\s+|its\s+|their\s+|a\s+|an\s+)?"
    r"(?P<cp>(?:(?!(?:" + _COUNTERPARTY_NP_VERB_DENYLIST + r")\b)"
    r"[a-z][\w\-]*\s+){0,2}"
    r"(?:" + _PARTY_HEAD_NOUNS_RE_FRAGMENT + r"))\b",
    re.IGNORECASE,
)

#: Known institutional recipient nouns — used for the no-"to" direct-object
#: form ("notify its CSIRT", "notify the authority of any changes"). Same
#: closed party/institution list as the "to" form, plus the compound
#: institutional phrases that read as a single head for this fixed-verb form.
_ROLE_NOUNS = (
    "csirt", "csirts", "supervisory authority", "competent authority",
    "authority", "authorities", "board", "commission", "controller",
    "controllers", "processor", "processors", "provider", "providers",
    "deployer", "deployers", "data protection officer", "dpo",
    "single point of contact", "coordinator", "regulator", "enisa",
    "member state", "member states", "data subject", "data subjects",
    "recipient", "recipients", "user", "users", "subject", "subjects",
    "person", "persons", "team", "teams", "body", "bodies",
    "entity", "entities",
    "market surveillance authority", "market surveillance authorities",
    "notified body", "notified bodies",
)
_COUNTERPARTY_DIRECT_RE = re.compile(
    r"\b(?:notify|notifies|notified|notifying"
    r"|report|reports|reported|reporting"
    r"|inform|informs|informed|informing)\b\s+(?:its|their|the)\s+"
    r"(?P<cp>" + "|".join(sorted(_ROLE_NOUNS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

#: Never a resolution on their own — a pronoun names no party.
_COUNTERPARTY_PRONOUN_STOPLIST = frozenset({
    "it", "them", "whom", "who", "this", "that", "these", "those",
})


def _extract_counterparty_en(action: str, raw: str) -> str:
    """The recipient named by a notify/report/inform/submit/… duty.

    Read ONLY off ``action`` — THIS rule's own operative text — never off
    the full ``raw`` sentence: a long enumerated EU provision is frequently
    one giant un-split "sentence" (no full stop between sub-clauses), and a
    completely unrelated clause fifty words later can name a recipient of
    ITS OWN notify duty, not this rule's. ``raw`` is accepted as a
    parameter for call-site stability but no longer searched; kept so a
    future, more surgical use (e.g. a bounded window around the action's
    own span) can be added without another signature change.

    "to …" form first (a party/institution-noun-headed NP, marked by the
    preposition), then the no-preposition direct-object form (bounded to
    the same party/institution noun list — "notify its CSIRT", "notify the
    authority of any changes"). "" when neither fires — never guessed,
    never a pronoun, never the thing being reported instead of who it is
    reported to.
    """
    del raw  # intentionally unused — see docstring
    m = _COUNTERPARTY_TO_RE.search(action or "")
    if m:
        cp = m.group("cp").strip()
        if cp.lower() not in _COUNTERPARTY_PRONOUN_STOPLIST:
            return cp
    m = _COUNTERPARTY_DIRECT_RE.search(action or "")
    if m:
        return m.group("cp").strip()
    return ""


#: Fronted trigger clauses that land IN the subject capture because the
#: bespoke subject char-class is deliberately permissive ("In the case of a
#: personal data breach, the controller shall …" — the whole clause up to
#: the modal is the lazy subject match). Moves the trigger into
#: :attr:`RuleFacet.condition` (if not already populated) and leaves the
#: real bearer as the subject.
_LEADING_CLAUSE_RE = re.compile(
    r"^(?:in\s+the\s+case\s+of|in\s+the\s+event\s+of|where|if|when|upon|once"
    r"|after\s+becoming\s+aware\s+(?:of|that)"
    r"|in\s+deciding)\s+"
    r"(?P<trigger>[^,]+),\s*(?P<rest>.+)$",
    re.IGNORECASE,
)


def _split_leading_clause(subject: str) -> tuple[str, str]:
    """``(real_subject, trigger)`` — ``trigger`` is "" when ``subject`` has
    no fronted clause to strip."""
    m = _LEADING_CLAUSE_RE.match(subject)
    if not m:
        return subject, ""
    return m.group("rest").strip(), m.group("trigger").strip()


def _extract_condition_en(sentence: str) -> str:
    """The real applicability trigger, never a hedge or a locative relative
    clause.

    Scans every ``condition_markers`` hit in the sentence (not just the
    first) and skips two kinds of false positive:
      * a hedge ("where applicable", "where appropriate", "where feasible")
        — scopes performance, not applicability;
      * a locative "where" attached to a preceding noun ("… in one of the
        Member States *where* the provider offers its services") — a
        relative clause describing the noun, not a sentence-level trigger.
        The tell: a genuine trigger's "where"/"if"/… is clause-initial (the
        sentence start, or right after a comma); a locative one is not.
    """
    prof = _PROFILES["en"]
    if prof.condition_pattern is None:
        return ""
    for m in prof.condition_pattern.finditer(sentence):
        cand = m.group("cond").strip()
        low = cand.rstrip(" .,;:").lower()
        if low in _HEDGE_WORDS:
            continue
        marker_text = sentence[m.start():m.end() - len(m.group("cond"))].strip().lower()
        if marker_text == "where":
            preceding = sentence[:m.start()].rstrip()
            is_clause_boundary = preceding == "" or preceding[-1] in ",;:"
            if not is_clause_boundary:
                continue  # locative relative clause, not a trigger
        return cand
    return ""


def extract_rules(content: str, *,
                  fingerprint_gate: "FingerprintGate | None" = None) -> list[RuleFacet]:
    """Extract structured rules from normative content (EU-wide).

    Splits content into sentences; detects each sentence's language; runs
    that language's rule patterns. Returns one :class:`RuleFacet` per matched
    sentence. A sentence that fails all patterns is dropped — the extractor
    errs on the side of high-precision output.

    Args:
        content: text to extract from.
        fingerprint_gate: an optional injected pre-filter — ``gate(content) ->
            bool`` — deciding WHETHER content is worth extracting from at all
            before this module decides WHAT the rules are. A host routing
            layer may wire its normative-fingerprint classifier in here; the
            plane itself carries no opinion on the gate and runs ungated
            (every candidate sentence considered) when none is supplied.
    """
    if fingerprint_gate is not None and not fingerprint_gate(content):
        return []

    rules: list[RuleFacet] = []
    sentences = _segment(content)
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 12:
            continue
        lang = _detect_language(sentence)
        prof = _PROFILES.get(lang) or _PROFILES["en"]

        ensurer = ""
        leading_trigger = ""
        # Try every bespoke/generic pattern in order (not just the first
        # that matches at all): a pattern whose subject/modal came back
        # empty, whose subject head is a pronoun, or whose subject is
        # STILL headed by a pronoun once a fronted trigger clause is split
        # off ("Where the processor engages another processor, it shall
        # …" -> subject "it") is rejected and the NEXT pattern is tried —
        # never the whole sentence abandoned on the first pattern's
        # failure.
        matched = None
        for pat in prof.rule_patterns:
            m = pat.search(sentence)
            if not m:
                continue
            groups = m.groupdict()
            cand_subject = (groups.get("subject") or "").strip()
            cand_modal = (groups.get("modal") or "").strip()
            cand_action = (groups.get("action") or "").strip()
            cand_consequence = (groups.get("consequence") or "").strip()
            if cand_consequence:
                cand_action = f"{cand_action} → {cand_consequence}".strip(" →")
            if not (cand_subject and cand_modal):
                continue
            cand_head = cand_subject.lower().split()[0] if cand_subject else ""
            if cand_head in prof.pronoun_stoplist:
                continue
            cand_trigger = ""
            # Only split a fronted clause off a subject that actually
            # STARTS the sentence (m.start("subject") == 0). A subject
            # capture that starts mid-sentence — the 120-char
            # anti-backtracking cap on the long bespoke patterns forces
            # this on a long compound NP — is not a fronted clause even
            # when it happens to open with one of the lead-in words;
            # splitting it there would drop real subject text.
            if lang == "en" and m.start("subject") == 0:
                split_subject, cand_trigger = _split_leading_clause(cand_subject)
                post_head = split_subject.lower().split()[0] if split_subject else ""
                if post_head in prof.pronoun_stoplist:
                    continue
                cand_subject = split_subject
            matched = (cand_subject, cand_modal, cand_action, cand_trigger)
            break
        if matched is None:
            continue
        subject, modal_phrase, action, leading_trigger = matched
        modal_class = _classify_modal(modal_phrase, lang)
        # Discontinuous negation (Germanic separable verbs: "mag … niet",
        # "darf … nicht"): a permission modal with a trailing negator in
        # the action is a prohibition.
        if (modal_class == "permission" and prof.negator_re is not None
                and prof.negator_re.search(action)):
            modal_class = "prohibition"
        # Leading-negation flip (English): "must never deploy" / a bare-modal
        # sentence whose action opens with a negator is a prohibition — the
        # negation binds the modal. The negator is stripped so the operative
        # verb leads the action; the surface phrase records the negation.
        if lang == "en" and modal_class in ("obligation", "permission"):
            nm = _LEADING_NEG_EN.match(action)
            if nm:
                modal_class = "prohibition"
                modal_phrase = f"{modal_phrase} {nm.group(0).strip()}".strip()
                action = action[nm.end():].strip()

        deadlines: list[str] = []
        if lang == "en":
            # Pull leading/embedded timing-and-hedge clauses out of the action
            # BEFORE the condition/exception boundary trim runs, so an
            # embedded hedge ("… and, where feasible, not later than 72
            # hours …, notify …") cannot be mistaken for the boundary and cut
            # the action down to the adverbial alone.
            action = _strip_adverbials(action, deadlines)

        condition = exception = ""
        if lang == "en":
            condition = _extract_condition_en(sentence)
        elif prof.condition_pattern:
            cm = prof.condition_pattern.search(sentence)
            condition = cm.group("cond").strip() if cm else ""
        if leading_trigger and not condition:
            condition = leading_trigger
        if prof.exception_pattern:
            em = prof.exception_pattern.search(sentence)
            exception = em.group("exc").strip() if em else ""
        # The action must not swallow a trailing condition/exception clause
        # ("establish X, unless Y" → action "establish X", exception "Y").
        # Trim the action at the first remaining condition/exception marker
        # (the English hedge/deadline markers are already gone by this point).
        _boundary = _marker_regex(prof.condition_markers + prof.exception_markers)
        if _boundary is not None:
            bm = _boundary.search(action)
            if bm and bm.start() > 0:
                action = action[:bm.start()].rstrip(" ,;–-")
        # The MS-ensure rewrite reads its action straight out of the raw
        # sentence tail, which (unlike the regular pattern's action group)
        # includes the closing full stop — strip it, here, universally.
        action = action.rstrip(" .;")

        # Compound rule: an "otherwise …" / "failing which …" / "or else …"
        # branch names the fallback if the requirement is not met. The action
        # group stopped at ";", so capture that branch verbatim rather than
        # dropping it (dropping it is what lets a downstream drafter guess).
        consequence = ""
        cq = _OTHERWISE_RE.search(sentence)
        if cq:
            consequence = cq.group("conseq").strip().rstrip(" .;,")

        deadline = ""
        counterparty = ""
        action_verb = ""
        if lang == "en":
            _collect_deadlines(sentence, deadlines)
            deadline = "; ".join(deadlines)
            counterparty = _extract_counterparty_en(action, sentence)
            action_verb = _lemmatize_action_verb(action)

        populated = sum(1 for x in (subject, modal_phrase, action) if x)
        extras = sum(1 for x in (condition, exception) if x)
        confidence = 0.6 + 0.1 * (populated - 2) + 0.1 * extras
        confidence = max(0.4, min(1.0, confidence))

        # Agentless-passive addressee check: "X shall be established" with no
        # "by <agent>" means subject is the patient, not the addressee. Flag
        # it and shave confidence rather than asserting a wrong addressee.
        # The subject is never rewritten here — a "by <agent>" phrase only
        # tells :func:`_is_agentless_passive` the agent is NAMED (so this
        # isn't an abstention case); it does not say the match belongs to
        # the main clause rather than an embedded relative clause ("…a
        # national authority, which shall be supervised by the
        # Commission"), so it is never promoted to the subject. No
        # cross-sentence carry-forward either. Byte-identical to main's
        # behaviour on this.
        addressee_resolved = not _is_agentless_passive(
            modal_phrase, action, lang)
        if not addressee_resolved:
            confidence = max(0.4, confidence - 0.1)

        rules.append(RuleFacet(
            subject=subject.lower(),
            modal=modal_class,
            modal_phrase=modal_phrase,
            action=action,
            condition=condition,
            exception=exception,
            consequence=consequence,
            raw_sentence=sentence,
            language=lang,
            confidence=confidence,
            addressee_resolved=addressee_resolved,
            deadline=deadline,
            counterparty=counterparty,
            action_verb=action_verb,
            ensurer=ensurer,
        ))
    return rules
